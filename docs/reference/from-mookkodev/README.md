# C# 하네스 MooKKoDev에서 넘겨받은 규칙

2026-10-30 사용자 결정으로 C# 하네스 MooKKoDev를 철거하기 전에, 철거 담당이 쓸 만한 규칙을 넘겼습니다. 원본은 MooKKoDev 커밋 daf975d(GitHub LeeJaeUng/MooKKoCLI)이고, 여기 파일은 그대로 옮긴 사본입니다. Windows·OpenRig·.NET 전용 내용(실행 파일 경로, `dotnet` 도구 허용, rig 명령)은 참고로만 읽고, Rust 하네스에서는 Linux·AI 매니저·HTTP 방식으로 다시 만듭니다.

| 파일 | 무엇 | Rust 하네스에서 쓰는 곳 |
|---|---|---|
| `security-tools-manifest.json` | 보안 검사 도구(gitleaks 8.30.1, trivy 0.75.0, osv-scanner 2.6.0, semgrep 1.182.1, cyclonedx 6.3.1)를 판·공식 출처·체크섬으로 고정하는 방식 | H2 강제 검사. Linux판을 같은 판으로 다시 받아 공식 체크섬과 대조합니다(내려받기는 사용자 승인 뒤). gitleaks 옵션과 "없으면 push 보류"는 `mookkodev-readme-excerpts.md` 보안 경계 절 |
| `qa-judge.md`, `service-qa.json`(`qa` 칸) | QA 판정 기준: 관문 통과 + 90점 이상 + 미해결 0, 최대 3회차, 같은 지적 2번·점수 정체 2번이면 멈추고 판단 담당에게, 기준을 낮추는 선택은 없음 | H5 QA·반영. 지금은 QA 보류·Claude만(2026-10-29 사용자 결정)이라 판정 숫자는 다시 시작할 때 적용 |
| `mookkodev-readme-excerpts.md` › 결과가 사라지지 않게 | AI 답 뒤의 처리: developerChecks, plan 등급(light·normal·important), 관문 cycle 고정 | H4 워커 한 턴·H5 |
| `validation-store.md` | 검증 실행의 작업 사본·근거·실행 잠금(run.lock)과 보관 기한(실패 24시간, 근거 30일), 실행 중인 것은 건드리지 않기 | H2·H5 검증 실행. 2026-10-30 규칙에 맞춰 바꿈: 캐시는 24시간 넘은 것만 지우고, 시험 임시·근거는 휴지통 규칙 |
| 같은 파일 › 일감 전달 규칙, 긴급 멈춤 | 전달 규칙, PAUSED, 시작 실패 재시도 30초~10분 | H3 담당·일감 |
| `recovery.md`, 같은 파일 › 막힘 정리·막힘 복구 워커 | 막힌 일감의 공통 원인을 찾아 묶어 고치기(연쇄 보류 묶기), 권한·금지 행동 | H3·H4 |
| 같은 파일 › 공용 규칙과 검사 기준 | 공용 규칙 묶음을 커밋에 고정하고 원문 해시·파일 목록 확인 | H2(제품 `docs/policy/`를 후보 커밋 기준으로 고정) |
| 같은 파일 › 정기 점검 | 일일·주간·월간 점검 | H3 이후 |
| `status-contract.md`, `status-contract.json` | 일감·워커·승인·서버 상태·작업 결과의 상태 정의 정본(저장 상태와 표시 상태 분리, 미정의 값은 '상태 미확인', 정의 버전·지문 전달) | H3 일감 상태 API·SSE. 화면은 없으므로 API 계약으로 씀 |

넘겨받지 않은 것: OpenRig 실행 모드와 `rules/openrig/`(철거 대상), 이미 이 저장소에 있는 `docs/reference/windows-runtime.md`·`worker-isolation-plan.md`·`rules/`·`tools/security_tools.py`.
