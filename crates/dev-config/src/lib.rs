//! 하네스 설정.
//!
//! 주소·포트는 코드에 두지 않고 이 JSON 파일에서만 읽습니다. 경로는 실행 인자 `--config <경로>`로 받습니다.
//! 자기 포트는 공통 규칙 순서(실행 인자 → 허브 → 설정)로 정하며, 그 순서는 `dev-hub`가 맡습니다.
#![forbid(unsafe_code)]

use std::ffi::OsString;
use std::path::{Path, PathBuf};
use std::time::Duration;

use serde::Deserialize;

/// 설정 경로를 넘기는 실행 인자.
pub const CONFIG_ARG: &str = "--config";
/// 허브가 켤 때 포트를 넘기는 실행 인자.
pub const PORT_ARG: &str = "--port";

/// 하네스 설정(JSON). 모든 칸이 필수입니다.
#[derive(Clone, Debug, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct DevConfig {
    /// 허브 앱 id(포트 조회와 프로그램 선택 상자에 씀).
    pub app_id: String,
    /// 듣는 주소.
    pub listen: ListenConfig,
    /// 허브.
    pub hub: HubConfig,
    /// 로그.
    pub telemetry: TelemetryConfig,
}

/// 듣는 주소. 포트는 허브 값이 있으면 허브 값을 씁니다.
#[derive(Clone, Debug, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ListenConfig {
    /// 듣는 IP(내부 도구는 루프백만).
    pub host: std::net::IpAddr,
    /// 허브가 꺼져 있을 때 쓰는 포트.
    pub fallback_port: u16,
}

/// 허브 연결.
#[derive(Clone, Debug, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct HubConfig {
    /// 허브 기본 주소.
    pub base_url: String,
    /// 허브 요청 기한(밀리초).
    pub timeout_ms: u64,
}

impl HubConfig {
    /// 요청 기한.
    pub fn timeout(&self) -> Duration {
        Duration::from_millis(self.timeout_ms)
    }
}

/// 로그.
#[derive(Clone, Debug, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct TelemetryConfig {
    /// 거르기 규칙(`info` 등).
    pub filter: String,
    /// `json` 또는 `text`.
    pub format: LogFormat,
}

/// 로그 형식.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum LogFormat {
    /// 한 줄 JSON.
    Json,
    /// 사람이 읽는 글.
    Text,
}

/// 실행 인자.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Args {
    /// 설정 파일 경로.
    pub config: PathBuf,
    /// 허브가 넘긴 포트(있으면 가장 먼저 씀).
    pub port: Option<u16>,
}

/// 설정 읽기 실패.
#[derive(Debug, thiserror::Error)]
pub enum ConfigError {
    /// `--config`가 없음.
    #[error("{CONFIG_ARG} <path> is required")]
    MissingConfig,
    /// 인자 값이 없거나 잘못됨.
    #[error("invalid argument {0}")]
    BadArg(String),
    /// 파일을 읽지 못함.
    #[error("cannot read config {path}: {source}")]
    Io {
        /// 경로.
        path: PathBuf,
        /// 원인.
        source: std::io::Error,
    },
    /// 형식·칸이 맞지 않음.
    #[error("invalid config {origin}: {source}")]
    Parse {
        /// 출처.
        origin: String,
        /// 원인.
        source: serde_json::Error,
    },
}

/// 실행 인자를 읽습니다(첫 인자인 실행 파일 이름은 빼고 넘깁니다).
pub fn parse_args<I: IntoIterator<Item = OsString>>(args: I) -> Result<Args, ConfigError> {
    let mut config = None;
    let mut port = None;
    let mut args = args.into_iter();
    while let Some(arg) = args.next() {
        if arg == CONFIG_ARG {
            config = Some(PathBuf::from(
                args.next().ok_or_else(|| ConfigError::BadArg(CONFIG_ARG.to_owned()))?,
            ));
        } else if arg == PORT_ARG {
            let value = args.next().ok_or_else(|| ConfigError::BadArg(PORT_ARG.to_owned()))?;
            let parsed = value.to_str().and_then(|v| v.parse::<u16>().ok()).filter(|p| *p != 0);
            port = Some(parsed.ok_or_else(|| ConfigError::BadArg(PORT_ARG.to_owned()))?);
        } else {
            return Err(ConfigError::BadArg(arg.to_string_lossy().into_owned()));
        }
    }
    Ok(Args {
        config: config.ok_or(ConfigError::MissingConfig)?,
        port,
    })
}

/// JSON 글자를 읽습니다.
pub fn parse_json(text: &str, origin: &str) -> Result<DevConfig, ConfigError> {
    serde_json::from_str(text).map_err(|source| ConfigError::Parse {
        origin: origin.to_owned(),
        source,
    })
}

/// 설정 파일을 읽습니다.
pub async fn load(path: &Path) -> Result<DevConfig, ConfigError> {
    let text = tokio::fs::read_to_string(path)
        .await
        .map_err(|source| ConfigError::Io {
            path: path.to_owned(),
            source,
        })?;
    parse_json(&text, &path.display().to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn os(v: &str) -> OsString {
        OsString::from(v)
    }

    #[test]
    fn args_need_config_and_accept_port() {
        let a = parse_args([os("--config"), os("c.json"), os("--port"), os("6001")]).unwrap();
        assert_eq!(a.config, PathBuf::from("c.json"));
        assert_eq!(a.port, Some(6001));
        assert!(matches!(parse_args([]), Err(ConfigError::MissingConfig)));
        assert!(matches!(
            parse_args([os("--config"), os("c.json"), os("--port"), os("0")]),
            Err(ConfigError::BadArg(_))
        ));
        assert!(matches!(parse_args([os("--what")]), Err(ConfigError::BadArg(_))));
    }

    #[test]
    fn config_is_strict() {
        let good = include_str!("../tests/fixtures/dev.json");
        assert_eq!(parse_json(good, "t").unwrap().app_id, "harness");
        let extra = good.replace("\"telemetry\"", "\"extra\":1,\"telemetry\"");
        assert!(parse_json(&extra, "t").is_err());
    }
}
