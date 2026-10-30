// 표본: 서비스 코드가 이관 밖에서 구조를 바꿈(잡아야 함). 주석의 ALTER TABLE은 보지 않음.
const WIDEN: &str = "ALTER TABLE svc.items ADD COLUMN note text";
const OK: &str = "SELECT item_id FROM svc.items WHERE item_id = $1";
