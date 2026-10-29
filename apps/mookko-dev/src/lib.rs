//! 하네스 조립: 설정 → 로그 → 포트(실행 인자 → 허브 → 설정) → 서버.
#![forbid(unsafe_code)]

use std::future::Future;
use std::net::SocketAddr;
use std::time::Duration;

use dev_config::{Args, ConfigError, DevConfig, LogFormat};
use dev_hub::{HubClient, HubError, PortChoice, resolve_port};
use dev_server::{Notifier, ServerSettings, UiConfig};
use tokio::net::TcpListener;
use tracing_subscriber::EnvFilter;

/// SSE 연결 유지 신호 간격.
const SSE_KEEP_ALIVE: Duration = Duration::from_secs(15);
/// 실시간 알림 버퍼 크기.
const NOTICE_CAPACITY: usize = 256;

/// 실행 실패.
#[derive(Debug, thiserror::Error)]
pub enum RunError {
    /// 설정.
    #[error(transparent)]
    Config(#[from] ConfigError),
    /// 허브 클라이언트.
    #[error(transparent)]
    Hub(#[from] HubError),
    /// 로그 설치.
    #[error("cannot install logging: {0}")]
    Telemetry(String),
    /// 주소에 묶지 못함.
    #[error("cannot bind port {port}: {source}")]
    Bind {
        /// 포트.
        port: u16,
        /// 원인.
        source: std::io::Error,
    },
    /// 실행 중 입출력.
    #[error("server io error: {0}")]
    Io(#[from] std::io::Error),
}

/// 묶인 서버.
#[derive(Debug)]
pub struct Bound {
    listener: TcpListener,
    router: axum::Router,
    /// 정한 포트와 출처.
    pub port: PortChoice,
    /// 실시간 알림 보내는 쪽.
    pub notifier: Notifier,
}

impl Bound {
    /// 실제로 묶인 주소.
    pub fn local_addr(&self) -> Result<SocketAddr, RunError> {
        Ok(self.listener.local_addr()?)
    }

    /// `shutdown`이 끝날 때까지 요청을 받습니다.
    pub async fn serve<F>(self, shutdown: F) -> Result<(), RunError>
    where
        F: Future<Output = ()> + Send + 'static,
    {
        axum::serve(self.listener, self.router)
            .with_graceful_shutdown(shutdown)
            .await?;
        Ok(())
    }
}

/// 로그를 설치합니다.
pub fn init_logging(config: &DevConfig) -> Result<(), RunError> {
    let filter = EnvFilter::try_new(&config.telemetry.filter).map_err(|e| RunError::Telemetry(e.to_string()))?;
    let builder = tracing_subscriber::fmt().with_env_filter(filter);
    let installed = match config.telemetry.format {
        LogFormat::Json => builder.json().try_init(),
        LogFormat::Text => builder.try_init(),
    };
    installed.map_err(|e| RunError::Telemetry(e.to_string()))
}

/// 포트를 정하고 주소에 묶습니다.
pub async fn bind(config: &DevConfig, arg_port: Option<u16>) -> Result<Bound, RunError> {
    let hub = HubClient::new(&config.hub)?;
    let port = resolve_port(arg_port, &hub, &config.app_id, config.listen.fallback_port).await;
    let listener = TcpListener::bind((config.listen.host, port.port))
        .await
        .map_err(|source| RunError::Bind {
            port: port.port,
            source,
        })?;
    let notifier = Notifier::new(NOTICE_CAPACITY);
    let ui = UiConfig {
        app_id: config.app_id.clone(),
        display_name: config.display_name.clone(),
        hub_url: hub.base_url().to_owned(),
    };
    let settings = ServerSettings {
        ui,
        web_dir: config.web_dir.clone(),
        keep_alive: SSE_KEEP_ALIVE,
    };
    let router = dev_server::router(settings, notifier.clone());
    Ok(Bound {
        listener,
        router,
        port,
        notifier,
    })
}

/// 실행 인자로 끝까지 실행합니다(Ctrl+C로 끔).
pub async fn run(args: Args) -> Result<(), RunError> {
    let config = dev_config::load(&args.config).await?;
    init_logging(&config)?;
    let bound = bind(&config, args.port).await?;
    tracing::info!(addr = %bound.local_addr()?, source = ?bound.port.source, "listening");
    bound.serve(shutdown_signal()).await?;
    tracing::info!("stopped");
    Ok(())
}

async fn shutdown_signal() {
    if let Err(e) = tokio::signal::ctrl_c().await {
        tracing::error!(error = %e, "cannot listen for shutdown signal; stopping");
    }
}
