"""scripts/ci/db 검사의 표본 시험 (docs/policy/conventions/tools.md T-PY-7).

잡아야 할 표본은 기대한 규칙 번호로 정확히 잡히고, 통과해야 할 표본은 아무것도 걸리지 않아야 한다.
- fixtures/migrations/single/*.sql: 머리 `-- expect: 규칙, …` 또는 `(없음)`, 이름이 `ch_`면 ClickHouse 규칙
- fixtures/repo-good, repo-bad: 폴더 단위(이름·번호·Rust 문자열)
- fixtures/data-model/*.md: `<!-- expect: … -->`
- fixtures/repo-reader-bad: 읽기 계정 감추기(S-SEC-9, 모두 연 서비스), repo-reader-closed: 닫힌 기본
- fixtures/repo-partition-bad: 파티션 부모를 엔진에 적기(S-PART-3)
- fixtures/repo-validate: 같은 배포 VALIDATE 근거(S-MIG-4)
- fixtures/repo-engine-good, repo-engine-bad: 엔진 표 읽기 계정 감추기(S-SEC-9 엔진 몫)
- fixtures/repo-good, apply-bad: 실제 PostgreSQL 적용(MOOKKO_TEST_POSTGRES가 있을 때만, 없으면 건너뜀을 출력)
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import data_classes  # noqa: E402
import migration_apply  # noqa: E402
import migration_lint  # noqa: E402
import migration_lock  # noqa: E402
import pending  # noqa: E402

FIXTURES = HERE / "fixtures"
EMPTY_PENDING = FIXTURES / "pending-empty.json"
EMPTY_LOCK = FIXTURES / "lock-empty.json"
EMPTY_EXCEPTIONS = FIXTURES / "exceptions-empty.json"
EMPTY_ENGINE = FIXTURES / "engine-generated-empty.json"


def expected(text: str, pattern: str) -> set[str]:
    match = re.search(pattern, text)
    if not match:
        raise AssertionError("표본에 expect 머리가 없음")
    value = match.group(1).strip()
    return set() if value == "(없음)" else {v.strip() for v in value.split(",")}


def quiet(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = fn(*args)
    return code, out.getvalue()


class MigrationLintSamples(unittest.TestCase):
    def test_single_files(self) -> None:
        files = sorted((FIXTURES / "migrations" / "single").glob("*.sql"))
        self.assertGreater(len(files), 40)
        for path in files:
            text = path.read_text(encoding="utf-8")
            dialect = "clickhouse" if path.name.startswith("ch_") else "postgres"
            got = {f.rule for f in migration_lint.lint_text(path.name, text, dialect, "svc")}
            with self.subTest(path.name):
                self.assertEqual(got, expected(text, r"-- expect: (.*)"))

    def test_good_repo_passes(self) -> None:
        code, out = quiet(migration_lint.main, ["--root", str(FIXTURES / "repo-good"), "--pending", str(EMPTY_PENDING), "--lock-file", str(EMPTY_LOCK), "--exceptions", str(EMPTY_EXCEPTIONS), "--engine-generated", str(EMPTY_ENGINE)])
        self.assertEqual(code, 0, out)

    def test_bad_repo_names_numbers_rust(self) -> None:
        root = FIXTURES / "repo-bad"
        findings = migration_lint.lint_dir(root, root / "crates" / "services" / "svc" / "migrations")
        self.assertIn("V4__d.sql", " ".join(f.path for f in findings))
        self.assertTrue(any("기대 0002" in f.message for f in findings))
        rust, _ = migration_lint.lint_rust(root)
        self.assertEqual(sorted(f.line for f in rust), [4, 5])
        code, _ = quiet(migration_lint.main, ["--root", str(root), "--pending", str(EMPTY_PENDING), "--lock-file", str(EMPTY_LOCK), "--exceptions", str(EMPTY_EXCEPTIONS), "--engine-generated", str(EMPTY_ENGINE)])
        self.assertEqual(code, 1)


class EngineFixedFiles(unittest.TestCase):
    """S-MIG-11: 엔진 생성 SQL을 그대로 고정한 파일은 등록부 SHA가 같을 때만 phase 머리·따옴표 이름을 건너뛴다."""

    TEXT = 'CREATE TABLE __SCHEMA__."audit_entries" (id uuid NOT NULL, CONSTRAINT "audit_entries_pkey" PRIMARY KEY (id));\n'
    PATH = "crates/services/svc/migrations/0003_audit_entries.sql"

    def registry(self, **change: str) -> dict:
        entry = {
            "path": self.PATH,
            "sha256": migration_lint.text_sha(self.TEXT),
            "source": "SequencedStream::create_table_sql",
            "reason": "시험",
            "expires": "2099-01-01",
            "approvedBy": "DB 담당",
        }
        entry.update(change)
        return {"files": [entry]}

    def test_matching_file_skips_only_header_and_quotes(self) -> None:
        fixed, problem = migration_lint.engine_fixed_status(self.PATH, self.TEXT.replace("\n", "\r\n"), self.registry())
        self.assertTrue(fixed)
        self.assertIsNone(problem)
        self.assertEqual({f.rule for f in migration_lint.lint_text(self.PATH, self.TEXT, "postgres", "svc", fixed)}, {"S-MONEY-2"})
        self.assertTrue({"S-MIG-4", "S-TYPE-6"} <= {f.rule for f in migration_lint.lint_text(self.PATH, self.TEXT, "postgres", "svc", False)})

    def test_changed_expired_or_incomplete_entry_gives_no_exception(self) -> None:
        # 내용이 다르면 예외만 없어지고(보통 규칙으로 판정 — 머리·따옴표가 잡음), 등록부 자체 문제는 따로 알린다.
        changed = self.TEXT + "-- 바뀜\n"
        self.assertEqual(migration_lint.engine_fixed_status(self.PATH, changed, self.registry()), (False, None))
        self.assertTrue({"S-MIG-4", "S-TYPE-6"} <= {f.rule for f in migration_lint.lint_text(self.PATH, changed, "postgres", "svc", False)})
        for registry, needle in ((self.registry(expires="2000-01-01"), "끝남"), (self.registry(approvedBy=""), "칸이 없음")):
            fixed, problem = migration_lint.engine_fixed_status(self.PATH, self.TEXT, registry)
            self.assertFalse(fixed)
            self.assertIn(needle, problem or "")
        self.assertEqual(migration_lint.engine_fixed_status("other.sql", self.TEXT, self.registry()), (False, None))

    def test_registered_monitoring_file_is_listed(self) -> None:
        registry = json.loads(migration_lint.ENGINE_GENERATED.read_text(encoding="utf-8"))
        for entry in registry["files"]:
            self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")
            self.assertTrue(entry["approvedBy"] and entry["source"] and entry["reason"])

    def test_restoring_fixed_file_is_not_a_rewrite(self) -> None:
        commits = [("e" * 40, "[MooKKo] 0003을 엔진 출력으로 되돌림", [("M", self.PATH)])]
        self.assertEqual(migration_lock.rewrite_findings(commits, set(), allowed=False, exempt=frozenset({self.PATH})), [])
        self.assertTrue(migration_lock.rewrite_findings(commits, set(), allowed=False))


class ServiceDdl(unittest.TestCase):
    """S-BND-7: 서비스 코드의 DDL은 막고, 기한 안의 예외 등록부에 오른 파일만 통과."""

    ROOT = FIXTURES / "repo-bad"
    PATH = "crates/services/svc/src/ddl.rs"

    def entry(self, **change: str) -> dict:
        item = {"id": "t", "paths": [self.PATH], "rule": "S-BND-7", "reason": "시험", "adr": f"{self.PATH} 시험",
                "condition": "시험", "expires": "2099-01-01", "approvedBy": "통합 담당"}
        item.update(change)
        return {"exceptions": [item]}

    def test_ddl_string_is_caught(self) -> None:
        found = migration_lint.lint_service_ddl(self.ROOT, {"exceptions": []})
        self.assertEqual(
            sorted((f.path, f.line) for f in found),
            sorted([(self.PATH, 2), (self.PATH, 4), (self.PATH, 5), (self.PATH, 6), (self.PATH, 7), ("crates/apps/mookko-svc/src/main.rs", 2)]),
        )

    def test_action_names_and_identifiers_are_not_ddl(self) -> None:
        # links 오탐(2026-10-30): "handle.revoke"를 REVOKE 문장으로 봄. 문장 머리의 SQL만 잡아야 함.
        self.assertEqual(migration_lint.lint_service_ddl(FIXTURES / "repo-good", {"exceptions": []}), [])

    def test_registered_exception_passes_until_expiry(self) -> None:
        self.assertEqual([f.path for f in migration_lint.lint_service_ddl(self.ROOT, self.entry())], ["crates/apps/mookko-svc/src/main.rs"])
        expired = migration_lint.lint_service_ddl(self.ROOT, self.entry(expires="2000-01-01"))
        self.assertTrue(any("기한" in f.message for f in expired) and any(f.path == self.PATH for f in expired))
        self.assertTrue(any("칸이 없음" in f.message for f in migration_lint.lint_service_ddl(self.ROOT, self.entry(approvedBy=""))))
        self.assertTrue(any("칸이 없음" in f.message for f in migration_lint.lint_service_ddl(self.ROOT, self.entry(adr=""))))
        self.assertTrue(any("근거 문서" in f.message for f in migration_lint.lint_service_ddl(self.ROOT, self.entry(adr="docs/없는-문서.md §1"))))

    def test_repository_registry_is_valid(self) -> None:
        registry = json.loads(migration_lint.EXCEPTIONS.read_text(encoding="utf-8"))
        _, problems = migration_lint.exception_paths(registry, today=None)
        self.assertEqual([p for p in problems if "칸이 없음" in p.message], [])


class EngineFixedEvidence(unittest.TestCase):
    """S-MIG-11 보강: 등록 파일마다 비교 시험이 있어야 하고, 코드로 적용하던 이관 ID를 새 파일로 바꾼 커밋은 등록·SHA가 맞아야 한다."""

    REPO = HERE.parents[2]

    def test_repository_registry_uses_add_generated(self) -> None:
        registry = json.loads(migration_lint.ENGINE_GENERATED.read_text(encoding="utf-8"))
        self.assertEqual(migration_lint.engine_fixed_tests(self.REPO, registry), [])
        self.assertTrue(all("test" not in e for e in registry["files"]), "옛 test 칸은 받지 않음")
        # add_generated를 쓰지 않는 가짜 서비스는 걸림(옛 test 칸을 줘도).
        fake = dict(registry["files"][0], path="crates/services/nosuch/migrations/0001_x.sql", test="crates/x.rs::f")
        self.assertTrue(migration_lint.engine_fixed_tests(self.REPO, {"files": [fake]}))

    def test_add_generated_in_code_passes(self) -> None:
        entry = {"path": "crates/services/svc/migrations/0001_accounts_and_ledger.sql"}
        self.assertEqual(migration_lint.engine_fixed_tests(FIXTURES / "repo-good", {"files": [entry]}), [])
        other = dict(entry, path="crates/services/svc/migrations/0002_accounts_add_region.sql")
        self.assertTrue(migration_lint.engine_fixed_tests(FIXTURES / "repo-good", {"files": [other]}), "add_generated에 그 파일 이름이 없으면 통과 아님")

    def test_code_id_to_file_change_in_history(self) -> None:
        since = migration_lock.load()["codeIdCheckSince"]
        now = migration_lint.code_id_to_file_findings(self.REPO, since)
        if now is None:
            self.skipTest("git 기록을 읽을 수 없음(WSL에서 Windows worktree) — 건너뜀(통과 아님)")
        self.assertEqual(now, [])
        # 기준 전 기록: 6a749ed가 코드로 적용하던 0003_audit_entries를 다른 내용 파일로 바꿈(QA 10차) — 새 검사가 잡아야 함.
        old = migration_lint.code_id_to_file_findings(self.REPO, migration_lock.load()["historyCheckedSince"]) or []
        self.assertTrue(any(p.endswith("0003_audit_entries.sql") and "6a749ed" in m for p, m in old), old)


class EngineHeaderRule(unittest.TestCase):
    """S-MIG-6: 엔진 이관기(migrate.rs header·outside_transaction)와 같은 머리 판정 — 앞 빈 줄 뒤 이어지는 `--` 줄 안 어디든."""

    def test_header_matches_engine(self) -> None:
        on = "-- mookko:transaction off"
        index = "CREATE INDEX CONCURRENTLY IF NOT EXISTS a ON s.t (x)"
        nl = chr(10)
        cases = [
            (nl.join([on, index]), True),
            (nl.join(["", "", "  -- mookko:phase expand", on, index]), True),
            (nl.join(["-- mookko:phase expand", "", on, index]), False),
            (nl.join(["CREATE TABLE t (id int);", on]), False),
            (nl.join(["-- mookko:phase expand", "CREATE TABLE t (id int);"]), False),
        ]
        for sql, expected in cases:
            with self.subTest(sql):
                self.assertEqual(migration_lint.outside_transaction(sql), expected)

    def test_engine_helpers_route_transaction_off(self) -> None:
        # include_str로 넣은 transaction off 파일은 add_concurrent_index·add_embedded·add_generated 중 하나가 있으면 통과.
        found = migration_lint.lint_embedded(FIXTURES / "repo-embedded")
        self.assertTrue(any(f.rule == "S-MIG-10" and "transaction off" in f.message for f in found))

    def test_add_generated_replaces_test_field(self) -> None:
        registry = {"files": [{"path": "crates/services/svc/migrations/0001_accounts_and_ledger.sql"}]}
        self.assertEqual(migration_lint.engine_fixed_tests(FIXTURES / "repo-good", registry), [])
        self.assertTrue(migration_lint.engine_fixed_tests(FIXTURES / "repo-bad", {"files": [dict(registry["files"][0])]}))


class EmbeddedMigrations(unittest.TestCase):
    """S-MIG-10·S-MONEY-2: 이관을 실행 파일에 넣어 쓰는 서비스의 ID·파일 대조, transaction off, append_only 지정."""

    def test_bad_service_is_caught(self) -> None:
        found = migration_lint.lint_embedded(FIXTURES / "repo-embedded")
        messages = " ".join(f"{f.rule} {f.message}" for f in found)
        self.assertEqual({f.rule for f in found}, {"S-MIG-10", "S-MONEY-2"}, messages)
        self.assertIn("`0001_audit`가 파일 이름", messages)
        self.assertIn("0002_index.sql`은 transaction off", messages)
        self.assertIn("0003_notes.sql", " ".join(f.path for f in found))
        self.assertIn("`audit_log`", messages)

    def test_good_service_passes(self) -> None:
        self.assertEqual(migration_lint.lint_embedded(FIXTURES / "repo-good"), [])


class MigrationLockSamples(unittest.TestCase):
    """S-MIG-1 출시 잠금: 출시 전에는 다시 써도 되고, 잠근 뒤에는 바꾸기·지우기·잠그지 않은 새 파일을 막는다."""

    ROOT = FIXTURES / "repo-good"
    DIR = "crates/services/svc/migrations"

    def locked(self) -> dict:
        import datetime

        return migration_lock.record(self.ROOT, {"launched": []}, self.DIR, "svc", "시험", datetime.date(2026, 11, 1))

    def test_prelaunch_has_no_lock(self) -> None:
        self.assertEqual(migration_lock.check(self.ROOT, {"launched": []}), [])

    def test_repository_lock_is_consistent(self) -> None:
        # 출시한 날에도 깨지지 않게: 실제 목록이 비었는지가 아니라 실제 저장소와 맞는지를 본다.
        self.assertEqual(migration_lock.check(HERE.parents[2], migration_lock.load()), [])
        self.assertIn("historyCheckedSince", migration_lock.load())

    def test_locked_unchanged_passes(self) -> None:
        data = self.locked()
        self.assertEqual(len(data["launched"][0]["files"]), 6)
        self.assertEqual(migration_lock.check(self.ROOT, data), [])

    def test_changed_missing_and_unlocked_files_fail(self) -> None:
        data = self.locked()
        files = data["launched"][0]["files"]
        files["0001_accounts_and_ledger.sql"] = "0" * 64
        files["0009_gone.sql"] = "0" * 64
        del files["0005_accounts_drop_tier.sql"]
        messages = " ".join(m for _, m in migration_lock.check(self.ROOT, data))
        self.assertIn("내용이 바뀜", messages)
        self.assertIn("없어짐", messages)
        self.assertIn("잠금 목록에 더함", messages)

    def test_checksum_matches_engine(self) -> None:
        import hashlib

        # 엔진: `__SCHEMA__` → `"svc"` 바꾼 뒤 줄 끝을 맞춰 SHA-256(migrate.rs add_dir·push).
        expected = hashlib.sha256('CREATE TABLE "svc".t (id int);\nSELECT 1;'.encode()).hexdigest()
        self.assertEqual(migration_lock.checksum("CREATE TABLE __SCHEMA__.t (id int);\r\nSELECT 1;", "svc"), expected)
        self.assertNotEqual(migration_lock.checksum("CREATE TABLE __SCHEMA__.t (id int);", "other"), expected)

    def test_record_keeps_old_values(self) -> None:
        import datetime

        data = self.locked()
        data["launched"][0]["files"]["0001_accounts_and_ledger.sql"] = "keep"
        again = migration_lock.record(self.ROOT, data, self.DIR, "svc", "다시", datetime.date(2026, 12, 1))
        self.assertEqual(again["launched"][0]["files"]["0001_accounts_and_ledger.sql"], "keep")
        self.assertEqual(again["launched"][0]["launchedAt"], "2026-11-01")

    def test_shrinking_the_lock_list_fails(self) -> None:
        data = self.locked()
        removed_file = json.loads(json.dumps(data))
        del removed_file["launched"][0]["files"]["0001_accounts_and_ledger.sql"]
        changed = json.loads(json.dumps(data))
        changed["launched"][0]["decidedBy"] = "다른 근거"
        self.assertEqual(migration_lock.shrink_findings([("a", {"launched": []}), ("b", data), ("c", data)]), [])
        self.assertTrue(migration_lock.shrink_findings([("b", data), ("c", {"launched": []})]))
        self.assertIn("0001_accounts_and_ledger.sql", " ".join(m for _, m in migration_lock.shrink_findings([("b", data), ("c", removed_file)])))
        self.assertIn("decidedBy", " ".join(m for _, m in migration_lock.shrink_findings([("b", data), ("c", changed)])))

    def test_rewrite_needs_commit_mark(self) -> None:
        path = "crates/services/svc/migrations/0001_accounts_and_ledger.sql"
        marked = f"[MooKKo] 고침\n\n{migration_lock.REWRITE_MARK} 0001_accounts_and_ledger.sql — 출시 전, 시험 DB뿐\n"
        commits = [
            ("a" * 40, "[MooKKo] 새 이관", [("A", "crates/services/svc/migrations/0006_new.sql")]),
            ("b" * 40, marked, [("M", path)]),
            ("c" * 40, "[MooKKo] 몰래 고침", [("M", path)]),
            ("d" * 40, "[MooKKo] 이름 바꿈", [("R100", "crates/services/svc/migrations/0001_renamed.sql"), ("D", path)]),
        ]
        # 사용자 결정으로 예외가 켜진 뒤: 표시가 있는 커밋만 통과.
        found = migration_lock.rewrite_findings(commits, set(), allowed=True)
        self.assertEqual(sorted(m[:13] for _, m in found), sorted(["커밋 " + "c" * 10, "커밋 " + "d" * 10, "커밋 " + "d" * 10]))
        self.assertEqual(migration_lock.rewrite_findings(commits, {"crates/services/svc/migrations"}, allowed=True), [])
        # 사용자 결정 전(지금): 표시가 있어도 다시 쓰기는 모두 실패, 새 파일 더하기는 통과.
        blocked = migration_lock.rewrite_findings(commits, set(), allowed=False)
        self.assertEqual(sorted(m[:13] for _, m in blocked), sorted(["커밋 " + "b" * 10, "커밋 " + "c" * 10, "커밋 " + "d" * 10, "커밋 " + "d" * 10]))

    def test_prelaunch_exception_needs_recorded_decision(self) -> None:
        self.assertFalse(migration_lock.prelaunch_allowed({}))
        self.assertFalse(migration_lock.prelaunch_allowed({"prelaunchRewrite": {"allowed": True, "decidedBy": None}}))
        self.assertTrue(migration_lock.prelaunch_allowed({"prelaunchRewrite": {"allowed": True, "decidedBy": "사용자 결정 2026-11-01 '…'"}}))


class DataClassSamples(unittest.TestCase):
    def test_docs(self) -> None:
        files = sorted((FIXTURES / "data-model").glob("*.md"))
        self.assertGreaterEqual(len(files), 3)
        for path in files:
            text = path.read_text(encoding="utf-8")
            got = {p.rule for p in data_classes.check_text(path.name, text)}
            with self.subTest(path.name):
                self.assertEqual(got, expected(text, r"<!-- expect: (.*?) -->"))

    def test_blind_index_needs_key_id_and_its_source(self) -> None:
        """엔진 `BlindIndex::compute`는 `{key_id, digest}`를 내므로 `<열>_bidx_kid`도 있어야 하고, 원래 열이 암호+색인이 아닌 색인 열은 잡는다."""
        path = FIXTURES / "data-model" / "bad-bidx.md"
        messages = [p.message for p in data_classes.check_text(path.name, path.read_text(encoding="utf-8"))]
        self.assertIn("`members.email`이 암호+색인인데 `email_bidx_kid` 열이 없음", messages)
        self.assertIn("`members.phone_bidx`의 원래 열 `phone`이 이 표에서 암호+색인이 아님", messages)
        self.assertIn("`members.phone_bidx_kid`의 원래 열 `phone`이 이 표에서 암호+색인이 아님", messages)
        self.assertEqual(len(messages), 3, messages)


class MigrationCoverage(unittest.TestCase):
    """S-SEC-1 이관 대조: 서비스 이관이 만드는 열(ADD COLUMN 포함)마다 그 서비스 설계서에 등급이 있어야 한다."""

    def test_complete_doc_passes(self) -> None:
        self.assertEqual(data_classes.migration_coverage(FIXTURES / "repo-good"), [])

    def test_missing_doc_and_column_fail(self) -> None:
        found = data_classes.migration_coverage(FIXTURES / "apply-bad")
        self.assertTrue(any("`audit_events`의 열 등급 표" in p.message for p in found), found)
        tables = migration_lint.created_tables(
            "-- mookko:phase expand\nSET LOCAL lock_timeout = '3s';\nALTER TABLE __SCHEMA__.accounts ADD COLUMN nickname text;\n",
            "postgres",
            "svc",
        )
        self.assertEqual(tables, {"accounts": ["nickname"]})


class PartitionedTables(unittest.TestCase):
    """S-PART-3: 이관은 파티션 부모만 만들고(달 파티션 `PARTITION OF` 금지), 부모는 서비스 코드가 엔진 `partitioned`로 적는다(E-DB-5)."""

    def test_good_repo_registers_parent(self) -> None:
        self.assertEqual(migration_lint.lint_partitioned(FIXTURES / "repo-good"), [])

    def test_unregistered_parent_is_caught(self) -> None:
        found = migration_lint.lint_partitioned(FIXTURES / "repo-partition-bad")
        messages = sorted(f.message for f in found)
        self.assertEqual({f.rule for f in found}, {"S-PART-3"}, found)
        self.assertEqual(len(found), 2, found)
        self.assertTrue(any("`events`" in m for m in messages), messages)
        self.assertTrue(any("`visits_202611`" in m and "visits_YYYYMM" in m for m in messages), messages)

    def test_strip_rust_comments_keeps_strings(self) -> None:
        text = "let u = \"https://x\"; /* a /* b */ c */ let q = '\"'; // dd\nr#\"// e\"#;"
        stripped = migration_lint.strip_rust_comments(text)
        self.assertIn('"https://x"', stripped)
        self.assertIn("let q = '\"';", stripped)
        self.assertIn('r#"// e"#', stripped)
        self.assertNotIn(" a ", stripped)
        self.assertNotIn("dd", stripped)
        self.assertEqual(stripped.count("\n"), 1)


class ReaderCoverage(unittest.TestCase):
    """S-SEC-9: 등급 `개인` 이상 열이 있는 표는 서비스 코드의 `READER_HIDDEN`·`READER_COLUMNS`로 읽기 계정에서 감춰야 한다(엔진 E-DB-12)."""

    def test_good_repo_hides_personal_columns(self) -> None:
        self.assertEqual(data_classes.reader_coverage(FIXTURES / "repo-good"), [])
        access = data_classes.reader_access(FIXTURES / "repo-good" / "crates" / "services" / "svc", FIXTURES / "repo-good")
        self.assertEqual(access.columns, {"accounts": ["account_id", "state", "created_at", "closed_at", "region"]})

    def test_rustfmt_layout_is_read(self) -> None:
        # rustfmt가 줄을 나누고 끝 쉼표를 붙인 모양(links 3c0689b가 알려 줌).
        text = "\n".join([
            "const READER_COLUMNS: &[(&str, &[&str])] = &[",
            "    (",
            '        "pages",',
            "        &[",
            '            "page_id",',
            '            "state",',
            "        ],",
            "    ),",
            "];",
            "fn f(m: M) { for (t, c) in READER_COLUMNS { m.reader_columns(t, c); } }",
        ])
        match = data_classes.READER_COLUMNS.search(text)
        self.assertIsNotNone(match)
        items = data_classes.READER_COLUMN_ITEM.findall(match.group(1))
        self.assertEqual([(t, data_classes.LITERAL.findall(c)) for t, c in items], [("pages", ["page_id", "state"])])

    def test_bad_settings_are_caught(self) -> None:
        found = [p.message for p in data_classes.reader_coverage(FIXTURES / "repo-reader-bad")]
        for needle in (
            "`READER_COLUMNS`가 `people.email`(등급 `개인` 이상)을 읽기 계정에 엶",
            "`reader_all_tables()`가 `notes`의 `개인` 이상 열(body)까지 엶",
            "`reader_all_tables()`가 `visits`의 `개인` 이상 열(ip_hash)까지 엶",
            "`READER_HIDDEN`을 적었지만 이 파일에서 그 상수를 `reader_hidden`으로 넘기지 않음",
            "읽기 계정 설정의 `missing_table`을 이관이 만들지 않음",
        ):
            self.assertTrue(any(needle in m for m in found), (needle, found))
        self.assertEqual(len(found), 5, found)


class ReaderClosedDefault(unittest.TestCase):
    """엔진 읽기 계정 기본은 닫힘(9f027fa): 열지 않은 개인 표는 괜찮고, `READER_TABLES`로 표째 열면 걸린다."""

    def test_closed_default(self) -> None:
        found = [p.message for p in data_classes.reader_coverage(FIXTURES / "repo-reader-closed") if "RECON_VIEWS" not in p.message]
        self.assertEqual(len(found), 1, found)
        self.assertIn("`READER_TABLES`가", found[0])
        self.assertIn("`notes`", found[0])


class ValidateDeploy(unittest.TestCase):
    """S-MIG-4 예외: 바로 앞 NOT VALID 제약을 VALIDATE만 하는 파일은 배포(같은·다음)와 근거를 머리나 설계서에 적는다."""

    def test_reason_in_header_or_doc(self) -> None:
        root = FIXTURES / "repo-validate"
        found = migration_lint.validate_deploy_findings(root, root / "crates" / "services" / "svc" / "migrations")
        self.assertEqual([f.path.rsplit("/", 1)[-1] for f in found], ["0003_items_kind_validate.sql"], found)

    def test_validate_only(self) -> None:
        ok = "\n".join(["-- mookko:phase migrate", "SET LOCAL lock_timeout = '3s';", "ALTER TABLE s.t VALIDATE CONSTRAINT c;", ""])
        mixed = "\n".join(["-- mookko:phase migrate", "ALTER TABLE s.t VALIDATE CONSTRAINT c;", "UPDATE s.t SET a = 1;", ""])
        self.assertEqual(migration_lint.validate_only(ok), {"c"})
        self.assertIsNone(migration_lint.validate_only(mixed))


class ReconViews(unittest.TestCase):
    """S-SEC-9 대사 계정(E-DB-15): `RECON_VIEWS`는 `recon_view`로 넘기고, 이관이 만든 보기여야 한다."""

    def test_good_repo(self) -> None:
        access = data_classes.reader_access(FIXTURES / "repo-good" / "crates" / "services" / "svc", FIXTURES / "repo-good")
        self.assertEqual(access.recon_views, {"accounts_recon"})
        self.assertEqual(data_classes.reader_coverage(FIXTURES / "repo-good"), [])

    def test_missing_view_is_caught(self) -> None:
        found = [p.message for p in data_classes.reader_coverage(FIXTURES / "repo-reader-closed")]
        self.assertTrue(any("`RECON_VIEWS`의 `notes_recon`" in m for m in found), found)


class EngineReaderCoverage(unittest.TestCase):
    """S-SEC-9 엔진 몫(QA 795bf8c): 엔진 표 설계서의 `개인` 이상 표는 엔진 코드의 `READER_HIDDEN`·`READER_COLUMNS`로 감춘다."""

    def test_hidden_engine_table_passes(self) -> None:
        self.assertEqual(data_classes.engine_reader_coverage(FIXTURES / "repo-engine-good"), [])

    def test_unhidden_engine_table_is_caught(self) -> None:
        found = [p.message for p in data_classes.engine_reader_coverage(FIXTURES / "repo-engine-bad")]
        self.assertEqual(len(found), 1, found)
        self.assertIn("엔진 표 `staff_sessions`", found[0])


class KeyTables(unittest.TestCase):
    """S-SEC-10(E-DB-8 키 파기): 감싼 행 키는 백업 보관이 짧은 키 DB(`keys/migrations`)에만, 키 DB에는 키 표만."""

    def test_key_dir_gets_its_own_schema(self) -> None:
        self.assertEqual(migration_lint.default_schema(Path("crates/services/svc/keys/migrations")), "svc_keys")
        self.assertEqual(migration_lint.owning_service(Path("crates/services/svc/keys/migrations")), "svc")
        self.assertEqual(migration_lint.default_schema(Path("crates/services/svc/migrations")), "svc")

    def test_good_key_table_passes(self) -> None:
        root = FIXTURES / "repo-good"
        self.assertEqual(migration_lint.lint_dir(root, root / "crates" / "services" / "svc" / "keys" / "migrations"), [])
        self.assertEqual(data_classes.migration_coverage(root), [])

    def test_wrapped_keys_outside_key_db_and_other_tables_inside_are_caught(self) -> None:
        root = FIXTURES / "repo-keys-bad"
        service = [f.message for f in migration_lint.lint_dir(root, root / "crates" / "services" / "svc" / "migrations") if f.rule == "S-SEC-10"]
        caught = {m.split("`")[1] for m in service}
        # QA 9344ed3 보통: `wrapped_key`가 아닌 이름(dek·row_key·data_key·wrapped_dek)과 이름 바꾸기(subject_key)도
        self.assertEqual(caught, {"profiles.profile_wrapped_key", "profiles.wrapped_key", "vaults.dek", "vaults.row_key", "vaults.data_key", "vaults.wrapped_dek", "blobs.subject_key"}, service)
        keys = [f.message for f in migration_lint.lint_dir(root, root / "crates" / "services" / "svc" / "keys" / "migrations") if f.rule == "S-SEC-10" or f.rule == "S-BND-5"]
        for needle in (
            "`row_keys.wrapped_key` 형식 `text` — `bytea`(§9.8 모양)",
            "키 표 `row_keys`에 `created_at timestamptz`가 없음(§9.8 모양)",
            "키 표 `row_keys`에 §9.8 모양 밖의 열: label",
            "키 DB에는 키 표(`wrapped_key bytea` 열)만 둠 — `notes`은 서비스 DB로",
            "키 DB 표 `row_keys`의 열을 더하거나 이름을 바꾸지 않음(`note`, §9.8 모양 고정)",
            # QA 9344ed3 보통: 키 DB에는 읽기·대사 계정이 없고, 앱에 UPDATE·TRUNCATE를 주지 않음
            "`svc_keys_ro`에게 GRANT: 자기 서비스 계정(svc_keys_app, svc_keys_migrate, svc_keys_owner)만",
            "`svc_keys_recon`에게 GRANT: 자기 서비스 계정(svc_keys_app, svc_keys_migrate, svc_keys_owner)만",
            "키 DB 표에는 UPDATE·TRUNCATE·TRIGGER·REFERENCES 권한을 주지 않음(앱은 SELECT·INSERT·DELETE만, §9.8)",
        ):
            self.assertIn(needle, keys)
        self.assertEqual(len(keys), 8, keys)

    def test_bytea_key_columns_must_be_hashes_in_the_design_doc(self) -> None:
        """서비스 DB의 bytea + key 낱말 열은 설계서 보호 `해시`이거나 `이름 예외`여야 한다(감싼 키를 다른 이름으로 두는 것)."""
        found = [p.message for p in data_classes.migration_coverage(FIXTURES / "repo-keys-bad") if p.rule == "S-SEC-10" and "digests" in p.message]
        self.assertEqual(len(found), 1, found)
        self.assertIn("`digests.blob_key`", found[0])
        # 이름에 key가 없는 bytea도 설계서 보호가 `암호`·`참조`면 잡음(QA 낮음 11-02), 해시 사슬 같은 `평문`은 통과
        payloads = [p.message for p in data_classes.migration_coverage(FIXTURES / "repo-keys-bad") if p.rule == "S-SEC-10" and "payloads" in p.message]
        self.assertEqual(len(payloads), 1, payloads)
        self.assertIn("`payloads.payload`(bytea)의 설계서 보호가 `암호`", payloads[0])
        self.assertEqual([p for p in data_classes.migration_coverage(FIXTURES / "repo-good") if p.rule == "S-SEC-10"], [])


class KeyMaterialCode(unittest.TestCase):
    """S-SEC-10 코드 쪽: 서비스 코드가 감싼 키를 손에 쥐면 설계서 등급과 상관없이 서비스 DB에 쓸 수 있으므로, 키 재료 API를 쓰지 않는다."""

    def test_service_code_using_key_material_api_is_caught(self) -> None:
        found = migration_lint.lint_key_material_code(FIXTURES / "repo-keys-bad")
        names = sorted(f.message.split("`")[1] for f in found if "키 재료 API" in f.message)
        self.assertEqual(names, ["WrappedKey", "WrappedKey", "generate_data_key", "insert_or_get", "unwrap_data_key"], [f.message for f in found])
        self.assertEqual({f.rule for f in found}, {"S-SEC-10"})
        # QA c63b644 D1: RowKeyStore가 돌려준 감싼 키를 형 이름 없이 `.to_bytes()`로 꺼냄 — src만, 시험의 HTTP 본문은 둠
        to_bytes = sorted((f.path.rsplit("/", 1)[-1], f.line) for f in found if "`.to_bytes()`" in f.message)
        self.assertEqual(to_bytes, [("lib.rs", 7), ("store_leak.rs", 5)], [f.message for f in found])
        # qa-design 11-03 2회 보통: WrappedKey 공개 필드(ciphertext·kek_id)로 꺼내는 길
        fields = sorted(f.message.split("`")[1] for f in found if "공개 필드" in f.message)
        self.assertEqual(fields, [".ciphertext", ".kek_id"], [f.message for f in found])

    def test_good_repo_and_engine_runtime_are_not_caught(self) -> None:
        self.assertEqual(migration_lint.lint_key_material_code(FIXTURES / "repo-good"), [])


class NameChecks(unittest.TestCase):
    """S-NAME-2(qa-design XC-D5): 이름 종류 열의 CHECK는 엔진 C3 `NameKind::sql_check` 글(등록부)과 같아야 한다. 등록부가 비면 보지 않음."""

    def test_registered_kind_must_match(self) -> None:
        import name_rules

        kinds, problems = name_rules.load(FIXTURES / "name-checks-sample.json")
        self.assertEqual(problems, [])
        found = name_rules.lint_name_checks(FIXTURES / "repo-names", kinds)
        got = sorted(f.message.split("`")[1] for f in found)
        # NULL을 받는 approved_by는 `열 IS NULL OR (등록 글)`(뒤 이관 NOT VALID)로 맞춰 통과, created_by만 잡힘
        self.assertEqual(got, ["actions.created_by"], [str(f) for f in found])

    def test_registry_sha_and_empty(self) -> None:
        import name_rules

        kinds, problems = name_rules.load(FIXTURES / "name-checks-bad-sha.json")
        self.assertEqual(kinds, [])
        self.assertIn("SHA가 다름", problems[0])
        kinds, problems = name_rules.load(name_rules.REGISTRY)
        self.assertEqual((kinds, problems), ([], []), "엔진 C3 전에는 비어 있음")
        self.assertEqual(name_rules.lint_name_checks(FIXTURES / "repo-names", []), [])


class TimeSources(unittest.TestCase):
    """S-TIME-1(qa-design XC-D3): 서비스 SQL 시각은 엔진 Clock의 `$now`, 새 ID는 앱 `TimeOrderedId`. S-TYPE-1 시간대 경고."""

    def test_db_clock_in_service_sql_and_migrations(self) -> None:
        import time_rules

        root = FIXTURES / "repo-time"
        found = time_rules.lint_time_sources(root, EMPTY_ENGINE)
        got = sorted((f.path.rsplit("/", 1)[-1], f.message.split("`")[1]) for f in found)
        self.assertEqual(got, [("0001_jobs.sql", "clock_timestamp()"), ("store.rs", "now()"), ("store.rs", "uuidv7()")], [str(f) for f in found])
        warnings = time_rules.timezone_warnings(root)
        self.assertEqual(len(warnings), 1, warnings)
        self.assertIn("store.rs:6", warnings[0])

    def test_audit_partition_needs_keep_days_and_archive(self) -> None:
        root = FIXTURES / "repo-time"
        found = [f for f in migration_lint.lint_partitioned(root) if "감사 파티션" in f.message]
        self.assertEqual(len(found), 1, [str(f) for f in found])
        self.assertIn("`audit_events`", found[0].message)

    def test_good_repo_has_no_db_clock(self) -> None:
        import time_rules

        self.assertEqual(time_rules.lint_time_sources(FIXTURES / "repo-good", EMPTY_ENGINE), [])


class ConstraintFunctions(unittest.TestCase):
    """QA 0d91d90 낮음: 파티션 부모 `ONLY` 제약은 lint가 먼저 막고, CHECK가 부르는 자기 스키마 함수는 IMMUTABLE·search_path(폴더 끝 상태)."""

    def test_only_on_parent_and_check_functions(self) -> None:
        root = FIXTURES / "repo-check-fn"
        found = migration_lint.lint_dir(root, root / "crates" / "services" / "svc" / "migrations")
        got = sorted((f.rule, f.message.split("`")[1]) for f in found if f.rule in ("S-MIG-2", "S-BND-6"))
        self.assertEqual(got, [("S-BND-6", "tags_nowhere"), ("S-BND-6", "tags_ok"), ("S-BND-6", "tags_public_path"), ("S-BND-6", "tags_volatile"), ("S-MIG-2", "events")], [f.message for f in found])
        # qa-design 2회 낮음: search_path 값은 pg_catalog·자기 스키마·pg_temp만, 자기 함수는 스키마를 붙여 부름
        self.assertTrue(any("스키마 없이 부름" in f.message and "`tags_ok`" in f.message for f in found), [f.message for f in found])
        self.assertTrue(migration_lint.search_path_ok("SET search_path = pg_catalog, pg_temp", "svc"))
        self.assertTrue(migration_lint.search_path_ok("SET search_path TO __SCHEMA__, pg_catalog AS $$", "svc"))
        self.assertFalse(migration_lint.search_path_ok("SET search_path = public", "svc"))
        self.assertFalse(migration_lint.search_path_ok("LANGUAGE sql IMMUTABLE", "svc"))


class EngineKeyDatabases(unittest.TestCase):
    """E-DB-17: 실행 파일이 있는 서비스의 키 DB 이관은 서비스 DB와 같은 `migrate` 실행에서 엔진이 돌린다(적용 시험의 설정 만들기)."""

    EXAMPLE = {
        "migrate": {
            "databases": {"svc": {"connection": {"kind": "postgres", "host": "h", "port": 1, "database": "svc", "user": "svc_migrate"}}},
            "keyDatabases": {"svc": {"connection": {"kind": "postgres", "host": "h", "port": 1, "database": "svc_keys", "user": "svc_keys_migrate"}, "ownerRole": "svc_keys_owner", "appRole": "svc_keys_app"}},
        }
    }

    def test_key_database_connection_goes_to_its_own_test_database(self) -> None:
        config = {"host": "127.0.0.1", "port": "5555"}
        settings = migration_apply.engine_settings(self.EXAMPLE, config, "db_main", "db_keys", Path("/run/secret"), data_classes.ReaderAccess())
        main = settings["migrate"]["databases"]["svc"]["connection"]
        keys = settings["migrate"]["keyDatabases"]["svc"]["connection"]
        self.assertEqual((main["database"], main["user"]), ("db_main", "svc_migrate"))
        self.assertEqual((keys["database"], keys["user"], keys["port"]), ("db_keys", "svc_keys_migrate", 5555))
        self.assertEqual(settings["migrate"]["keyDatabases"]["svc"]["appRole"], "svc_keys_app")
        self.assertEqual(self.EXAMPLE["migrate"]["keyDatabases"]["svc"]["connection"]["database"], "svc_keys", "예시는 그대로")
        with self.assertRaises(ValueError):
            migration_apply.engine_settings(self.EXAMPLE, config, "db_main", None, Path("/run/secret"), data_classes.ReaderAccess())

    def test_key_dir_without_key_databases_in_the_example_is_caught(self) -> None:
        root = FIXTURES / "repo-good"
        directory = root / "crates" / "services" / "svc" / "migrations"
        target = migration_apply.Target(directory, "crates/services/svc/migrations", "svc", "svc")
        problems: list[str] = []
        app = migration_apply.EngineApp(Path("mookko-svc"), {"migrate": {"databases": {}}})
        self.assertIsNone(migration_apply.engine_key_target(root, target, app, problems))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("`keyDatabases.svc`가 없음", problems[0])
        problems.clear()
        key = migration_apply.engine_key_target(root, target, migration_apply.EngineApp(Path("mookko-svc"), self.EXAMPLE), problems)
        self.assertEqual(problems, [])
        self.assertEqual((key.schema, key.rel), ("svc_keys", "crates/services/svc/keys/migrations"))


class PendingList(unittest.TestCase):
    def test_expiry(self) -> None:
        import datetime

        problems: list[str] = []
        items = pending.load(problems)
        self.assertEqual(problems, [])
        item = pending.Pending("a/b.sql", "x", datetime.date(2026, 1, 2), "r")
        self.assertTrue(pending.is_waived(pending.match([item], "a/b.sql"), datetime.date(2026, 1, 2)))
        self.assertFalse(pending.is_waived(pending.match([item], "a/b.sql"), datetime.date(2026, 1, 3)))
        self.assertIsNone(pending.match([item], "a/bc.sql"))
        limited = pending.Pending("svc", "x", datetime.date(2026, 1, 2), "r", ("S-SEC-9",))
        self.assertIs(pending.match([limited], "svc/migrations/0001_a.sql", "S-SEC-9"), limited)
        self.assertIsNone(pending.match([limited], "svc/migrations/0001_a.sql", "S-SEC-1"))
        self.assertIsNone(pending.match([limited], "svc/migrations/0001_a.sql"), "규칙을 넘기지 않는 검사(migration_lint)에는 효력 없음")
        for entry in items:
            self.assertLessEqual((entry.until - datetime.date(2026, 10, 30)).days, 60, f"{entry.path}: 유예는 60일 안")


@unittest.skipUnless(os.environ.get("MOOKKO_TEST_POSTGRES"), "MOOKKO_TEST_POSTGRES 없음 — 실제 PostgreSQL 적용 시험 건너뜀(통과 아님)")
class ApplySamples(unittest.TestCase):
    def test_good_repo_applies(self) -> None:
        code, out = quiet(migration_apply.main, ["--root", str(FIXTURES / "repo-good"), "--pending", str(EMPTY_PENDING)])
        self.assertEqual(code, 0, out)
        self.assertIn("이관 6개 적용", out)

    def test_reader_sees_personal_column_without_settings(self) -> None:
        """서비스 코드가 `reader_all_tables()`로 모두 열고 감추지 않으면, 적용 시험이 개인 등급 열을 잡는다."""
        original = data_classes.reader_access
        data_classes.reader_access = lambda crate, root: data_classes.ReaderAccess(all_tables=True)
        try:
            code, out = quiet(migration_apply.main, ["--root", str(FIXTURES / "repo-good"), "--pending", str(EMPTY_PENDING)])
        finally:
            data_classes.reader_access = original
        self.assertEqual(code, 1, out)
        self.assertIn("S-SEC-9 읽기 계정이 `accounts.email`(등급 `개인`)을 읽을 수 있음", out)
        self.assertNotIn("accounts.state", out)

    def test_recon_view_using_personal_column_is_caught(self) -> None:
        """대사 보기가 개인 등급 열을 쓰면(WHERE에만 써도) 잡고, 대사 계정은 원본 표를 못 읽는다."""
        original = data_classes.reader_access
        data_classes.reader_access = lambda crate, root: data_classes.ReaderAccess(recon_views={"accounts_recon", "accounts_contact"})
        try:
            code, out = quiet(migration_apply.main, ["--root", str(FIXTURES / "repo-good"), "--pending", str(EMPTY_PENDING)])
        finally:
            data_classes.reader_access = original
        self.assertEqual(code, 1, out)
        self.assertIn("S-SEC-9 대사 보기 `accounts_contact`가 `accounts.email`(등급 `개인`)을 씀", out)
        self.assertNotIn("대사 보기 `accounts_recon`", out)
        self.assertNotIn("대사 계정이 원본 표", out)

    def test_hidden_table_has_no_reader_privilege(self) -> None:
        """감춘 표는 grant 뒤 읽기 계정에 표·열 SELECT가 하나도 없어야 한다(has_table_privilege·has_column_privilege로 확인)."""
        original = data_classes.reader_access
        data_classes.reader_access = lambda crate, root: data_classes.ReaderAccess(hidden={"accounts"})
        try:
            code, out = quiet(migration_apply.main, ["--root", str(FIXTURES / "repo-good"), "--pending", str(EMPTY_PENDING)])
        finally:
            data_classes.reader_access = original
        self.assertEqual(code, 0, out)
        self.assertNotIn("S-SEC-9", out)

    def test_bad_repo_is_caught(self) -> None:
        code, out = quiet(migration_apply.main, ["--root", str(FIXTURES / "apply-bad"), "--pending", str(EMPTY_PENDING)])
        self.assertEqual(code, 1, out)
        for needle in (
            "S-MIG-8 적용 실패 42703",
            "S-MONEY-2 덧붙이기만 하는 `audit_events`에 막기 트리거 없음: TRUNCATE",
            "S-MONEY-2 `audit_log` UPDATE가 막히지 않음",
            "S-MONEY-2 `audit_log` DELETE가 막히지 않음",
            "S-TYPE `audit_events.amount` 형식 `numeric`",
            "S-MIG-3 `loose_rows`에 기본 키가 없음",
            "S-BND-2 앱 계정이 스키마에 CREATE",
            "S-SEC-3 `members.email_bidx` 형식 `text`",
            "S-SEC-3 `members.email_bidx`에 `CHECK (octet_length(email_bidx) = 32)`(이 글 그대로 따로 된 CHECK)가 없음",
            "S-SEC-3 `members.email_bidx`으로 시작하는 색인",
            "S-SEC-3 `members.email_bidx` 옆에 키 ID 열 `email_bidx_kid text`가 없음",
            "S-SEC-3 `members.phone_bidx`와 `phone_bidx_kid`의 NOT NULL이 다름",
            "S-SEC-3 `members.alias_bidx`와 `alias_bidx_kid`가 NULL을 받는데",
            "S-SEC-3 `members.alias_bidx_kid`에 `CHECK (alias_bidx_kid ~ '^[A-Za-z0-9_-]{1,32}$')`가 없음",
            # QA 9344ed3 낮음: CHECK는 정의 전체를 맞춤(`= 320`·`OR true`는 잡음)
            "S-SEC-3 `contacts.wide_bidx`에 `CHECK (octet_length(wide_bidx) = 32)`",
            "S-SEC-3 `contacts.wide_bidx_kid`에 `CHECK (wide_bidx_kid ~ '^[A-Za-z0-9_-]{1,32}$')`가 없음",
            # 키 DB(§9.8)
            "S-SEC-10 키 표 `row_keys`의 기본 키가 `(subject_id, purpose)`가 아님(지금 `subject_id`)",
            "S-SEC-10 키 DB에 표가 아닌 `row_key_counts`(v)",
            "S-SEC-10 키 DB에 표가 아닌 `noop`(function)",
            "S-SEC-10 키 DB에 `svcbad_keys_ro`이 스키마 USAGE를 가짐",
        ):
            self.assertIn(needle, out)
        for needle in ("`members.phone_bidx_kid`에 `CHECK", "`members.email_bidx_kid`에 `CHECK", "`contacts.note_bidx", "키 DB 앱 계정이"):
            self.assertNotIn(needle, out)


if __name__ == "__main__":
    if os.environ.get("MOOKKO_REQUIRE_TEST_POSTGRES") == "1" and not os.environ.get("MOOKKO_TEST_POSTGRES"):
        print("MOOKKO_REQUIRE_TEST_POSTGRES=1인데 MOOKKO_TEST_POSTGRES가 없음")
        sys.exit(1)
    unittest.main(verbosity=1)
