// 표본: 실행 파일 crate가 이관 밖에서 구조를 바꿈(잡아야 함).
const PARTITION: &str = "CREATE TABLE IF NOT EXISTS svc.events_202611 PARTITION OF svc.events FOR VALUES FROM (1) TO (2)";
