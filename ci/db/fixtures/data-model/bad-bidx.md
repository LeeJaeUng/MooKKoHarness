<!-- expect: S-SEC-3 -->
# 표본 (잡아야 함: blind index 열 모양, E-DB-7)

### `members`

| 열 | 형식 | 등급 | 보호 |
|---|---|---|---|
| `member_id` | `uuid` | 내부 | 평문 |
| `email` | `text` | 개인 | 암호+색인 |
| `email_bidx` | `bytea` | 내부 | 평문 |
| `phone` | `text` | 개인 | 암호 |
| `phone_bidx` | `bytea` | 내부 | 평문 |
| `phone_bidx_kid` | `text` | 내부 | 평문 |

보관: 탈퇴 즉시 지움.
