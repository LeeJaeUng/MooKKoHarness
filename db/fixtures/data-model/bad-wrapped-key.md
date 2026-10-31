<!-- expect: S-SEC-10 -->
# 표본 (잡아야 함: 감싼 행 키 등급, E-DB-8)

### `row_keys`

| 열 | 형식 | 등급 | 보호 |
|---|---|---|---|
| `subject_id` | `uuid` | 내부 | 평문 |
| `wrapped_key` | `bytea` | 비밀 | 해시 |

보관: 파기할 때 지움, 키 DB 백업 4일.
