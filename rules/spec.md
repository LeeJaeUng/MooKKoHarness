# 명세 담당 (2단계)

서비스별 명세를 씁니다. C# 판(나중에 삭제)은 기능을 파악하는 참고로만 읽고, 더 나은 설계가 있으면 새로 설계합니다. 형식은 MooKKo `docs/plan.md` › 명세 형식, 판정은 `docs/policy/gates.md` › SPEC-01입니다.

- 근거: C# 판에서 가져온 것은 C# 읽기 전용 사본의 상대 경로:줄(사본 커밋은 `.runtime/context/reference.md`), 새로 설계한 것은 "새 설계"와 이유. 근거 없는 추측은 `open-questions.md`로 보냅니다.
- 서비스마다 `docs/spec/<서비스>/`에 README·features·api·data-model·money·security·open-questions를 둡니다. gRPC 계약은 `proto/mookko/<서비스>/v1/`에 Protobuf 규약대로 새로 씁니다(C# `.proto`는 참고만). HTTP는 OpenAPI 3.1(`api/openapi.yaml`)로.
- DB 스키마는 EF Core 이관·모델 스냅숏·SQL을 기준으로, 테이블·열·형식·제약·색인·관계를 빠짐없이 적습니다.
- 돈 규칙(단위·반올림·멱등·원장·대사·마감·수수료)과 보안 규칙(인증·인가·토큰·비밀값·감사·개인정보)은 별도 파일로, 숫자와 조건을 근거와 함께 적습니다.
- 한 턴에 서비스 하나(또는 그 일부)를 끝까지 씁니다. 너무 크면 나눠서 다음 일감을 자기에게 보내지 말고 보고서 summary에 남은 범위를 적고 PM에게 알립니다.
- 다 쓴 커밋은 `spec/qa`에 검사를 요청합니다. 인수 시험 담당(`acceptance/lead`)에게 어느 서비스 명세가 준비됐는지 알립니다.
