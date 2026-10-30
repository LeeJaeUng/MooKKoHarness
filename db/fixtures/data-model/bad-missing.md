<!-- expect: S-SEC-1, S-SEC-6 -->
# 표본 (잡아야 함: 칸 없음·문장만·요약 표·보관 없음·SQL 열 빠짐)

### `handles`

| 열 | 형식 | 제약 | 설명 |
|---|---|---|---|
| `handle` | `text` | PK | 정규화한 핸들 |

### `reports` — 신고

`report_id uuid PK`, `detail text`, `created_at`.

| 테이블 | 열(요약) | 제약 |
|---|---|---|
| `host` | `id`, `name`, `address` | |

### `sessions`

| 열 | 형식 | 등급 | 보호 |
|---|---|---|---|
| `session_id` | `uuid` | 내부 | 평문 |

### `query_audits`

```sql
CREATE TABLE logs.query_audits (
    id uuid PRIMARY KEY,
    actor_id text NOT NULL,
    criteria jsonb NOT NULL
);
```

| 테이블 | 열 | 등급 | 보호 |
|---|---|---|---|
| `query_audits` | `id` | 내부 | 평문 |

보관: 2년.
