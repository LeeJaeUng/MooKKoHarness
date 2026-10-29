#![forbid(unsafe_code)]
// 시험 파일 전체가 시험 코드입니다(시험의 unwrap·expect 허용). 도우미 함수에도 적용합니다.
#![allow(clippy::unwrap_used, clippy::expect_used)]

use std::time::Duration;

use axum::body::{Body, to_bytes};
use dev_server::{Notifier, ServerSettings, router};
use futures_util::StreamExt;
use http::{Request, StatusCode};
use tower::ServiceExt;

fn settings() -> ServerSettings {
    ServerSettings {
        keep_alive: Duration::from_secs(15),
    }
}

#[tokio::test]
async fn health_answers_and_unknown_paths_are_404() {
    let app = router(settings(), Notifier::new(16));
    let response = app
        .clone()
        .oneshot(Request::get("/health").body(Body::empty()).unwrap())
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(response.headers()["x-content-type-options"], "nosniff");
    let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
    assert!(String::from_utf8_lossy(&body).contains("\"ok\""));

    let response = app
        .oneshot(Request::get("/jobs").body(Body::empty()).unwrap())
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::NOT_FOUND, "no screens are served");
}

#[tokio::test]
async fn events_stream_starts_with_hello_and_delivers_notices() {
    let notifier = Notifier::new(16);
    let app = router(settings(), notifier.clone());
    let response = app
        .oneshot(Request::get("/api/v1/events").body(Body::empty()).unwrap())
        .await
        .unwrap();
    assert_eq!(response.headers()["content-type"], "text/event-stream");

    let mut body = response.into_body().into_data_stream();
    let first = body.next().await.unwrap().unwrap();
    assert!(String::from_utf8_lossy(&first).contains("event: hello"));

    notifier.notify("tasks");
    let next = tokio::time::timeout(Duration::from_secs(2), body.next())
        .await
        .unwrap()
        .unwrap()
        .unwrap();
    let text = String::from_utf8_lossy(&next);
    assert!(text.contains("event: notice") && text.contains("\"tasks\""), "{text}");
}
