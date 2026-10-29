#![forbid(unsafe_code)]
// 시험 파일 전체가 시험 코드입니다(시험의 unwrap·expect 허용). 도우미 함수에도 적용합니다.
#![allow(clippy::unwrap_used, clippy::expect_used)]

use std::path::PathBuf;
use std::time::Duration;

use axum::body::{Body, to_bytes};
use dev_server::{Notifier, ServerSettings, UiConfig, router};
use http::{Request, StatusCode};
use tower::ServiceExt;

fn web_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixtures")
        .join("web")
}

fn app() -> axum::Router {
    let ui = UiConfig {
        app_id: "rustdev".to_owned(),
        display_name: "시험".to_owned(),
        hub_url: "hub-from-config".to_owned(),
    };
    router(
        ServerSettings {
            ui,
            web_dir: web_dir(),
            keep_alive: Duration::from_secs(15),
        },
        Notifier::new(16),
    )
}

async fn get(path: &str) -> (StatusCode, http::HeaderMap, String) {
    let response = app()
        .oneshot(Request::get(path).body(Body::empty()).unwrap())
        .await
        .unwrap();
    let status = response.status();
    let headers = response.headers().clone();
    let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
    (status, headers, String::from_utf8(body.to_vec()).unwrap())
}

#[tokio::test]
async fn health_and_ui_config() {
    let (status, headers, body) = get("/health").await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(headers["x-content-type-options"], "nosniff");
    assert!(body.contains("\"ok\""));

    let (_, _, body) = get("/api/v1/ui-config").await;
    let value: serde_json::Value = serde_json::from_str(&body).unwrap();
    assert_eq!(value["appId"], "rustdev");
    assert_eq!(value["hubUrl"], "hub-from-config");
}

#[tokio::test]
async fn serves_spa_files_and_falls_back_to_index() {
    let (status, _, body) = get("/").await;
    assert_eq!(status, StatusCode::OK);
    assert!(body.contains("fixture-index"));

    let (status, _, body) = get("/assets/app.js").await;
    assert_eq!(status, StatusCode::OK);
    assert!(body.contains("fixture-asset"));

    let (status, _, body) = get("/jobs/123").await;
    assert_eq!(status, StatusCode::OK, "unknown screen paths serve index.html");
    assert!(body.contains("fixture-index"));
}

#[tokio::test]
async fn events_stream_starts_with_hello_and_delivers_notices() {
    let notifier = Notifier::new(16);
    let ui = UiConfig {
        app_id: "rustdev".to_owned(),
        display_name: "시험".to_owned(),
        hub_url: String::new(),
    };
    let app = router(
        ServerSettings {
            ui,
            web_dir: web_dir(),
            keep_alive: Duration::from_secs(15),
        },
        notifier.clone(),
    );
    let response = app
        .oneshot(Request::get("/api/v1/events").body(Body::empty()).unwrap())
        .await
        .unwrap();
    assert_eq!(response.headers()["content-type"], "text/event-stream");

    let mut body = response.into_body().into_data_stream();
    use futures_util::StreamExt;
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
