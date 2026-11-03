# svc 표본 설계서 (이관 대조 시험용)

### `accounts`

| 열 | 형식 | 등급 | 보호 |
|---|---|---|---|
| `account_id` | `uuid` | 내부 | 평문 |
| `email` | `text` | 개인 | 암호+색인 |
| `email_bidx` | `bytea` | 내부 | 평문 |
| `email_bidx_kid` | `text` | 내부 | 평문 |
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

### `row_keys` — 키 DB(스키마 svc_keys, 키 클러스터)

| 열 | 형식 | 등급 | 보호 |
|---|---|---|---|
| `subject_id` | `uuid` | 내부 | 평문 |
| `purpose` | `text` | 내부 | 평문 |
| `wrapped_key` | `bytea` | 비밀 | 암호 |
| `created_at` | `timestamptz` | 내부 | 평문 |

보관: 파기 단위(회원)를 파기할 때 행을 지우고 같은 날 `VACUUM`. 키 클러스터 백업·WAL 보관 4일이라 그 뒤에는 어떤 사본에도 남지 않음.
