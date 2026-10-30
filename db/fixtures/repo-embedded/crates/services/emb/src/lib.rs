//! 표본: 이관을 실행 파일에 넣어 쓰는 서비스(잡아야 할 것: ID가 파일 이름과 다름, transaction off를 .add()로, 빠진 파일, append_only 지정 없음).
const MIGRATIONS: &[(&str, &str)] = &[
    ("0001_audit", include_str!("../migrations/0001_audit_log.sql")),
    (
        "0002_index",
        include_str!("../migrations/0002_index.sql"),
    ),
];
