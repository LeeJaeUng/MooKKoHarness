# svc 표본 설계서 (이관 대조 시험용)

### `accounts`

| 열 | 형식 | 등급 | 보호 |
|---|---|---|---|
| `account_id` | `uuid` | 내부 | 평문 |
| `email` | `text` | 개인 | 암호+색인 |
| `email_bidx` | `bytea` | 내부 | 평문 |
| `state` | `text` | 내부 | 평문 |
| `created_at` | `timestamptz` | 내부 | 평문 |
| `closed_at` | `timestamptz` | 내부 | 평문 |
| `region` | `text` | 내부 | 평문 |
| `tier` | `text` | 내부 | 평문 |

보관: 탈퇴 즉시 `email` 지움.

### `ledger_entries`

| 열 | 형식 | 등급 | 보호 |
|---|---|---|---|
| `entry_id` | `uuid` | 내부 | 평문 |
| `account_id` | `uuid` | 내부 | 평문 |
| `amount_minor` | `bigint` | 내부 | 평문 |
| `currency` | `char(3)` | 내부 | 평문 |
| `idempotency_key` | `text` | 내부 | 평문 |
| `occurred_at` | `timestamptz` | 내부 | 평문 |

보관: 법정 기간(법무 확인), 파티션 떼기로 파기.
