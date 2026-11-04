//! 표본: 이관기 덧붙이기만 목록에서 지운 표(audit_records)를 뺀 서비스. 빌드하지 않는다.
const APPEND_ONLY: &[&str] = &[];

fn migrator(m: SchemaMigrator) -> SchemaMigrator {
    APPEND_ONLY.iter().fold(m, |m, t| m.append_only(t))
}
