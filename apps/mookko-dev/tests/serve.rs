#![forbid(unsafe_code)]
// 시험 파일 전체가 시험 코드입니다(시험의 unwrap·expect 허용). 도우미 함수에도 적용합니다.
#![allow(clippy::unwrap_used, clippy::expect_used)]

use std::path::PathBuf;

use dev_hub::PortSource;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpStream;
use tokio::sync::oneshot;

fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixtures")
        .join("dev.json")
}

async fn http_get(addr: std::net::SocketAddr, path: &str) -> String {
    let mut stream = TcpStream::connect(addr).await.unwrap();
    let request = format!("GET {path} HTTP/1.1\r\nHost: {addr}\r\nConnection: close\r\n\r\n");
    stream.write_all(request.as_bytes()).await.unwrap();
    let mut response = String::new();
    stream.read_to_string(&mut response).await.unwrap();
    response
}

#[tokio::test]
async fn starts_with_fallback_port_when_hub_is_down_and_serves() {
    let config = dev_config::load(&fixture()).await.unwrap();
    let bound = mookko_dev::bind(&config, None).await.unwrap();
    assert_eq!(bound.port.source, PortSource::Fallback);
    let addr = bound.local_addr().unwrap();
    let (stop_tx, stop_rx) = oneshot::channel::<()>();
    let running = tokio::spawn(bound.serve(async move {
        let _ = stop_rx.await;
    }));

    let health = http_get(addr, "/health").await;
    assert!(health.starts_with("HTTP/1.1 200"), "{health}");
    let missing = http_get(addr, "/jobs").await;
    assert!(missing.starts_with("HTTP/1.1 404"), "{missing}");

    stop_tx.send(()).unwrap();
    running.await.unwrap().unwrap();
}

#[tokio::test]
async fn arg_port_is_used_first() {
    let config = dev_config::load(&fixture()).await.unwrap();
    // 비어 있는 포트를 운영체제에서 받아 실행 인자로 넘깁니다.
    let probe = tokio::net::TcpListener::bind((config.listen.host, 0)).await.unwrap();
    let free = probe.local_addr().unwrap().port();
    drop(probe);
    let bound = mookko_dev::bind(&config, Some(free)).await.unwrap();
    assert_eq!(bound.port.source, PortSource::Arg);
    assert_eq!(bound.local_addr().unwrap().port(), free);
}
