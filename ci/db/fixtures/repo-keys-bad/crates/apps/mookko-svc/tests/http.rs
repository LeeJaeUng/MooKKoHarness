//! 시험 코드의 HTTP 본문 `Collected::to_bytes`는 잡지 않음.
async fn body(response: Response) -> Bytes {
    response.into_body().collect().await.unwrap().to_bytes()
}
