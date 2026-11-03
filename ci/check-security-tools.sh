#!/usr/bin/env bash
# 보안 도구 관문(docs/architecture/host-security.md §6, H-5). check-all에서 돕니다.
#   1) 도구 판 고정: config/dev/security-tools.json의 설치 위치에 있는 실행 파일만 쓰고, SHA256이 다르면 멈춥니다.
#   2) 작업 트리 사본: git이 올리는 파일(추적 + 무시되지 않은 새 파일)만 $TMPDIR/mookko-test/rustdev/<실행>/src에 복사해 봅니다.
#      data/·.claude/ 같은 로컬 파일과 빌드 캐시는 보지 않습니다.
#   3) gitleaks(비밀값, 예외는 docs/policy/gitleaks.toml(제품)) · OSV-Scanner(lock 파일 취약점) ·
#      Trivy(취약점·설정 오류·비밀값, HIGH 이상) · cargo-cyclonedx(SBOM이 패키지마다 만들어지는지)
# 사본 폴더는 이 실행이 만든 것만 성공하면 바로 지우고, 실패하면 원인 확인용으로 남깁니다(CLAUDE.md › WSL 시험 임시 폴더 예외).
set -euo pipefail

H="$(cd "$(dirname "$0")/.." && pwd)"  # 하네스 저장소 최상위
if [ -z "${MOOKKO_PRODUCT_ROOT:-}" ]; then
    echo "MOOKKO_PRODUCT_ROOT(검사할 제품 저장소)가 없습니다. 제품의 ci/check-all.sh(harness.lock 판)로 부르세요" >&2
    exit 2
fi
cd "$MOOKKO_PRODUCT_ROOT"
ROOT="$PWD"
MANIFEST="$H/config/dev/security-tools.json"

# 1) 판·해시 확인 뒤 도구 경로를 받습니다(PATH에서 찾지 않음).
declare -A TOOL
while IFS='=' read -r name path; do
    TOOL[$name]="$path"
done < <(python3 -I -X utf8 - "$MANIFEST" <<'PY'
import hashlib, json, os, sys
manifest = json.load(open(sys.argv[1], encoding="utf-8"))
root = os.path.expanduser(manifest["installRoot"])
bad = []
for t in manifest["tools"]:
    path = os.path.join(root, f"{t['name']}-{t['version']}", t["binary"])
    if not os.path.isfile(path):
        bad.append(f"{t['name']} {t['version']}: 설치되지 않음 ({path}). README › 보안 도구 설치를 보세요")
        continue
    digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
    if digest != t["binarySha256"]:
        bad.append(f"{t['name']} {t['version']}: 실행 파일 SHA256 {digest}이 고정값 {t['binarySha256']}과 다름 ({path})")
        continue
    print(f"{t['name']}={path}")
for b in bad:
    print(f"security-tools.json: {b}", file=sys.stderr)
sys.exit(1 if bad else 0)
PY
)
for name in gitleaks trivy osv-scanner cargo-cyclonedx; do
    if [ -z "${TOOL[$name]:-}" ]; then
        echo "보안 도구 $name을 쓸 수 없습니다(위 메시지). 관문을 멈춥니다." >&2
        exit 1
    fi
done

# 2) 작업 트리 사본
RUN_ROOT="${TMPDIR:-/tmp}/mookko-test/rustdev"
RUN_DIR="$RUN_ROOT/security-$(date +%Y%m%d%H%M%S)-$$"
RUN_DIR_MADE=""
cleanup() {
    local status=$?
    if [ -z "$RUN_DIR_MADE" ]; then
        return
    fi
    if [ "$status" -ne 0 ]; then
        echo "FAILED (exit $status): security gate folder kept for diagnosis: $RUN_DIR" >&2
        return
    fi
    rm -rf -- "$RUN_DIR"
}
trap cleanup EXIT
mkdir -p "$RUN_ROOT"
mkdir -m 700 "$RUN_DIR"
RUN_DIR_MADE=1
SRC="$RUN_DIR/src"
mkdir "$SRC"
# 작업 트리에서 지운(아직 커밋 안 한) 추적 파일은 건너뜁니다.
git ls-files -z -co --exclude-standard \
    | python3 -I -c 'import os,sys; sys.stdout.buffer.write(b"".join(p+b"\0" for p in sys.stdin.buffer.read().split(b"\0") if p and os.path.isfile(p)))' \
    | tar --null -T - -cf - | tar -xf - -C "$SRC"
cd "$SRC"

# 도구가 스스로 찾아 읽는 예외 파일은 옆길이라 두지 않습니다(QA 6b8bdab T3). 예외는 docs/policy/gitleaks.toml(제품) 하나뿐입니다.
side_doors="$(find . -type f \( -name .gitleaksignore -o -name '.trivyignore*' -o -name 'trivy.yaml' -o -name 'trivy.yml' \
    -o -name 'osv-scanner.toml' \) -print)"
if [ -n "$side_doors" ]; then
    echo "보안 도구 예외 파일은 두지 않습니다. 예외는 docs/policy/gitleaks.toml(제품)에 사유와 함께 적으세요:" >&2
    printf '%s\n' "$side_doors" >&2
    exit 1
fi

echo "-- gitleaks"
# 코드 안 gitleaks:allow 주석도 예외 옆길이라 무시합니다.
"${TOOL[gitleaks]}" dir . --config "$ROOT/docs/policy/gitleaks.toml" --ignore-gitleaks-allow --no-banner --redact \
    --exit-code 1 --log-level warn

echo "-- osv-scanner"
"${TOOL[osv-scanner]}" scan source --recursive --format table .

echo "-- trivy"
"${TOOL[trivy]}" fs --quiet --scanners vuln,misconfig,secret --severity HIGH,CRITICAL --ignorefile "" --exit-code 1 .

echo "-- cargo-cyclonedx"
"${TOOL[cargo-cyclonedx]}" cyclonedx -q --format json --all-features --spec-version 1.5
python3 -I -X utf8 - <<'PY'
import json, pathlib, subprocess, sys
meta = json.loads(subprocess.run(["cargo", "metadata", "--no-deps", "--format-version", "1", "--locked"],
                                 check=True, capture_output=True, text=True, encoding="utf-8").stdout)
missing, empty = [], []
for pkg in meta["packages"]:
    bom = pathlib.Path(pkg["manifest_path"]).parent / f"{pkg['name']}.cdx.json"
    if not bom.is_file():
        missing.append(pkg["name"])
        continue
    doc = json.loads(bom.read_text(encoding="utf-8"))
    if doc.get("bomFormat") != "CycloneDX" or "metadata" not in doc:
        empty.append(pkg["name"])
for name in missing:
    print(f"SBOM이 만들어지지 않음: {name}", file=sys.stderr)
for name in empty:
    print(f"SBOM 형식이 아님: {name}", file=sys.stderr)
if missing or empty:
    sys.exit(1)
print(f"SBOM {len(meta['packages'])}개(CycloneDX 1.5) 확인")
PY
echo "security tools gate passed"
