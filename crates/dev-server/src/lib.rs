//! 하네스 HTTP 서버.
//!
//! - `GET /health`: 살아 있는지.
//! - `GET /api/v1/ui-config`: 화면이 처음 읽는 값(앱 id, 표시 이름, 허브 주소). 화면 코드에 주소를 두지 않기 위해 서버가 넘깁니다.
//! - `GET /api/v1/events`: 실시간 알림(SSE). 화면은 주기 새로고침 대신 이것을 듣습니다.
//! - 그 밖의 경로: 빌드된 화면(SPA). 없는 파일은 `index.html`(화면 안 경로).
#![forbid(unsafe_code)]

use std::convert::Infallible;
use std::path::PathBuf;
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
use tower_http::services::{ServeDir, ServeFile};
use tower_http::set_header::SetResponseHeaderLayer;

/// 화면에 넘기는 값.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UiConfig {
    /// 허브 앱 id(프로그램 선택 상자의 `data-current`).
    pub app_id: String,
    /// 화면에 보이는 이름.
    pub display_name: String,
    /// 허브 기본 주소(프로그램 선택 상자 스크립트 위치).
    pub hub_url: String,
}

/// 실시간 알림 하나. `kind`로 화면이 무엇을 다시 읽을지 정합니다.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct Notice {
    /// 종류(예: `tasks`, `roles`).
    pub kind: String,
}

/// 서버 설정.
#[derive(Clone, Debug)]
pub struct ServerSettings {
    /// 화면 값.
    pub ui: UiConfig,
    /// 빌드된 화면 폴더.
    pub web_dir: PathBuf,
    /// SSE 연결 유지 신호 간격.
    pub keep_alive: Duration,
}

/// 서버 상태(실시간 알림 보내는 쪽).
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

    /// 알림을 보냅니다(듣는 화면이 없으면 버림).
    pub fn notify(&self, kind: &str) {
        let _ = self.tx.send(Notice { kind: kind.to_owned() });
    }
}

#[derive(Clone, Debug)]
struct AppState {
    ui: UiConfig,
    notifier: Notifier,
    keep_alive: Duration,
}

/// 라우터를 만듭니다.
pub fn router(settings: ServerSettings, notifier: Notifier) -> Router {
    let index = settings.web_dir.join("index.html");
    let spa = ServeDir::new(&settings.web_dir).fallback(ServeFile::new(index));
    let state = AppState {
        ui: settings.ui,
        notifier,
        keep_alive: settings.keep_alive,
    };
    Router::new()
        .route("/health", get(health))
        .route("/api/v1/ui-config", get(ui_config))
        .route("/api/v1/events", get(events))
        .with_state(state)
        .fallback_service(spa)
        .layer(SetResponseHeaderLayer::if_not_present(
            header::X_CONTENT_TYPE_OPTIONS,
            HeaderValue::from_static("nosniff"),
        ))
        .layer(SetResponseHeaderLayer::if_not_present(
            header::X_FRAME_OPTIONS,
            HeaderValue::from_static("DENY"),
        ))
        .layer(SetResponseHeaderLayer::if_not_present(
            header::REFERRER_POLICY,
            HeaderValue::from_static("no-referrer"),
        ))
}

#[derive(Debug, Serialize)]
struct HealthBody {
    status: &'static str,
}

async fn health() -> Json<HealthBody> {
    Json(HealthBody { status: "ok" })
}

async fn ui_config(State(state): State<AppState>) -> Json<UiConfig> {
    Json(state.ui)
}

async fn events(State(state): State<AppState>) -> Sse<impl Stream<Item = Result<Event, Infallible>>> {
    let hello = futures_util::stream::once(async { Ok(Event::default().event("hello").data("{}")) });
    let notices = BroadcastStream::new(state.notifier.tx.subscribe()).filter_map(|item| async move {
        match item {
            Ok(notice) => Event::default().event("notice").json_data(&notice).ok().map(Ok),
            // 따라오지 못해 버린 알림이 있으면 화면이 전부 다시 읽게 합니다.
            Err(_) => Some(Ok(Event::default().event("resync").data("{}"))),
        }
    });
    Sse::new(hello.chain(notices)).keep_alive(KeepAlive::new().interval(state.keep_alive))
}
