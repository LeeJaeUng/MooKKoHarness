//! 표본: 상수만 있고 엔진에 넘기지 않음(`reader_hidden` 부름이 주석에만 있음).

const READER_HIDDEN: &[&str] = &["visits"];

// migrator.reader_hidden(&SqlName::parse(table)?)
