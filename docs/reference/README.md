# 옛 판 기록 (경로·명령은 쓰지 않음)

**옛 판입니다. 안의 경로·명령·설정은 쓰지 않습니다.** 예전 C# 하네스 MooKKoDev(2026-10-30 철거)와 Windows 실행부의 기록입니다. 운영 교훈을 찾을 때만 읽습니다. 지금 기준은 `docs/design.md`에 있습니다.

- `from-mookkodev/`: MooKKoDev가 넘긴 규칙 사본. 보안 도구 목록의 경로·`LOCALAPPDATA`는 그때 Windows 값입니다. 지금 목록은 `config/dev/security-tools.json`입니다.
- `legacy-tools/`: C# 실행부(QA 영수증)가 부르던 Python 도구(`validate-rust.py`·`export-policy.py`·`security_tools.py`). 지금 검사는 `ci/`입니다.
- `windows-runtime.md`, `worker-isolation-plan.md`: Windows 실행 구조와 워커 격리 계획. 격리는 Linux 컨테이너로 다시 정합니다(`docs/design.md` › 정해야 할 것).
