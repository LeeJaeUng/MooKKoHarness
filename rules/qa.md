# QA 담당 (분야별 독립 검사)

- 분야별 QA 세션(qa-design·qa-engine·qa-services·rust-qa)이 맡습니다. 당분간 개발과 QA 모두 Claude이며(사용자 2026-10-29), 결과마다 `엔진: Claude(모델명)`을 적습니다. 빌드·시험(check-all)은 rust-qa 한 세션만 돌립니다.
- 정확한 후보 커밋(`commit:` 태그)을 검사합니다. MooKKo `docs/policy/gates.md`(정본 하네스 `policy/gates.md`)의 자기 분야 관문을 `verification.gates`에 하나씩 판정합니다. 적용되는 관문은 `na`가 될 수 없고, `pass`에는 그 관문 경로 안의 파일·줄 근거가 필요합니다.
- 명세 검사(SPEC-01)는 관문에 적힌 근거(예전 C# 사본 경로:줄 또는 새 설계 근거 문서)를 표본이 아니라 항목마다 직접 열어 확인합니다. 빠진 기능·계약·스키마가 있으면 `fail`입니다. 스키마를 바꾸는 설계서는 qa-design의 `design:approved`(DBDES-01) 뒤에만 통합합니다.
- 결과는 요청한 개발 담당과 통합 담당에게 보냅니다(문제·부족·추가하면 좋은 것). 통과·실패 모두 근거를 적습니다. 쓰기 권한이 없으므로 고치지 않습니다.
