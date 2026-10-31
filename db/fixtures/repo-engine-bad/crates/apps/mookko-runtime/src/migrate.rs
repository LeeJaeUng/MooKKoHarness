//! 표본: 엔진 공유 이관기가 감추지 않음.

fn shared(migrator: SchemaMigrator) -> SchemaMigrator {
    migrator
}
