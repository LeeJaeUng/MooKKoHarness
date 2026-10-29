#![forbid(unsafe_code)]
// 시험 파일 전체가 시험 코드입니다(시험의 unwrap·expect 허용). 도우미 함수에도 적용합니다.
#![allow(clippy::unwrap_used, clippy::expect_used)]

use axum::Json;
use axum::Router;
use axum::extract::Path;
use axum::routing::get;
use dev_config::HubConfig;
use dev_hub::{HubClient, PortSource, resolve_port};
use serde::Deserialize;
use serde_json::{Value, json};

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct Fixture {
    fake_hub_listen: String,
    fake_hub_scheme: String,
    unreachable_hub_base_url: String,
    timeout_ms: u64,
}

fn fixture() -> Fixture {
    serde_json::from_str(include_str!("fixtures/hub-test.json")).unwrap()
}

/// 가짜 허브: `rustdev`는 포트 6123, 그 밖은 이상한 레코드.
async fn fake_hub() -> String {
    let f = fixture();
    let app = Router::new().route(
        "/v1/ports/{id}",
        get(|Path(id): Path<String>| async move {
            if id == "rustdev" {
                Json(json!({"id": id, "port": 6123, "url": "ignored"}))
            } else {
                Json(Value::Null)
            }
        }),
    );
    let listener = tokio::net::TcpListener::bind(f.fake_hub_listen.as_str()).await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    format!("{}://{addr}", f.fake_hub_scheme)
}

fn client(base_url: String) -> HubClient {
    HubClient::new(&HubConfig {
        base_url,
        timeout_ms: fixture().timeout_ms,
    })
    .unwrap()
}

#[tokio::test]
async fn arg_wins_over_hub() {
    let hub = client(fake_hub().await);
    let choice = resolve_port(Some(7001), &hub, "rustdev", 7002).await;
    assert_eq!((choice.port, choice.source), (7001, PortSource::Arg));
}

#[tokio::test]
async fn hub_port_is_used_when_no_arg() {
    let hub = client(fake_hub().await);
    let choice = resolve_port(None, &hub, "rustdev", 7002).await;
    assert_eq!((choice.port, choice.source), (6123, PortSource::Hub));
}

#[tokio::test]
async fn fallback_when_hub_is_down_or_odd() {
    let down = client(fixture().unreachable_hub_base_url);
    let choice = resolve_port(None, &down, "rustdev", 7002).await;
    assert_eq!((choice.port, choice.source), (7002, PortSource::Fallback));

    let odd = client(fake_hub().await);
    let choice = resolve_port(None, &odd, "other-app", 7002).await;
    assert_eq!((choice.port, choice.source), (7002, PortSource::Fallback));
}
