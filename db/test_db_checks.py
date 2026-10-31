"""scripts/ci/db 검사의 표본 시험 (docs/policy/conventions/tools.md T-PY-7).

잡아야 할 표본은 기대한 규칙 번호로 정확히 잡히고, 통과해야 할 표본은 아무것도 걸리지 않아야 한다.
- fixtures/migrations/single/*.sql: 머리 `-- expect: 규칙, …` 또는 `(없음)`, 이름이 `ch_`면 ClickHouse 규칙
- fixtures/repo-good, repo-bad: 폴더 단위(이름·번호·Rust 문자열)
- fixtures/data-model/*.md: `<!-- expect: … -->`
- fixtures/repo-reader-bad: 읽기 계정 감추기(S-SEC-9)
- fixtures/repo-partition-bad: 파티션 부모를 엔진에 적기(S-PART-3)
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

    def test_repository_registry_has_comparison_tests(self) -> None:
        registry = json.loads(migration_lint.ENGINE_GENERATED.read_text(encoding="utf-8"))
        self.assertEqual(migration_lint.engine_fixed_tests(self.REPO, registry), [])
        # 깨진 항목은 add_generated를 쓰지 않는 가짜 서비스로(실제 서비스가 add_generated로 옮겨도 시험이 그대로 서게).
        fake = dict(registry["files"][0], path="crates/services/nosuch/migrations/0001_x.sql")
        broken = {"files": [dict(fake, test=registry["files"][0].get("test", "a.rs::f") + "_missing")]}
        self.assertTrue(migration_lint.engine_fixed_tests(self.REPO, broken))
        self.assertTrue(migration_lint.engine_fixed_tests(self.REPO, {"files": [dict(fake, test="")]}))

    def test_add_generated_needs_no_test_field(self) -> None:
        entry = {"path": "crates/services/svc/migrations/0001_accounts_and_ledger.sql", "test": ""}
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
        registry = {"files": [{"path": "crates/services/svc/migrations/0001_accounts_and_ledger.sql", "test": ""}]}
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
        self.assertEqual(len(data["launched"][0]["files"]), 5)
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
        self.assertEqual([(f.rule, "`events`" in f.message) for f in found], [("S-PART-3", True)], found)


class ReaderCoverage(unittest.TestCase):
    """S-SEC-9: 등급 `개인` 이상 열이 있는 표는 서비스 코드의 `READER_HIDDEN`·`READER_COLUMNS`로 읽기 계정에서 감춰야 한다(엔진 E-DB-12)."""

    def test_good_repo_hides_personal_columns(self) -> None:
        self.assertEqual(data_classes.reader_coverage(FIXTURES / "repo-good"), [])
        access = data_classes.reader_access(FIXTURES / "repo-good" / "crates" / "services" / "svc", FIXTURES / "repo-good")
        self.assertEqual(access.columns, {"accounts": ["account_id", "state", "created_at", "closed_at", "region"]})

    def test_bad_settings_are_caught(self) -> None:
        found = [p.message for p in data_classes.reader_coverage(FIXTURES / "repo-reader-bad")]
        for needle in (
            "`READER_COLUMNS`가 `people.email`(등급 `개인` 이상)을 읽기 계정에 엶",
            "`notes`의 `개인` 이상 열(body)을 읽기 계정에서 감추지 않음",
            "`visits`의 `개인` 이상 열(ip_hash)을 읽기 계정에서 감추지 않음",
            "`READER_HIDDEN`을 적었지만 이 파일에서 그 상수를 `reader_hidden`으로 넘기지 않음",
            "읽기 계정 설정의 `missing_table`을 이관이 만들지 않음",
        ):
            self.assertTrue(any(needle in m for m in found), (needle, found))
        self.assertEqual(len(found), 5, found)


class EngineReaderCoverage(unittest.TestCase):
    """S-SEC-9 엔진 몫(QA 795bf8c): 엔진 표 설계서의 `개인` 이상 표는 엔진 코드의 `READER_HIDDEN`·`READER_COLUMNS`로 감춘다."""

    def test_hidden_engine_table_passes(self) -> None:
        self.assertEqual(data_classes.engine_reader_coverage(FIXTURES / "repo-engine-good"), [])

    def test_unhidden_engine_table_is_caught(self) -> None:
        found = [p.message for p in data_classes.engine_reader_coverage(FIXTURES / "repo-engine-bad")]
        self.assertEqual(len(found), 1, found)
        self.assertIn("엔진 표 `staff_sessions`", found[0])


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
        self.assertIn("이관 5개 적용", out)

    def test_reader_sees_personal_column_without_settings(self) -> None:
        """서비스 코드에 읽기 계정 설정이 없으면 엔진처럼 표 전체 SELECT가 되고, 적용 시험이 개인 등급 열을 잡는다."""
        original = data_classes.reader_access
        data_classes.reader_access = lambda crate, root: data_classes.ReaderAccess()
        try:
            code, out = quiet(migration_apply.main, ["--root", str(FIXTURES / "repo-good"), "--pending", str(EMPTY_PENDING)])
        finally:
            data_classes.reader_access = original
        self.assertEqual(code, 1, out)
        self.assertIn("S-SEC-9 읽기 계정이 `accounts.email`(등급 `개인`)을 읽을 수 있음", out)
        self.assertNotIn("accounts.state", out)

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
        ):
            self.assertIn(needle, out)


if __name__ == "__main__":
    if os.environ.get("MOOKKO_REQUIRE_TEST_POSTGRES") == "1" and not os.environ.get("MOOKKO_TEST_POSTGRES"):
        print("MOOKKO_REQUIRE_TEST_POSTGRES=1인데 MOOKKO_TEST_POSTGRES가 없음")
        sys.exit(1)
    unittest.main(verbosity=1)
