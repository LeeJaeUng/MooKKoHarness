// 주석의 SELECT * FROM t는 보지 않음
const Q: char = '"';
const OK: &str = "SELECT count(*) FROM t";
const BAD: &str = "SELECT * FROM t WHERE a = $1";
const RAW: &str = r#"
    UPDATE t SET a = 1
    RETURNING *
"#;
