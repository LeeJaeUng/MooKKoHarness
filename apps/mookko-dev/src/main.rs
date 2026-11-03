//! MooKKoHarness 서버. `--config <경로>`(필수)와 허브가 넘기는 `--port <포트>`(선택)를 받습니다.
#![forbid(unsafe_code)]

use std::process::ExitCode;

#[tokio::main]
async fn main() -> ExitCode {
    let result = match dev_config::parse_args(std::env::args_os().skip(1)) {
        Ok(args) => mookko_dev::run(args).await,
        Err(e) => Err(e.into()),
    };
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("mookko-dev: {e}");
            ExitCode::FAILURE
        }
    }
}
