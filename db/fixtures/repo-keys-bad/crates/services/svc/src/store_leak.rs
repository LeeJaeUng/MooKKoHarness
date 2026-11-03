//! 표본(잡아야 함, QA c63b644 D1): `RowKeyStore`가 돌려준 감싼 키를 형 이름 없이 `.to_bytes()`로 꺼내 서비스 DB에 씀.

async fn leak(store: &RowKeyStore, subject: Uuid) -> Result<Vec<u8>, DataError> {
    let key = store.get(subject, "svc/profile").await?.expect("있음");
    Ok(key.to_bytes())
}

async fn put(store: &RowKeyStore, subject: Uuid, key: &K) -> Result<(), DataError> {
    store.insert_or_get(subject, "svc/profile", key).await?;
    Ok(())
}
