<!-- expect: S-SEC-1, S-SEC-2, S-SEC-3 -->
# 표본 (잡아야 함: 등급·보호)

### `users`

| 열 | 형식 | 등급 | 보호 |
|---|---|---|---|
| `user_id` | `uuid` | 내부 | 평문 |
| `email` | `text` | 개인 | 평문 |
| `phone` | `text` | 내부 | 평문 |
| `api_key` | `text` | 개인 | 암호 |
| `rrn` | `text` | 민감 | 암호+색인 |
| `nick` | `text` | 보통 | 평문 |

보관: 탈퇴 뒤 30일.
