"""One-shot CI tool for the Rust product (MooKKo), never a management server. Called only when tests are enabled.

The C# host (NativeWorkflow.VerifyAsync) runs this inside the QA role's AppContainer on the exact candidate commit, after it
ran Trivy, OSV-Scanner and Semgrep itself on a snapshot of that commit (--host-scanners). Every step must pass; the last
line printed is the JSON the host checks (status, head, base, checksCommit, services, steps) before it signs a receipt.

Steps, in order (any failure stops the run and no receipt is issued):
  1. the checkout is exactly --sha and clean; the approved base is its ancestor; trusted CI paths equal the checks commit
  2. every crate root (lib, bin, test, bench, example, build script) declares #![forbid(unsafe_code)]
  3. cargo fmt --all -- --check
  4. cargo clippy --workspace --all-targets --all-features --locked -- -D warnings
  5. cargo test --workspace --all-features --locked
  6. cargo deny --locked check            (pinned executable, sha256 checked)
  7. cargo audit --deny warnings          (pinned executable, sha256 checked)
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

POLICY_VERSION = "mookkorust-validation-v1"
# Changing these needs its own reviewed policy export (a new checksCommit), never a worker's candidate.
TRUSTED_PATHS = ("deny.toml", "rust-toolchain.toml", ".cargo/", "clippy.toml", "rustfmt.toml", "docs/policy/",
                 "docs/coordination/owners.json", "scripts/ci/", ".github/")
FORBID = re.compile(r"^\s*#!\[\s*forbid\s*\(([^)]*)\)\s*\]", re.MULTILINE)


def git(root, *args):
    return subprocess.check_output(["git", "-c", "core.hooksPath=NUL", *args], cwd=root, stderr=subprocess.PIPE).decode("utf-8").strip()


def assert_checkout(checkout, sha):
    if git(checkout, "rev-parse", "HEAD") != sha or git(checkout, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("Validation checkout changed or is not clean")


def validate_policy(checkout, sha, policy):
    for key in ("baseCommit", "checksCommit"):
        if not re.fullmatch(r"[0-9a-f]{40}", policy.get(key) or "") or git(checkout, "rev-parse", "--verify", policy[key] + "^{commit}") != policy[key]:
            raise ValueError("Missing approved product revision: " + key)
    subprocess.run(["git", "merge-base", "--is-ancestor", policy["baseCommit"], sha], cwd=checkout, check=True, capture_output=True)
    changed = git(checkout, "diff", "--name-only", policy["checksCommit"], sha, "--", *TRUSTED_PATHS)
    if changed:
        raise ValueError("Validation policy changes need separate review: " + changed)
    assert_checkout(checkout, sha)


def pinned(tools, name):
    pin = tools.get(name) or {}
    executable = Path(pin.get("executable", ""))
    if not executable.is_absolute() or not executable.is_file() or not re.fullmatch(r"[0-9a-f]{64}", pin.get("sha256") or "") \
            or hashlib.sha256(executable.read_bytes()).hexdigest() != pin["sha256"]:
        raise ValueError("An independently pinned " + name + " executable is required")
    return str(executable)


def crate_roots(checkout, cargo):
    raw = subprocess.check_output([cargo, "metadata", "--no-deps", "--format-version", "1", "--locked"], cwd=checkout)
    metadata = json.loads(raw)
    members = set(metadata.get("workspace_members") or [])
    roots = []
    for package in metadata["packages"]:
        if package["id"] not in members:
            continue
        for target in package["targets"]:
            roots.append(Path(target["src_path"]))
    if not roots:
        raise ValueError("The workspace has no crate targets")
    return sorted(set(roots))


def unsafe_violations(checkout, roots):
    missing = []
    base = checkout.resolve()
    for root in roots:
        path = root.resolve()
        if base not in path.parents:
            raise ValueError("A crate root lies outside the candidate: " + str(root))
        text = path.read_text(encoding="utf-8-sig")
        if not any("unsafe_code" in [part.strip() for part in match.group(1).split(",")] for match in FORBID.finditer(text)):
            missing.append(path.relative_to(base).as_posix())
    return missing


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    for key in ("candidate", "sha", "service", "policy", "evidence"):
        parser.add_argument("--" + key, required=True)
    parser.add_argument("--host-scanners", action="store_true")
    args = parser.parse_args()
    candidate, evidence = Path(args.candidate).resolve(), Path(args.evidence).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    configured = json.loads(Path(args.policy).read_text(encoding="utf-8-sig"))
    policy, tools = configured["policy"], (configured.get("tools") or {}).get("tools") or configured.get("tools") or {}
    if not args.host_scanners:
        raise ValueError("Trivy, OSV-Scanner and Semgrep run on the host for MooKKo; a run without them is not a validation")
    # The whole Cargo workspace is validated on every receipt, whichever area asked; the host compares this set with the policy.
    services = list(policy.get("requiredServices") or [])
    if not services:
        raise ValueError("The approved policy names no required services")
    validate_policy(candidate, args.sha, policy)
    cargo = shutil.which("cargo")
    if not cargo:
        raise ValueError("cargo is not on PATH")
    deny, audit = pinned(tools, "cargo-deny"), pinned(tools, "cargo-audit")
    steps = []

    def run(name, command):
        logfile = evidence / (str(len(steps)) + "-" + name + ".log")
        with logfile.open("wb") as stream:
            result = subprocess.run(command, cwd=candidate, stdout=stream, stderr=subprocess.STDOUT, timeout=3600, check=False)
        steps.append({"name": name, "command": command, "status": "passed" if result.returncode == 0 else "failed",
                      "exitCode": result.returncode, "outputSha256": hashlib.sha256(logfile.read_bytes()).hexdigest()})
        if result.returncode:
            raise RuntimeError("CI step failed (" + name + "); protected host receipt was not issued")

    missing = unsafe_violations(candidate, crate_roots(candidate, cargo))
    (evidence / "forbid-unsafe.json").write_text(json.dumps({"missing": missing}), encoding="utf-8")
    steps.append({"name": "forbid-unsafe", "command": ["#![forbid(unsafe_code)] on every crate root"], "status": "failed" if missing else "passed",
                  "exitCode": 1 if missing else 0, "outputSha256": hashlib.sha256(json.dumps(missing).encode()).hexdigest()})
    if missing:
        raise RuntimeError("Crate roots without #![forbid(unsafe_code)]: " + ", ".join(missing[:10]))
    run("fmt", [cargo, "fmt", "--all", "--", "--check"])
    run("clippy", [cargo, "clippy", "--workspace", "--all-targets", "--all-features", "--locked", "--", "-D", "warnings"])
    run("test", [cargo, "test", "--workspace", "--all-features", "--locked"])
    run("deny", [deny, "--locked", "check"])
    run("audit", [audit, "audit", "--deny", "warnings"])
    # cargo writes only target/ (ignored); anything else changing means a build script or test touched the sources.
    assert_checkout(candidate, args.sha)
    result = {"policy": POLICY_VERSION, "head": args.sha, "status": "passed", "base": policy["baseCommit"],
              "checksCommit": policy["checksCommit"], "services": services, "requested": args.service, "steps": steps, "hostScanners": args.host_scanners}
    (evidence / "validation.json").write_text(json.dumps(result), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(json.dumps({"status": "failed", "error": str(error)[:2000]}))
        sys.exit(1)
