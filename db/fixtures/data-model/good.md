<!-- expect: (없음) -->
# 표본 설계서 (통과해야 함)

## 2. 테이블

### `accounts`

| 열 | 형식 | 제약 | 등급 | 보호 | 뜻 |
|---|---|---|---|---|---|
| `account_id` | `uuid` | PK | 내부 | 평문 | UUIDv7 |
| `email` | `text` | NOT NULL | 개인 | 암호+색인 | 로그인 이메일(`a|b` 같은 글은 칸을 나누지 않음) |
| `email_bidx` | `bytea` | UNIQUE | 내부 | 평문 | `email`의 blind index |
| `password_hash` | `text` | NOT NULL | 비밀 | 해시 | Argon2id |
| `token_count` | `integer` | NOT NULL | 내부 | 평문 | 이름 예외: 개수일 뿐 |
| `bank_account_ref` | `text` | NULL | 민감 | 토큰화 | PG사 토큰 |

보관: 탈퇴 즉시 `email`을 지우고 행은 가명으로 남김.

### 3.1 `audit_events` — 덧붙이기만

| 열 | 형식 | 등급 | 보호 |
|---|---|---|---|
| `id` | `uuid` | 내부 | 평문 |
| `reason` | `text` | 개인 | 암호 |

보관 기한: 5년(법무 확인), 파티션 떼기로 파기.

### 3.4 역할 — `roles`·`staff_roles`

| 테이블 | 열 | 형식 | 등급 | 보호 |
|---|---|---|---|---|
| `roles` | `role_id` | `text` | 내부 | 평문 |
| `staff_roles` | `staff_id` | `text` | 내부 | 평문 |

보관: 지금 상태만, 이력은 감사.

## 4. ClickHouse

### `mookko_logs.otel_logs`

```sql
CREATE TABLE mookko_logs.otel_logs
(
    Timestamp DateTime64(9) CODEC(Delta(8), ZSTD(1)),
    Body String,
    UserRef String MATERIALIZED LogAttributes['mookko.user'],
    INDEX idx_body lower(Body) TYPE tokenbf_v1(32768, 3, 0) GRANULARITY 1
)
ENGINE = MergeTree
ORDER BY Timestamp
TTL Timestamp + INTERVAL 45 DAY DELETE;
```

| 테이블 | 열 | 등급 | 보호 | 뜻 |
|---|---|---|---|---|
| `otel_logs` | `Body` | 내부 | 평문 | 수집기가 가린 뒤의 본문 |
| `otel_logs` | `UserRef` | 내부 | 평문 | HMAC로 가린 사용자 |
| `otel_logs` | (나머지) | 내부 | 평문 | 시각·서비스 |

보관: TTL 45일.

## 5. 엔진 테이블(서비스가 이름을 정함)

### `<원장>_heads`

| 열 | 형식 | 등급 | 보호 |
|---|---|---|---|
| `partition_key` | `text` | 내부 | 평문 |
| `head_hash` | `bytea` | 내부 | 평문 |

보관: 구간마다 한 행, 지우지 않음.
