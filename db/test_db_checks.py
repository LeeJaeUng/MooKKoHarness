"""scripts/ci/db 검사의 표본 시험 (docs/policy/conventions/tools.md T-PY-7).

잡아야 할 표본은 기대한 규칙 번호로 정확히 잡히고, 통과해야 할 표본은 아무것도 걸리지 않아야 한다.
- fixtures/migrations/single/*.sql: 머리 `-- expect: 규칙, …` 또는 `(없음)`, 이름이 `ch_`면 ClickHouse 규칙
- fixtures/repo-good, repo-bad: 폴더 단위(이름·번호·Rust 문자열)
- fixtures/data-model/*.md: `<!-- expect: … -->`
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
        code, out = quiet(migration_lint.main, ["--root", str(FIXTURES / "repo-good"), "--pending", str(EMPTY_PENDING), "--lock-file", str(EMPTY_LOCK)])
        self.assertEqual(code, 0, out)

    def test_bad_repo_names_numbers_rust(self) -> None:
        root = FIXTURES / "repo-bad"
        findings = migration_lint.lint_dir(root, root / "crates" / "services" / "svc" / "migrations")
        self.assertIn("V4__d.sql", " ".join(f.path for f in findings))
        self.assertTrue(any("기대 0002" in f.message for f in findings))
        rust, _ = migration_lint.lint_rust(root)
        self.assertEqual(sorted(f.line for f in rust), [4, 5])
        code, _ = quiet(migration_lint.main, ["--root", str(root), "--pending", str(EMPTY_PENDING), "--lock-file", str(EMPTY_LOCK)])
        self.assertEqual(code, 1)


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
        found = migration_lock.rewrite_findings(commits, set())
        self.assertEqual(sorted(m[:13] for _, m in found), sorted(["커밋 " + "c" * 10, "커밋 " + "d" * 10, "커밋 " + "d" * 10]))
        self.assertEqual(migration_lock.rewrite_findings(commits, {"crates/services/svc/migrations"}), [])


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
        for entry in items:
            self.assertLessEqual((entry.until - datetime.date(2026, 10, 30)).days, 60, f"{entry.path}: 유예는 60일 안")


@unittest.skipUnless(os.environ.get("MOOKKO_TEST_POSTGRES"), "MOOKKO_TEST_POSTGRES 없음 — 실제 PostgreSQL 적용 시험 건너뜀(통과 아님)")
class ApplySamples(unittest.TestCase):
    def test_good_repo_applies(self) -> None:
        code, out = quiet(migration_apply.main, ["--root", str(FIXTURES / "repo-good")])
        self.assertEqual(code, 0, out)
        self.assertIn("이관 5개 적용", out)

    def test_bad_repo_is_caught(self) -> None:
        code, out = quiet(migration_apply.main, ["--root", str(FIXTURES / "apply-bad")])
        self.assertEqual(code, 1, out)
        for needle in (
            "S-MIG-8 적용 실패 42703",
            "S-MONEY-2 덧붙이기만 하는 `audit_events`에 막기 트리거 없음: TRUNCATE",
            "S-MONEY-2 `audit_log`의 막기 트리거 함수 `allow_change`가 거부하지 않음",
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
