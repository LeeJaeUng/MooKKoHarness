# 바탕 담당 (3단계)

서비스들이 함께 쓰는 바탕 crate를 `crates/`에 만듭니다: axum(HTTP), tonic(gRPC), sqlx(PostgreSQL, 컴파일 시 쿼리 검사), tracing/OpenTelemetry(관측), 설정·비밀값 읽기, 오류 형식, 기한·재시도·동시 실행 상한.

- 목표 구조: 서비스 11개를 프로세스 1~2개로 묶습니다(서비스는 라이브러리 crate, 실행 파일이 묶음). 서비스 경계는 crate 경계와 공개 API로 지킵니다.
- 설계는 `docs/architecture/`에 먼저 적고(메모리 예산·프로세스 구성·장애 격리), 명세(`docs/spec/`)와 인수 시험(`acceptance/`)의 계약을 따릅니다.
- 의존성은 DEPS-01을 따릅니다. TLS는 rustls. C 컴파일러가 필요한 crate(ring·aws-lc 등)는 지금 PC에 Windows SDK가 없어 빌드되지 않을 수 있으니, 막히면 보고서에 그대로 적습니다(사용자 몫).
- 리드는 설계·검토·작업 나누기, backend는 구현을 맡습니다. 다 쓴 커밋은 `foundation/qa`에 검사를 요청합니다.
