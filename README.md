# MooKKoDev 하네스 (Rust 판)

공통 안내: `C:\Project\MooKKo\CLAUDE.md` · AI 매니저: `http://127.0.0.1:5290` (연동 안내 `C:\Project\MooKKo\MooKKoAIManager\docs\연동-안내.md`)

MooKKo 제품(Rust 판)을 만드는 AI 워커를 관리하는 하네스입니다. **개발될 서비스들이 정해진 방식(공용 엔진, 모듈화, JSON 설정, React·TS·Tailwind 화면, Linux 빌드)대로만 개발되도록 강하게 잡는 것**이 역할입니다(`docs/design.md` › 강제하는 것). 담당·일감을 나누고, AI 매니저에서 자리를 빌려 워커를 돌리고, 다른 엔진의 QA와 CI를 통과한 커밋만 제품 `main`에 반영합니다. 2026-10-29 사용자 결정으로 MooKKoDev C# 복사판을 버리고 **Rust로 새로** 만듭니다. 이름에 Rust를 붙이지 않습니다.

- 설계: `docs/design.md` (역할, 강제하는 것, 구조, 운영 교훈, 단계 H1~H5, 정해야 할 것)
- 운영 교훈 근거: `docs/reference/` (MooKKoDev C# 실행부 문서)
- 담당 규칙(워커에게 넘김): `rules/` · 담당 구성 초안: `defaults/roles.json`
- CI 도구: `tools/validate-rust.py`(제품 후보 커밋 검사), `tools/export-policy.py`(제품 관문 정책 내보내기), `tools/security_tools.py`

| 항목 | 값 |
|---|---|
| 허브 앱 id | `rustdev` (포트는 허브 `GET /v1/ports/rustdev`) |
| 서버 | Rust(axum, tokio). API와 실시간 알림(SSE)만, 화면 없음 |
| 실행 데이터 | `data\` (git 제외): `runtime\`(설정·토큰·상태), `tools\`(검사 도구), `reference\`(C# 판 읽기 전용 사본), `legacy-csharp-copy\`(버린 C# 복사판, 참고용) |

## 남은 것 (10-29)

- AI 매니저 승인(사용자): 프로그램 `prg_da8511696f19b9a2`, 매니저 화면 **프로그램** 탭.
- 제품 GitHub 원격(사용자): 없으면 main 반영이 실패합니다.
- 호스트 검사 도구(Trivy·OSV-Scanner·Semgrep)를 `data\tools`에: 없으면 QA 영수증이 없습니다.
- `docs/design.md` › 정해야 할 것: 하네스 실행 위치, 워커 격리 위치.
