"""Write the one product policy the C# runtime judges QA receipts against, from the Rust product's main.

The C# runtime (NativeWorkflow.VerifyAsync) refuses to issue a QA receipt without this file. Its source is the MooKKo product repository
docs/policy/gates.json at the exact main commit: gates, path patterns, judging criteria, documentation-only pattern,
required services and the exception register. baseCommit and checksCommit are that main commit, so validate-rust.py
refuses a candidate that changed a trusted CI path since the approved policy.

Usage (from the MooKKoDev harness checkout):
    python -X utf8 tools/export-policy.py --repo <product repository path> [--ref main] [--out <path>]
Default output: data/runtime/product-policy.json (the C# option productPolicyFile).
"""
import argparse
import datetime
import json
import re
import subprocess
from pathlib import Path

GATE = re.compile(r"^[A-Z][A-Z0-9]*-\d{2}$")


def git(repo, *args):
    return subprocess.check_output(["git", "-c", "core.hooksPath=NUL", "-C", str(repo), *args]).decode("utf-8")


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--repo", required=True, help="product repository path (from the harness config)")
    parser.add_argument("--ref", default="main")
    parser.add_argument("--out", help="output path (default: data/runtime/product-policy.json)")
    args = parser.parse_args()
    commit = git(args.repo, "rev-parse", "--verify", args.ref + "^{commit}").strip()
    source = json.loads(git(args.repo, "show", commit + ":docs/policy/gates.json"))
    gates = source.get("gates") or []
    if not gates or any(not GATE.match(g) for g in gates) or len(set(gates)) != len(gates):
        raise SystemExit("gates.json needs distinct gate IDs")
    paths = source.get("gatePaths") or {}
    if set(paths) - set(gates) or not source.get("requiredServices"):
        raise SystemExit("gatePaths names unknown gates or requiredServices is empty")
    for gate, patterns in paths.items():
        for pattern in patterns:
            re.compile(pattern)
    policy = {
        "baseCommit": commit,
        "checksCommit": commit,
        "requiredServices": source["requiredServices"],
        "gates": gates,
        "gatePaths": paths,
        "gateCriteria": {k: v for k, v in (source.get("gateCriteria") or {}).items() if k in gates},
        "gatesSinceById": source.get("gatesSinceById") or {},
        "docOnlyPaths": source.get("docOnlyPaths") or "",
        "gateExceptions": source.get("gateExceptions") or [],
        "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "source": "MooKKo " + commit + ":docs/policy/gates.json",
    }
    out = Path(args.out) if args.out else Path(__file__).resolve().parent.parent / "data" / "runtime" / "product-policy.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    pending = out.with_suffix(".json.pending")
    pending.write_text(json.dumps(policy, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    pending.replace(out)
    print(json.dumps({"out": str(out), "commit": commit, "gates": len(gates), "requiredServices": policy["requiredServices"],
                      "gatePaths": sorted(paths), "exceptions": len(policy["gateExceptions"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
