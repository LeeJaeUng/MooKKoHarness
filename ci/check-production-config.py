"""운영 설정 검사 (SEC-01, qa-engine 2026-11-03 QE-SEC-2·QE-SEC-3·QE-SEC-4·A1·A2, QAManager 요청 6번; 근거 docs/policy/gates.md SEC-01,
docs/architecture/config-catalog.md, docs/coordination/engine-priority.md "qa-engine 관문 판정").

운영(라이브) 설정이 개발용 값으로 나가지 않게 막는다. 대상: 저장소 안 *.json 가운데 `app.environment`가 "production"인 것과
`overlays/live/` 아래 파일(설정 저장소의 라이브 덮어쓰기). 지금은 운영 설정이 저장소에 없으므로 0건이면 통과하고, 생기는
순간부터 막는다. 규칙(값이 있을 때 본다. 칸 이름은 엔진 설정 형의 JSON 이름):
- 비밀·키: `keyVault.kind`가 "file"이면 실패(KMS 감싼 키만, QE-SEC-2). `signer.kind`가 "file"이면 실패(KMS 서명, A3).
- 직원 세션: `staffSessions.absoluteLifetimeMs` ≤ 12시간, `idleTimeoutMs` ≤ 15분(QE-SEC-4). `staffLogin.kind`가 "devLocal"이면 실패.
  직원 로그인·신원 설정이 있으면 `requireMfa: true`(QE-SEC-3).
- RPC: `rpc.server`가 있으면 `staffRecentMfa`가 있어야 함(XC-MFA-3, 없으면 requires_recent_mfa가 강제되지 않음).
- 직원 대리 정보 받는 곳(aud, 보안 담당 2026-11-14 S-8 ③ 결정, security.md §4.1): `rpc.server.peers[]`에 `actorSigningKeys`가 있으면
  `rpc.server.staffAudience`가 있어야 하고, `adapters.actorSigner.kind`가 "none"이 아니면(직원 대리 호출을 보냄) `rpc.clients.targets[]`마다
  `staffAudience`가 있어야 함. 값은 `<환경>.<서비스>` 꼴(소문자·숫자·`._-`, 점 하나 이상, 1~64자). 엔진은 선택·경고, 운영 설정에서 필수.
- 평문: `allowPlainHttp: true` 실패, DB·ClickHouse `tls.mode`가 "disable"·"require"면 실패(검증 없는 TLS, A2).
- 로컬 파일 객체 저장소(`objects.kind: "file"`) 실패(컨테이너를 바꾸면 사라짐).
실패하면 `파일:1: 칸 경로: 이유`를 한 줄씩 내고 1로 끝난다.

사용: python3 -X utf8 ci/check-production-config.py [저장소 루트]
"""

from __future__ import annotations

import os
import json
import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", "target", "node_modules", ".claude", "data", "dist", "fixtures"}
MAX_ABSOLUTE_MS = 12 * 60 * 60 * 1000  # 직원 세션 절대 만료 상한 12시간(QE-SEC-4, L3 기준)
MAX_IDLE_MS = 15 * 60 * 1000  # 직원 세션 유휴 만료 상한 15분(QE-SEC-4)
STAFF_AUDIENCE = re.compile(r"^(?=.{1,64}$)[a-z0-9_-]+\.[a-z0-9._-]+$")  # `<환경>.<서비스>`(보안 S-8 ③, 엔진 is_audience보다 좁게)


def walk(value: object, path: str = ""):
    """(점으로 이은 칸 경로, 마지막 키, 값)을 모두."""
    if isinstance(value, dict):
        for key, child in value.items():
            here = f"{path}.{key}" if path else key
            yield here, key, child
            yield from walk(child, here)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from walk(child, f"{path}[{i}]")


def is_production(rel: str, data: object) -> bool:
    if "/overlays/live/" in f"/{rel}":
        return True
    return isinstance(data, dict) and isinstance(data.get("app"), dict) and data["app"].get("environment") == "production"


def check(rel: str, data: object, problems: list[str]) -> None:
    def bad(path: str, why: str) -> None:
        problems.append(f"{rel}:1: {path}: {why}")

    has_staff_login = False
    for path, key, value in walk(data):
        parent = path.rsplit(".", 1)[0] if "." in path else ""
        if key == "kind" and parent.endswith("keyVault") and value == "file":
            bad(path, "운영에서 파일 KEK를 쓰지 않습니다(KMS 감싼 키, QE-SEC-2)")
        if key == "kind" and parent.endswith("signer") and value == "file":
            bad(path, "운영에서 파일 서명 키를 쓰지 않습니다(KMS 서명, A3)")
        if key == "kind" and parent.endswith("staffLogin"):
            has_staff_login = True
            if value == "devLocal":
                bad(path, "운영에서 개발용 직원 로그인을 쓰지 않습니다")
        if key == "kind" and parent.endswith("objects") and value == "file":
            bad(path, "운영에서 로컬 파일 객체 저장소를 쓰지 않습니다(운영용 객체 저장소 어댑터)")
        if key == "absoluteLifetimeMs" and parent.endswith("staffSessions") and isinstance(value, int) and value > MAX_ABSOLUTE_MS:
            bad(path, f"{value}ms는 12시간을 넘습니다(QE-SEC-4)")
        if key == "idleTimeoutMs" and parent.endswith("staffSessions") and isinstance(value, int) and value > MAX_IDLE_MS:
            bad(path, f"{value}ms는 15분을 넘습니다(QE-SEC-4)")
        if key == "allowPlainHttp" and value is True:
            bad(path, "운영에서 평문 HTTP를 허용하지 않습니다")
        if key == "mode" and parent.endswith("tls") and value in ("disable", "require"):
            bad(path, f"tls.mode {value}는 운영에서 쓰지 않습니다(인증서 검증, A2)")
        if key == "requireMfa" and value is not True:
            WARNINGS.append(f"{rel}:1: {path}: 직원 로그인은 MFA가 필수입니다(QE-SEC-3, 엔진에 칸이 생길 때까지 경고)")
        if key == "server" and parent.endswith("rpc") and isinstance(value, dict) and "staffRecentMfa" not in value:
            bad(path, "staffRecentMfa가 없으면 requires_recent_mfa 메서드가 강제되지 않습니다(XC-MFA-3)")
    staff_audience_checks(data, bad)
    if has_staff_login and not any(key == "requireMfa" for _, key, _ in walk(data)):
        # 엔진 설정은 deny_unknown_fields인데 엔진에 requireMfa 칸이 아직 없어(QE-SEC-3 엔진 몫), 실패로 두면 검사와 엔진을 함께
        # 만족할 수 없음(mookko-rust-qa·qa-engine 11-04). 엔진에 칸이 생기면 다시 실패로.
        WARNINGS.append(f"{rel}:1: staffLogin: requireMfa: true가 없습니다(QE-SEC-3, 엔진에 칸이 생길 때까지 경고)")


def staff_audience_checks(data: object, bad) -> None:
    """직원 대리 정보의 받는 곳(aud)을 운영 설정에서 필수로(보안 담당 2026-11-14). 칸 이름은 엔진 RpcServerConfig·RpcTargetConfig·
    런타임 adapters.actorSigner의 JSON 이름."""
    if not isinstance(data, dict):
        return
    rpc = data.get("rpc") if isinstance(data.get("rpc"), dict) else {}
    server = rpc.get("server") if isinstance(rpc.get("server"), dict) else None
    if server is not None:
        peers = server.get("peers") if isinstance(server.get("peers"), list) else []
        if any(isinstance(peer, dict) and peer.get("actorSigningKeys") for peer in peers):
            value = server.get("staffAudience")
            if value is None:
                bad("rpc.server.staffAudience", "peers에 actorSigningKeys가 있으면 받는 곳 이름이 있어야 합니다(다른 환경 앞 직원 정보를 막음, 보안 S-8 ③)")
            elif not (isinstance(value, str) and STAFF_AUDIENCE.match(value)):
                bad("rpc.server.staffAudience", f"{value!r}는 `<환경>.<서비스>` 꼴(소문자·숫자·`._-`, 1~64자)이어야 합니다")
    adapters = data.get("adapters") if isinstance(data.get("adapters"), dict) else {}
    signer = adapters.get("actorSigner")
    sends_actor = isinstance(signer, dict) and signer.get("kind") not in (None, "none")
    clients = rpc.get("clients") if isinstance(rpc.get("clients"), dict) else {}
    targets = clients.get("targets") if isinstance(clients.get("targets"), list) else []
    if sends_actor:
        for i, target in enumerate(targets):
            if not isinstance(target, dict):
                continue
            value = target.get("staffAudience")
            path = f"rpc.clients.targets[{i}].staffAudience"
            if value is None:
                bad(path, f"직원 대리 호출을 보내는 설정(adapters.actorSigner)인데 대상 {target.get('service')!r}에 받는 곳 이름이 없습니다(보안 S-8 ③)")
            elif not (isinstance(value, str) and STAFF_AUDIENCE.match(value)):
                bad(path, f"{value!r}는 `<환경>.<서비스>` 꼴(소문자·숫자·`._-`, 1~64자)이어야 합니다")


WARNINGS: list[str] = []  # 엔진에 칸이 없어 아직 경고로 두는 규칙(QE-SEC-3)


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(os.environ.get("MOOKKO_PRODUCT_ROOT") or ".").resolve()
    problems: list[str] = []
    checked = 0
    for path in sorted(root.rglob("*.json")):
        rel = path.relative_to(root).as_posix()
        if any(p in SKIP_DIRS for p in Path(rel).parts):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue  # JSON이 아니거나 다른 검사가 볼 파일
        if not is_production(rel, data):
            continue
        checked += 1
        check(rel, data, problems)
    for p in problems:
        print(p)
    for w in WARNINGS:
        print(f"경고: {w}")
    if problems:
        print(f"production config check failed ({len(problems)} problems)")
        return 1
    print(f"production config check passed ({checked} production configs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
