//! 표본: 지우는 열·표를 아직 부르는 코드(2건)와 잡지 않을 것. 빌드하지 않는다.
// olds 표는 주석에만 나오면 잡지 않음
const READ: &str = "SELECT item_id, old_note FROM items WHERE item_id = $1";
const PURGE: &str = "DELETE FROM olds";
const OK: &str = "SELECT item_id FROM items";
const NOTE_ELSEWHERE: &str = "old_note";
