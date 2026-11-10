"""Pinned security scanners for native validation (harness review 2026-10-19, P1-4).

Pins (executable, sha256, version) come from MooKKoDev's own tools manifest (`data/tools/manifest.json`, pointed to by
`securityToolsManifest` in the OpenRig config). `validation_policy.execute()` verifies each pin, runs this module as a
separate recorded step per scanner and then re-reads the evidence file it produced. Everything fails closed: a missing
pin, a checksum or version mismatch, a scanner error, a missing or malformed result file, or a blocking finding stops
the validation. Semgrep has no Windows wheel, so it runs inside the worker WSL distribution: the exact commit tree goes
in through stdin (`git archive`), the JSON report comes back through stdout.

지움(11-10): 하네스 `data/tools/`(manifest.json·도구 묶음)는 지웠습니다. 옛 구조 참고용으로만 둡니다.

This file is also executed directly (`python -B security_tools.py <scanner> ...`), so it imports nothing from the package.
"""
import argparse
import hashlib
import io
import json
import os
import re
import shlex
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

TOOLS = ("gitleaks", "trivy", "osv-scanner", "cyclonedx", "semgrep")
TRIVY_BLOCKING = ("HIGH", "CRITICAL")
SEMGREP_RULES = ("p/csharp", "p/secrets", "p/security-audit")
SEMGREP_BLOCKING = ("ERROR",)
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
SHA256 = re.compile(r"[0-9a-f]{64}")


# ---------------------------------------------------------------- pins

def tool_pins(config):
    """Read the verified tools manifest named by the config and return one pin per scanner."""
    location = config.get("securityToolsManifest")
    if not isinstance(location, str) or not location:
        raise ValueError("Missing security tools manifest path (securityToolsManifest)")
    path = Path(os.path.expandvars(location))
    try:
        manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise ValueError("Unreadable security tools manifest: " + str(path)) from error
    rows = manifest.get("tools") if isinstance(manifest, dict) else None
    if not isinstance(rows, dict):
        raise ValueError("Security tools manifest has no tools table")
    pins = {"manifest": str(path)}
    for name in TOOLS:
        row = rows.get(name)
        if not isinstance(row, dict) or not isinstance(row.get("executable"), str) or not row["executable"] \
                or not isinstance(row.get("version"), str) or not row["version"]:
            raise ValueError("Missing security tool pin: " + name)
        pin = {"executable": row["executable"], "version": row["version"]}
        if name == "semgrep":
            distribution = row.get("distribution") or config.get("distribution")
            if not isinstance(distribution, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", distribution):
                raise ValueError("Missing WSL distribution for Semgrep")
            pin["distribution"] = distribution
            if distribution == "windows":
                # Native Windows Semgrep (10-25): the pinned interpreter runs the pip --target install named by pythonPath.
                if not isinstance(row.get("pythonPath"), str) or not row["pythonPath"] \
                        or not isinstance(row.get("sha256"), str) or not SHA256.fullmatch(row["sha256"]):
                    raise ValueError("Windows Semgrep needs pythonPath and the interpreter checksum")
                pin["pythonPath"], pin["sha256"] = row["pythonPath"], row["sha256"]
        else:
            if not isinstance(row.get("sha256"), str) or not SHA256.fullmatch(row["sha256"]):
                raise ValueError("Missing security tool checksum: " + name)
            pin["sha256"] = row["sha256"]
        if name == "trivy":
            cache = row.get("cacheDir") or str(Path(row["executable"]).parent.parent / "cache")
            if not isinstance(cache, str) or not cache:
                raise ValueError("Missing Trivy cache directory")
            pin["cacheDir"] = cache
        pins[name] = pin
    return pins


def verify_executable(executable, digest, name):
    """The pinned file must exist and hash to the pinned digest; returns the absolute path."""
    path = Path(executable)
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        raise ValueError("Missing security tool checksum: " + name)
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError("Security tool checksum mismatch: " + name)
    return str(path.resolve())


def verified(pins, name):
    """Pin of `name` from tool_pins() after verifying its executable (WSL Semgrep is checked by version inside WSL;
    native Windows Semgrep verifies the pinned interpreter)."""
    pin = (pins or {}).get(name)
    if not isinstance(pin, dict):
        raise ValueError("Missing security tool pin: " + name)
    if name != "semgrep" or pin.get("distribution") == "windows":
        verify_executable(pin["executable"], pin.get("sha256"), name)
    return pin


# ---------------------------------------------------------------- verdicts (shared by the helper and execute())

def vulnerable_packages(listing, project=None):
    """Rows for every vulnerable package in `dotnet list package --vulnerable --include-transitive --format json`."""
    if not isinstance(listing, dict) or not isinstance(listing.get("projects"), list):
        raise ValueError("Unexpected dotnet list package output")
    rows = []
    for entry in listing["projects"]:
        for problem in (entry.get("problems") or []) + (listing.get("problems") or []):
            if isinstance(problem, dict) and str(problem.get("level", "")).lower() == "error":
                raise ValueError("dotnet list package reported an error: " + str(problem.get("text")))
        for framework in entry.get("frameworks") or []:
            for scope, transitive in (("topLevelPackages", False), ("transitivePackages", True)):
                for package in framework.get(scope) or []:
                    for vulnerability in package.get("vulnerabilities") or []:
                        rows.append({"project": project or entry.get("path"), "framework": framework.get("framework"),
                                     "package": package.get("id"), "version": package.get("resolvedVersion"),
                                     "transitive": transitive, "severity": vulnerability.get("severity"),
                                     "advisory": vulnerability.get("advisoryurl")})
    return rows


def vulnerable_blocking(report, service=None):
    if not isinstance(report, dict) or report.get("service") != service or not isinstance(report.get("vulnerable"), list) \
            or not isinstance(report.get("projects"), list) or report.get("status") not in ("passed", "vulnerable", "no-projects"):
        raise ValueError("Malformed vulnerable package evidence")
    return report["vulnerable"]


def sbom_blocking(report, service=None, projects=None):
    if not isinstance(report, dict) or report.get("bomFormat") != "CycloneDX" or not isinstance(report.get("components"), list):
        raise ValueError("Malformed SBOM evidence")
    component = (report.get("metadata") or {}).get("component") or {}
    properties = {p.get("name"): p.get("value") for p in (report.get("metadata") or {}).get("properties") or [] if isinstance(p, dict)}
    if component.get("name") != "mookko-" + str(service) or properties.get("mookko:service") != service:
        raise ValueError("SBOM evidence names another service")
    if projects is not None and properties.get("mookko:projects") != str(len(projects)):
        raise ValueError("SBOM evidence covers a different project count")
    return []


def trivy_blocking(report):
    if not isinstance(report, dict) or report.get("SchemaVersion") != 2 or "ArtifactName" not in report:
        raise ValueError("Malformed Trivy evidence")
    rows = []
    for result in report.get("Results") or []:
        target = result.get("Target")
        for item in result.get("Vulnerabilities") or []:
            if str(item.get("Severity", "")).upper() in TRIVY_BLOCKING:
                rows.append({"kind": "vulnerability", "target": target, "id": item.get("VulnerabilityID"),
                             "package": item.get("PkgName"), "version": item.get("InstalledVersion"), "severity": item.get("Severity")})
        for item in result.get("Secrets") or []:   # every secret blocks, whatever severity the rule carries
            rows.append({"kind": "secret", "target": target, "id": item.get("RuleID"), "severity": item.get("Severity"),
                         "line": item.get("StartLine")})
        for item in result.get("Misconfigurations") or []:
            if item.get("Status") == "FAIL" and str(item.get("Severity", "")).upper() in TRIVY_BLOCKING:
                rows.append({"kind": "misconfiguration", "target": target, "id": item.get("ID"), "severity": item.get("Severity")})
    return rows


def osv_blocking(report):
    if not isinstance(report, dict) or not isinstance(report.get("results"), list):
        raise ValueError("Malformed OSV-Scanner evidence")
    if report.get("status") == "no-targets":
        return []
    rows = []
    for result in report["results"]:
        source = (result.get("source") or {}).get("path")
        for package in result.get("packages") or []:
            info = package.get("package") or {}
            for vulnerability in package.get("vulnerabilities") or []:
                rows.append({"kind": "vulnerability", "target": source, "id": vulnerability.get("id"),
                             "package": info.get("name"), "version": info.get("version")})
    return rows


def semgrep_blocking(report):
    if not isinstance(report, dict) or not isinstance(report.get("results"), list) or not isinstance(report.get("errors"), list):
        raise ValueError("Malformed Semgrep evidence")
    scanned = (report.get("paths") or {}).get("scanned")
    if not isinstance(scanned, list) or not scanned:
        raise ValueError("Semgrep scanned no files")
    rows = []
    for finding in report["results"]:
        severity = str((finding.get("extra") or {}).get("severity", "")).upper()
        if severity in SEMGREP_BLOCKING:
            rows.append({"kind": "semgrep", "id": finding.get("check_id"), "path": finding.get("path"),
                         "line": (finding.get("start") or {}).get("line"), "severity": severity})
    return rows


def require_clean(path, kind, **context):
    """Load the evidence file a scanner step wrote and refuse validation on any blocking finding (fail closed)."""
    path = Path(path)
    label = kind + (" (" + context["service"] + ")" if context.get("service") else "")
    if not path.is_file():
        raise ValueError("Missing security evidence: " + label)
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise ValueError("Unreadable security evidence: " + label) from error
    verdicts = {"vulnerable": vulnerable_blocking, "sbom": sbom_blocking, "trivy": trivy_blocking, "osv": osv_blocking, "semgrep": semgrep_blocking}
    blocking = verdicts[kind](report, **context)
    if blocking:
        raise ValueError(f"Blocking security findings in {label}: {len(blocking)}")
    return report


# ---------------------------------------------------------------- helper subcommands (one recorded validation step each)

def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def capture(command, **kwargs):
    # English dotnet messages keep the evidence readable (the console code page garbles Korean text in captured output).
    environment = {**os.environ, "DOTNET_CLI_UI_LANGUAGE": "en-US", "DOTNET_NOLOGO": "1", **kwargs.pop("env", {})}
    return subprocess.run(command, capture_output=True, creationflags=CREATE_NO_WINDOW, env=environment, **kwargs)


def json_output(text, label):
    start = text.find("{")
    if start < 0:
        raise SystemExit(label + " produced no JSON")
    try:
        return json.loads(text[start:])
    except ValueError as error:
        raise SystemExit(label + " produced unreadable JSON: " + str(error))


def run_vulnerable(args):
    report = {"tool": "dotnet list package --vulnerable --include-transitive", "service": args.service,
              "projects": list(args.projects), "vulnerable": [], "status": "no-projects"}
    for project in args.projects:
        result = capture(["dotnet", "list", project, "package", "--vulnerable", "--include-transitive", "--format", "json"],
                         text=True, encoding="utf-8", errors="replace")
        if result.returncode:
            raise SystemExit(f"dotnet list package failed for {project} ({result.returncode}): {(result.stderr or result.stdout).strip()[:2000]}")
        report["vulnerable"] += vulnerable_packages(json_output(result.stdout, "dotnet list package"), project)
    if args.projects:
        report["status"] = "vulnerable" if report["vulnerable"] else "passed"
    write_json(args.output, report)
    if report["vulnerable"]:
        for row in report["vulnerable"]:
            print(f"vulnerable: {row['package']} {row['version']} ({row['severity']}) in {row['project']} {row['advisory']}")
        raise SystemExit(f"{len(report['vulnerable'])} vulnerable package(s) in service {args.service}")
    print(f"vulnerable packages: none in {len(args.projects)} project(s) of {args.service}")
    return 0


def merge_boms(service, boms):
    components, dependencies, seen, seen_refs = [], [], set(), set()
    for bom in boms:
        for component in bom.get("components") or []:
            key = component.get("purl") or component.get("bom-ref") or json.dumps(component, sort_keys=True)
            if key not in seen:
                seen.add(key)
                components.append(component)
        for dependency in bom.get("dependencies") or []:
            ref = dependency.get("ref")
            if ref not in seen_refs:
                seen_refs.add(ref)
                dependencies.append(dependency)
    return {"bomFormat": "CycloneDX", "specVersion": "1.7", "version": 1,
            "metadata": {"component": {"type": "application", "bom-ref": "mookko-" + service, "name": "mookko-" + service},
                         "properties": [{"name": "mookko:service", "value": service},
                                        {"name": "mookko:projects", "value": str(len(boms))},
                                        {"name": "mookko:generator", "value": "CycloneDX dotnet tool, merged per service"}]},
            "components": components, "dependencies": dependencies}


def run_sbom(args):
    executable = verify_executable(args.executable, args.sha256, "cyclonedx")
    output = Path(args.output)
    parts = output.with_suffix("")
    boms = []
    for project in args.projects:
        name = Path(project).stem + ".json"
        result = capture([executable, project, "-o", str(parts), "-fn", name, "-F", "Json", "-dpr", "-sn", Path(project).stem],
                         text=True, encoding="utf-8", errors="replace")
        if result.returncode:
            raise SystemExit(f"CycloneDX failed for {project} ({result.returncode}): {(result.stderr or result.stdout).strip()[:2000]}")
        # Without obj/project.assets.json the tool still exits 0 with an empty BOM (measured 10-19): that is no SBOM.
        if "Found Assetsfile under" not in (result.stdout or ""):
            raise SystemExit(f"CycloneDX found no restored assets for {project}: {(result.stdout or '').strip()[:800]}")
        try:
            bom = json.loads((parts / name).read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise SystemExit(f"CycloneDX wrote no readable BOM for {project}: {error}")
        if bom.get("bomFormat") != "CycloneDX":
            raise SystemExit("CycloneDX wrote an unexpected document for " + project)
        boms.append(bom)
    write_json(output, merge_boms(args.service, boms))
    print(f"sbom: {sum(len(b.get('components') or []) for b in boms)} component(s) from {len(boms)} project(s) of {args.service}")
    return 0


def run_trivy(args):
    executable = verify_executable(args.executable, args.sha256, "trivy")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    result = capture([executable, "fs", "--scanners", "vuln,secret,misconfig", "--cache-dir", args.cache_dir, "--skip-version-check",
                      "--format", "json", "--output", str(output), "--exit-code", "0", "--quiet", args.target],
                     text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise SystemExit(f"Trivy failed ({result.returncode}): {(result.stderr or result.stdout).strip()[:2000]}")
    try:
        report = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SystemExit("Trivy wrote no readable report: " + str(error))
    blocking = trivy_blocking(report)
    if blocking:
        for row in blocking:
            print("trivy: " + json.dumps(row, ensure_ascii=False))
        raise SystemExit(f"{len(blocking)} blocking Trivy finding(s)")
    print(f"trivy: no {'/'.join(TRIVY_BLOCKING)} findings or secrets in {len(report.get('Results') or [])} target(s)")
    return 0


def run_osv(args):
    executable = verify_executable(args.executable, args.sha256, "osv-scanner")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # --all-packages keeps the scanned packages in the evidence, not only the vulnerable ones (coverage is visible).
    result = capture([executable, "scan", "source", "-r", args.target, "--all-packages", "--format", "json", "--output-file", str(output)],
                     text=True, encoding="utf-8", errors="replace")
    messages = (result.stderr or "") + (result.stdout or "")
    if result.returncode == 128 and "No package sources found" in messages:
        # The product has almost no lock files yet; requiring them is the product's work (P1-4 item 1).
        write_json(output, {"tool": "osv-scanner", "status": "no-targets", "results": [], "message": "No package sources found"})
        print("osv-scanner: no lock files found (no-targets)")
        return 0
    if result.returncode not in (0, 1):
        raise SystemExit(f"OSV-Scanner failed ({result.returncode}): {messages.strip()[:2000]}")
    try:
        report = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SystemExit("OSV-Scanner wrote no readable report: " + str(error))
    report["tool"], report["status"] = "osv-scanner", "scanned"
    write_json(output, report)
    blocking = osv_blocking(report)
    if blocking:
        for row in blocking:
            print("osv: " + json.dumps(row, ensure_ascii=False))
        raise SystemExit(f"{len(blocking)} OSV vulnerability finding(s)")
    print(f"osv-scanner: no vulnerabilities in {len(report['results'])} source(s)")
    return 0


def wsl(distribution, script, stdin):
    command = ["wsl.exe", "--distribution", distribution, "--cd", "~", "--exec", "bash", "-c", script]
    return capture(command, input=stdin, env={**os.environ, "WSL_UTF8": "1"})


def semgrep_report(report, args, distribution):
    """Record provenance, write the evidence and fail on blocking findings (shared by the WSL and Windows paths)."""
    report["mookko"] = {"sha": args.sha, "rules": list(SEMGREP_RULES), "version": args.version, "distribution": distribution}
    write_json(args.output, report)
    blocking = semgrep_blocking(report)
    if blocking:
        for row in blocking:
            print("semgrep: " + json.dumps(row, ensure_ascii=False))
        raise SystemExit(f"{len(blocking)} Semgrep {'/'.join(SEMGREP_BLOCKING)} finding(s)")
    print(f"semgrep: {len(report['results'])} finding(s), none at {'/'.join(SEMGREP_BLOCKING)}; "
          f"{len(report['paths']['scanned'])} file(s) scanned, {len(report['errors'])} scanner error(s)")
    return 0


def run_semgrep_windows(args, archive):
    """Native Windows Semgrep (10-25): the pinned launcher (`<pythonPath>/bin/semgrep.exe` from a pip --target install, checksum
    pinned) runs the package from --python-path on an extraction of the exact commit under %TEMP%\\mookko-test\\dev, never
    on the working tree. WSL is not started. (`python -m semgrep` no longer works in this version, so the launcher it is.)"""
    executable = verify_executable(args.executable, getattr(args, "sha256", None), "semgrep")
    python_path = getattr(args, "python_path", None)
    if not python_path or not Path(python_path).is_dir():
        raise SystemExit("Windows Semgrep needs --python-path (the pinned package folder)")
    base = Path(os.environ.get("TEMP") or tempfile.gettempdir()) / "mookko-test" / "dev"
    base.mkdir(parents=True, exist_ok=True)
    # The launcher hands --version/scan to pysemgrep.exe beside it by PATH lookup; the package itself comes from PYTHONPATH.
    # pywin32 (pulled in by semgrep's mcp dependency) spreads over win32/, win32/lib and pythonwin/ and relies on a .pth file
    # that only site-packages would process, so those folders go on PYTHONPATH too; its DLLs sit in pywin32_system32.
    extra = [Path(python_path) / p for p in ("win32", "win32/lib", "pythonwin")]
    environment = {"PYTHONPATH": os.pathsep.join([python_path] + [str(p) for p in extra if p.is_dir()]),
                   "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1", "SEMGREP_SEND_METRICS": "off",
                   "PATH": os.pathsep.join([str(Path(python_path) / "bin")] + [str(Path(python_path) / "pywin32_system32")] * ((Path(python_path) / "pywin32_system32").is_dir())
                                           + [os.environ.get("PATH", "")])}
    with tempfile.TemporaryDirectory(prefix="semgrep-", dir=str(base)) as folder:
        source = Path(folder) / "src"
        source.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
            tar.extractall(source, filter="data")
        version = capture([executable, "--version"], env=environment, text=True, encoding="utf-8", errors="replace")
        found = re.search(r"^\s*(\d+\.\d+\.\d+)\s*$", (version.stdout or "") + "\n" + (version.stderr or ""), re.M)
        actual = found.group(1) if found else ""
        if version.returncode or actual != args.version:
            raise SystemExit("Semgrep version mismatch: " + (actual or ((version.stdout or "") + (version.stderr or "")).strip()[:300]))
        output = Path(folder) / "semgrep.json"
        rules = [part for rule in SEMGREP_RULES for part in ("--config", rule)]
        scan = capture([executable, "scan", *rules, "--json", "--output", str(output), "--metrics=off", "--quiet", "--no-error", "."],
                       cwd=str(source), env=environment, text=True, encoding="utf-8", errors="replace")
        if scan.returncode:
            raise SystemExit(f"Semgrep failed ({scan.returncode}): {(scan.stderr or scan.stdout or '').strip()[:2000]}")
        try:
            report = json.loads(output.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise SystemExit("Semgrep produced unreadable JSON: " + str(error))
    return semgrep_report(report, args, "windows")


def run_semgrep(args):
    if not re.fullmatch(r"[0-9a-f]{40}", args.sha):
        raise SystemExit("Semgrep needs the exact commit SHA")
    archive = capture(["git", "archive", "--format=tar", args.sha], cwd=args.checkout)
    if archive.returncode or not archive.stdout:
        raise SystemExit("git archive failed: " + archive.stderr.decode("utf-8", "replace").strip()[:500])
    if args.distribution == "windows":
        return run_semgrep_windows(args, archive.stdout)
    unpack = wsl(args.distribution, 'set -eu; w=$(mktemp -d /tmp/mookko-semgrep.XXXXXX); mkdir "$w/src"; tar -x -C "$w/src"; printf %s "$w"', archive.stdout)
    work = unpack.stdout.decode("utf-8", "replace").strip()
    if unpack.returncode or not re.fullmatch(r"/tmp/mookko-semgrep\.[A-Za-z0-9]+", work):
        raise SystemExit("Could not stage the commit tree in WSL: " + unpack.stderr.decode("utf-8", "replace").strip()[:500])
    executable, version = shlex.quote(args.executable), shlex.quote(args.version)
    rules = " ".join("--config " + shlex.quote(rule) for rule in SEMGREP_RULES)
    script = (f'set -eu; trap \'rm -rf {shlex.quote(work)}\' EXIT; cd {shlex.quote(work)}/src; '
              f'actual="$({executable} --version 2>/dev/null | tail -n 1)"; '
              f'if [ "$actual" != {version} ]; then echo "Semgrep version mismatch: $actual" >&2; exit 3; fi; '
              f'{executable} scan {rules} --json --output ../semgrep.json --metrics=off --quiet --no-error . >/dev/null; '
              f'cat ../semgrep.json')
    scan = wsl(args.distribution, script, b"")
    if scan.returncode:
        raise SystemExit(f"Semgrep failed ({scan.returncode}): {scan.stderr.decode('utf-8', 'replace').strip()[:2000]}")
    try:
        report = json.loads(scan.stdout.decode("utf-8"))
    except ValueError as error:
        raise SystemExit("Semgrep produced unreadable JSON: " + str(error))
    return semgrep_report(report, args, args.distribution)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Pinned security scanners for MooKKo native validation")
    commands = parser.add_subparsers(dest="scanner", required=True)
    vulnerable = commands.add_parser("vulnerable")
    vulnerable.add_argument("--service", required=True)
    vulnerable.add_argument("--output", required=True)
    vulnerable.add_argument("projects", nargs="*")
    vulnerable.set_defaults(handler=run_vulnerable)
    sbom = commands.add_parser("sbom")
    for name in ("--service", "--executable", "--sha256", "--output"):
        sbom.add_argument(name, required=True)
    sbom.add_argument("projects", nargs="*")
    sbom.set_defaults(handler=run_sbom)
    trivy = commands.add_parser("trivy")
    for name in ("--executable", "--sha256", "--cache-dir", "--output"):
        trivy.add_argument(name, required=True)
    trivy.add_argument("target")
    trivy.set_defaults(handler=run_trivy)
    osv = commands.add_parser("osv")
    for name in ("--executable", "--sha256", "--output"):
        osv.add_argument(name, required=True)
    osv.add_argument("target")
    osv.set_defaults(handler=run_osv)
    semgrep = commands.add_parser("semgrep")
    for name in ("--distribution", "--executable", "--version", "--sha", "--output"):
        semgrep.add_argument(name, required=True)
    semgrep.add_argument("--python-path")   # Windows native Semgrep: the pinned package folder
    semgrep.add_argument("--sha256")        # Windows native Semgrep: checksum of the pinned interpreter
    semgrep.add_argument("checkout")
    semgrep.set_defaults(handler=run_semgrep)
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except ValueError as error:
        raise SystemExit(str(error))


if __name__ == "__main__":
    sys.exit(main())
