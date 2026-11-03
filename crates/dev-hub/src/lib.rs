//! 허브(MooKKoHub) 클라이언트.
//!
//! 공통 규칙(MooKKo 폴더 `CLAUDE.md` › 포트): 자기 포트는 실행 인자 → 허브 `GET /v1/ports/<id>` → 설정 값 순서로 정합니다.
//! 허브 주소는 설정 JSON에서만 옵니다.
#![forbid(unsafe_code)]

use dev_config::HubConfig;
use serde::Deserialize;

/// 포트를 어디서 정했는지.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PortSource {
    /// 허브가 켤 때 넘긴 실행 인자.
    Arg,
    /// 허브 포트 조회.
    Hub,
    /// 허브가 꺼져 있거나 답이 없어 설정 값을 씀.
    Fallback,
}

/// 정한 포트.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PortChoice {
    /// 포트.
    pub port: u16,
    /// 출처.
    pub source: PortSource,
}

/// 허브 요청 실패.
#[derive(Debug, thiserror::Error)]
pub enum HubError {
    /// HTTP 클라이언트를 만들지 못함.
    #[error("cannot build hub client: {0}")]
    Client(String),
    /// 요청 실패(꺼짐·시간 초과·응답 형식).
    #[error("hub request failed: {0}")]
    Request(String),
    /// 응답의 id나 포트가 맞지 않음.
    #[error("hub returned an unexpected port record")]
    Unexpected,
}

#[derive(Debug, Deserialize)]
struct PortRecord {
    id: String,
    port: u16,
}

/// 허브 클라이언트.
#[derive(Clone, Debug)]
pub struct HubClient {
    http: reqwest::Client,
    base_url: String,
}

impl HubClient {
    /// 설정으로 만듭니다(요청마다 설정의 기한을 씀, 리디렉션 따라가지 않음).
    pub fn new(config: &HubConfig) -> Result<Self, HubError> {
        let http = reqwest::Client::builder()
            .timeout(config.timeout())
            .redirect(reqwest::redirect::Policy::none())
            .no_proxy()
            .build()
            .map_err(|e| HubError::Client(e.to_string()))?;
        Ok(Self {
            http,
            base_url: config.base_url.trim_end_matches('/').to_owned(),
        })
    }

    /// 허브 기본 주소(화면의 프로그램 선택 상자에 넘김).
    pub fn base_url(&self) -> &str {
        &self.base_url
    }

    /// 허브에 등록된 포트를 묻습니다.
    pub async fn port_of(&self, app_id: &str) -> Result<u16, HubError> {
        let url = format!("{}/v1/ports/{app_id}", self.base_url);
        let record: PortRecord = self
            .http
            .get(url)
            .send()
            .await
            .and_then(reqwest::Response::error_for_status)
            .map_err(|e| HubError::Request(e.to_string()))?
            .json()
            .await
            .map_err(|e| HubError::Request(e.to_string()))?;
        if record.id == app_id && record.port != 0 {
            Ok(record.port)
        } else {
            Err(HubError::Unexpected)
        }
    }
}

/// 공통 규칙 순서대로 포트를 정합니다. 허브 실패는 경고만 남기고 설정 값으로 넘어갑니다.
pub async fn resolve_port(arg: Option<u16>, hub: &HubClient, app_id: &str, fallback: u16) -> PortChoice {
    if let Some(port) = arg {
        return PortChoice {
            port,
            source: PortSource::Arg,
        };
    }
    match hub.port_of(app_id).await {
        Ok(port) => PortChoice {
            port,
            source: PortSource::Hub,
        },
        Err(e) => {
            tracing::warn!(error = %e, "hub port lookup failed; using fallback port from config");
            PortChoice {
                port: fallback,
                source: PortSource::Fallback,
            }
        }
    }
}
