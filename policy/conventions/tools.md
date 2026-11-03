# 도구 규약 (Python · Bash)

대상: `scripts/`, 시험·CI 도구. 서버 실행 코드에는 쓰지 않는다(서버는 Rust만). 도구도 하네스 CI가 돌리므로 실패를 숨기지 않는 것이 가장 중요하다.

## Python

- T-PY-1 Python 3.12+, 표준 라이브러리 우선. 바깥 패키지가 필요하면 이유와 함께 고정 버전. **[QA]**
- T-PY-2 실행은 `python3 -X utf8`, 파일은 `encoding="utf-8"`으로 읽고 쓴다. **[QA]**
- T-PY-3 실패는 0이 아닌 종료 코드와 이유 한 줄씩(어느 파일:줄). 예외를 삼키지 않는다(`except: pass` 금지). **[QA]**
- T-PY-4 하위 프로세스는 `subprocess.run([...], check=True)` 목록 인자로(`shell=True` 금지). **[QA]**
- T-PY-5 경로·주소를 코드에 두지 않는다: 저장소 기준 상대 경로(`Path(__file__).resolve().parents[n]`)나 인자·설정. **[QA]**
- T-PY-6 타입 힌트(`from __future__ import annotations`), 함수 하나에 한 가지 일, 맨 위 docstring에 무엇을 왜 검사하는지와 근거 문서. **[QA]**
- T-PY-7 검사 스크립트는 잡아야 할 표본과 통과시켜야 할 표본으로 시험한 뒤 커밋(커밋 본문에 결과). **[QA]**

## Bash

- T-SH-1 맨 위 `set -euo pipefail`, 변수는 따옴표로 감싼다. **[QA]**
- T-SH-2 Linux에서 돈다(제품 검사는 Linux 기준). Windows 전용 명령을 쓰지 않는다. **[QA]**
- T-SH-3 임시 파일은 `%TEMP%\mookko-test\<앱>\<실행>`(Linux는 `$TMPDIR/mookko-test/...`)에 만들고 끝나면 지운다. Linux에서 바로 지우는 것은 그 실행이 직접 만든 폴더 하나뿐이고, 시험이 실패하면 원인 확인용으로 남긴다(Bash는 종료 코드, Rust `Drop`은 `std::thread::panicking()`으로 가림). **[검사]** `check-test-tempdirs.py`(Rust `temp_dir()` 뒤 첫 `.join("mookko-test")`, 지우는 `Drop`의 실패 시 남기기, Bash `rm -r` 대상이 mookko-test 아래 변수인지)
