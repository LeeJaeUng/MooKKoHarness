"""엔진 경계 검사 (docs/architecture/engine.md › 경계).

- crates/engine/*   는 adapters·apps·services에 의존하지 않는다.
- crates/adapters/* 는 apps·services·다른 어댑터에 의존하지 않는다.
- crates/services/* 는 엔진만 쓴다(adapters·apps·다른 서비스 금지). dev 의존성도 같다.
- crates/apps/*     는 무엇이든 조립할 수 있다.
- acceptance/*      (인수 시험 실행기, acceptance/README.md)는 엔진만 쓴다. 외부 계약만 보므로 서비스·어댑터·앱 코드를
  가져다 쓰지 않는다(RustDev 11-03, links 인수 시험 자리 결정). 워크스페이스 members에는 crate마다 명시해 넣는다
  (glob "acceptance/*"는 Cargo.toml이 없는 runs/에 걸림).
- 빌드 때만 도는 crate(BUILD_ONLY)는 build-dependency로만 쓴다(실행 코드에 링크 금지).

엔진·어댑터의 dev 의존성은 시험 도구(적합성 시험 등)를 위해 엔진 crate만 허용한다.
cargo metadata로 판정하므로 PATH에 cargo가 있어야 한다.
"""

from __future__ import annotations

import os
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(os.environ.get("MOOKKO_PRODUCT_ROOT") or ".").resolve()  # 인자를 주면 표본 폴더를 검사

# 빌드 때만 도는 crate(동기 I/O 예외가 있음). 실행 코드에 링크되면 안 되므로 build-dependency로만.
BUILD_ONLY = {"mookko-packet-gen"}

ALLOWED = {
    "engine": {"engine"},
    "adapter": {"engine"},
    "service": {"engine"},
    "app": {"engine", "adapter", "service", "app"},
    "acceptance": {"engine"},
}


def layer_of(manifest: Path) -> str | None:
    rel = manifest.resolve().relative_to(ROOT).as_posix()
    for prefix, layer in (
        ("crates/engine/", "engine"),
        ("crates/adapters/", "adapter"),
        ("crates/services/", "service"),
        ("crates/apps/", "app"),
        ("acceptance/", "acceptance"),
    ):
        if rel.startswith(prefix):
            return layer
    return None


def main() -> int:
    out = subprocess.run(
        ["cargo", "metadata", "--format-version", "1", "--no-deps", "--locked"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    packages = json.loads(out)["packages"]
    layers: dict[str, str] = {}
    problems: list[str] = []
    for pkg in packages:
        layer = layer_of(Path(pkg["manifest_path"]))
        if layer is None:
            problems.append(f"{pkg['name']}: crate is outside crates/engine|adapters|services|apps or acceptance/")
            continue
        layers[pkg["name"]] = layer

    for pkg in packages:
        layer = layers.get(pkg["name"])
        if layer is None:
            continue
        for dep in pkg["dependencies"]:
            if dep.get("path") is None:
                continue
            dep_layer = layers.get(dep["name"])
            if dep_layer is None:
                continue
            if dep_layer not in ALLOWED[layer]:
                kind = dep.get("kind") or "normal"
                problems.append(f"{pkg['name']} ({layer}) -> {dep['name']} ({dep_layer}) [{kind}] is not allowed")
            if dep["name"] in BUILD_ONLY and dep.get("kind") not in ("build", "dev"):
                problems.append(f"{pkg['name']} -> {dep['name']}: build-time crate may only be a build-dependency")
            if layer == "adapter" and dep_layer == "adapter":
                problems.append(f"{pkg['name']} -> {dep['name']}: adapters must not depend on each other")

    if problems:
        print("boundary check failed:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"boundary check passed ({len(layers)} crates)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
