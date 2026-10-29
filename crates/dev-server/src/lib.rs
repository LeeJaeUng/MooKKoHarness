//! 하네스 HTTP 서버(API만, 화면 없음).
//!
//! - `GET /health`: 살아 있는지.
//! - `GET /api/v1/events`: 실시간 알림(SSE). 허브 같은 다른 프로그램이 상태 변화를 듣습니다.
#![forbid(unsafe_code)]

use std::convert::Infallible;
use std::time::Duration;

use axum::Json;
use axum::Router;
use axum::extract::State;
use axum::response::sse::{Event, KeepAlive, Sse};
use axum::routing::get;
use futures_util::{Stream, StreamExt};
use http::{HeaderValue, header};
use serde::Serialize;
use tokio::sync::broadcast;
use tokio_stream::wrappers::BroadcastStream;
use tower_http::set_header::SetResponseHeaderLayer;

/// 실시간 알림 하나. `kind`로 받는 쪽이 무엇을 다시 읽을지 정합니다.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct Notice {
    /// 종류(예: `tasks`, `roles`).
    pub kind: String,
}

/// 서버 설정.
#[derive(Clone, Debug)]
pub struct ServerSettings {
    /// SSE 연결 유지 신호 간격.
    pub keep_alive: Duration,
}

/// 실시간 알림 보내는 쪽.
#[derive(Clone, Debug)]
pub struct Notifier {
    tx: broadcast::Sender<Notice>,
}

impl Notifier {
    /// 받는 쪽이 따라오지 못하면 오래된 알림부터 버리는 크기 `capacity`로 만듭니다.
    pub fn new(capacity: usize) -> Self {
        let (tx, _) = broadcast::channel(capacity.max(1));
        Self { tx }
    }

    /// 알림을 보냅니다(듣는 쪽이 없으면 버림).
    pub fn notify(&self, kind: &str) {
        let _ = self.tx.send(Notice { kind: kind.to_owned() });
    }
}

#[derive(Clone, Debug)]
struct AppState {
    notifier: Notifier,
    keep_alive: Duration,
}

/// 라우터를 만듭니다.
pub fn router(settings: ServerSettings, notifier: Notifier) -> Router {
    let state = AppState {
        notifier,
        keep_alive: settings.keep_alive,
    };
    Router::new()
        .route("/health", get(health))
        .route("/api/v1/events", get(events))
        .with_state(state)
        .layer(SetResponseHeaderLayer::if_not_present(
            header::X_CONTENT_TYPE_OPTIONS,
            HeaderValue::from_static("nosniff"),
        ))
        .layer(SetResponseHeaderLayer::if_not_present(
            header::CACHE_CONTROL,
            HeaderValue::from_static("no-store"),
        ))
}

#[derive(Debug, Serialize)]
struct HealthBody {
    status: &'static str,
}

async fn health() -> Json<HealthBody> {
    Json(HealthBody { status: "ok" })
}

async fn events(State(state): State<AppState>) -> Sse<impl Stream<Item = Result<Event, Infallible>>> {
    let hello = futures_util::stream::once(async { Ok(Event::default().event("hello").data("{}")) });
    let notices = BroadcastStream::new(state.notifier.tx.subscribe()).filter_map(|item| async move {
        match item {
            Ok(notice) => Event::default().event("notice").json_data(&notice).ok().map(Ok),
            // 따라오지 못해 버린 알림이 있으면 받는 쪽이 전부 다시 읽게 합니다.
            Err(_) => Some(Ok(Event::default().event("resync").data("{}"))),
        }
    });
    Sse::new(hello.chain(notices)).keep_alive(KeepAlive::new().interval(state.keep_alive))
}
