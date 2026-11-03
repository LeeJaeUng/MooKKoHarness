//! 표본(잡아야 함, S-SEC-10): 서비스 코드가 감싼 키를 직접 만들어 서비스 DB 아무 열에 쓰는 모양. 빌드하지 않는다.
//! 주석 안의 WrappedKey·generate_data_key 낱말은 세지 않는다.

async fn seal(vault: &dyn KeyVault, purpose: &KeyPurpose) -> Result<Vec<u8>, PortError> {
    let key = vault.generate_data_key(purpose).await?;
    let wrapped: &WrappedKey = &key.wrapped;
    Ok(wrapped.to_bytes()) // payload bytea로 서비스 DB에 감
}

/* 블록 주석: unwrap_data_key */
async fn open(vault: &dyn KeyVault, bytes: &[u8], purpose: &KeyPurpose) -> Result<(), PortError> {
    let wrapped = WrappedKey::from_bytes(bytes).ok_or(PortError::Rejected("bad".into()))?;
    let _key = vault.unwrap_data_key(&wrapped, purpose).await?;
    Ok(())
}
