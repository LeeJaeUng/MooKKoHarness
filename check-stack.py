"""스택 강제 검사 (AGENTS.md, docs/policy/gates.md, 하네스 docs/design.md › 강제하는 것).

1. 공용 엔진 우회 금지: 서비스 crate(crates/services/*)는 HTTP 서버·HTTP 클라이언트·DB 드라이버·gRPC·캐시
   클라이언트 crate를 직접 의존하지 않는다. 그런 기능은 엔진 포트로만 쓴다(사용자 결정: 모든 앱이 엔진 하나를 공유).
2. 화면 스택: 화면 코드는 web/ 안에만, React + TypeScript + Tailwind CSS, pnpm만. 다른 화면·CSS 프레임워크와
   npm/yarn/bun lock 파일 금지. Next.js는 공개 SEO 화면 앱(web/apps/public*)에서만.
3. 이름: crate·실행 파일 이름에 "rust"를 붙이지 않는다(사용자 지시: 이름은 MooKKo).

cargo metadata로 판정하므로 PATH에 cargo가 있어야 한다.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 서비스가 직접 쓰면 안 되는 crate(엔진 포트를 거쳐야 함).
ENGINE_ONLY_CRATES = {
    "axum", "axum-core", "hyper", "hyper-util", "tower-http", "actix-web", "warp", "rocket", "poem", "salvo",
    "reqwest", "ureq", "isahc", "surf",
    "sqlx", "tokio-postgres", "postgres", "deadpool-postgres", "bb8-postgres", "diesel", "diesel-async", "sea-orm",
    "rusqlite", "libsql",
    "tonic", "tonic-web", "prost",
    "redis", "fred", "deadpool-redis",
    "rdkafka", "lapin",
}

# web/ 패키지에서 금지하는 의존성(이름 또는 접두어).
BANNED_WEB = {
    "vue", "nuxt", "svelte", "@sveltejs/", "@angular/", "jquery", "solid-js", "preact", "lit", "ember-source",
    "bootstrap", "bulma", "foundation-sites", "@mui/", "@chakra-ui/", "antd", "styled-components", "@emotion/",
}
FOREIGN_LOCKS = {"package-lock.json", "yarn.lock", "bun.lockb", "bun.lock", "npm-shrinkwrap.json"}
UI_SUFFIXES = {".tsx", ".jsx", ".vue", ".svelte", ".html", ".css", ".scss"}
SKIP_DIRS = {".git", "target", "node_modules", ".claude", "data", "dist"}


def walk(base: Path):
    """base 아래 폴더·파일(SKIP_DIRS에는 들어가지 않음). rglob은 건너뛸 폴더(.claude/worktrees 등)도 다 훑은 뒤 걸러서
    /mnt/c 위에서 메모리가 모자랄 수 있습니다(2026-11-01 check-systemd-units ENOMEM과 같은 원인)."""
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        here = Path(dirpath)
        for name in [*dirnames, *filenames]:
            path = here / name
            yield path, path.relative_to(ROOT)


def cargo_packages() -> list[dict]:
    out = subprocess.run(
        ["cargo", "metadata", "--format-version", "1", "--no-deps", "--locked"],
        cwd=ROOT, check=True, capture_output=True, text=True, encoding="utf-8",
    ).stdout
    return json.loads(out)["packages"]


def check_engine_bypass(packages: list[dict], problems: list[str]) -> None:
    for pkg in packages:
        rel = Path(pkg["manifest_path"]).resolve().relative_to(ROOT).as_posix()
        if not rel.startswith("crates/services/"):
            continue
        for dep in pkg["dependencies"]:
            if dep["name"] in ENGINE_ONLY_CRATES:
                problems.append(f"{pkg['name']}: service depends on `{dep['name']}` directly — use engine ports")


def check_names(packages: list[dict], problems: list[str]) -> None:
    for pkg in packages:
        names = {pkg["name"]} | {t["name"] for t in pkg["targets"]}
        for name in names:
            if "rust" in name.lower():
                problems.append(f"{pkg['name']}: name `{name}` contains 'rust' — names are MooKKo/mookko-*")


def banned(dep: str) -> bool:
    return any(dep == b or (b.endswith("/") and dep.startswith(b)) for b in BANNED_WEB)


def check_web(problems: list[str]) -> None:
    web = ROOT / "web"
    for path, rel in walk(ROOT):
        if not path.is_file():
            continue
        top = rel.parts[0]
        if path.name in FOREIGN_LOCKS:
            problems.append(f"{rel.as_posix()}: only pnpm is allowed (pnpm-lock.yaml)")
        if top != "web" and (path.suffix in UI_SUFFIXES or path.name == "package.json"):
            if top in {"docs", "acceptance"} and path.suffix == ".html":
                continue
            problems.append(f"{rel.as_posix()}: screen/frontend files belong under web/")
    if not web.exists():
        return
    for path, rel in walk(web):
        if path.name != "package.json":
            continue
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            problems.append(f"{rel.as_posix()}: invalid JSON ({e})")
            continue
        deps = {**manifest.get("dependencies", {}), **manifest.get("devDependencies", {})}
        for dep, version in deps.items():
            if banned(dep):
                problems.append(f"{rel.as_posix()}: `{dep}` is not allowed (React + TypeScript + Tailwind only)")
            if isinstance(version, str) and version.startswith(("git", "http", "file:", "link:")):
                problems.append(f"{rel.as_posix()}: `{dep}` must come from the npm registry (got {version})")
        if "next" in deps and not rel.as_posix().startswith("web/apps/public"):
            problems.append(f"{rel.as_posix()}: Next.js is only for public SEO apps (web/apps/public*)")
    if not (web / "pnpm-lock.yaml").exists() and any(web.rglob("package.json")):
        problems.append("web/: pnpm-lock.yaml is required")


def main() -> int:
    problems: list[str] = []
    packages = cargo_packages()
    check_engine_bypass(packages, problems)
    check_names(packages, problems)
    check_web(problems)
    if problems:
        print("stack check failed:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"stack check passed ({len(packages)} crates, web/ {'present' if (ROOT / 'web').exists() else 'absent'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
