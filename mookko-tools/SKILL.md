---
name: mookko-tools
description: MooKKo 도구 규약(Python·Bash). scripts/ 아래 CI·검사·시험 도구 스크립트를 쓰거나 고칠 때 반드시 먼저 읽는다. 실패를 숨기지 않기, utf-8, 목록 인자 subprocess, 경로·주소 하드코딩 금지, 표본으로 검사 시험.
---

# MooKKo 도구 규약 (요약)

정본은 `docs/policy/conventions/tools.md`(규칙 번호 T-*). 도구는 서버에 쓰지 않는다(서버는 Rust만). 하네스 CI가 이 도구를 돌리므로 실패를 숨기지 않는 것이 가장 중요하다.

- Python 3.12+, 표준 라이브러리 우선, `python3 -X utf8`, 파일은 `encoding="utf-8"`.
- 실패는 0이 아닌 종료 코드와 `파일:줄: 이유` 한 줄씩. `except: pass` 금지.
- `subprocess.run([...], check=True)` 목록 인자, `shell=True` 금지.
- 경로는 `Path(__file__).resolve().parents[n]` 기준 상대 경로나 인자. 주소·포트를 코드에 두지 않는다.
- 맨 위 docstring에 무엇을 왜 검사하는지와 근거 문서. 타입 힌트.
- 새 검사는 잡아야 할 표본과 통과시켜야 할 표본으로 시험하고 결과를 커밋 본문에.
- Bash는 `set -euo pipefail`, 따옴표, Linux 기준. 임시 파일은 `mookko-test/<앱>/<실행>` 아래에 만들고 끝나면 지운다.
