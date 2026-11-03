//! 시험 코드의 now()는 보지 않음.
const SEED: &str = "INSERT INTO svc.jobs (job_id, claimed_at) VALUES ($1, now())";
