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

        return migration_lock.record(self.ROOT, {"launched": []}, self.DIR, "시험", datetime.date(2026, 11, 1))

    def test_prelaunch_has_no_lock(self) -> None:
        self.assertEqual(migration_lock.check(self.ROOT, {"launched": []}), [])
        self.assertEqual(migration_lock.entries(migration_lock.load()), [], "출시 전에는 잠금 목록이 비어 있어야 함")

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
        self.assertEqual(migration_lock.checksum("SELECT 1;\r\nSELECT 2;"), migration_lock.checksum("SELECT 1;\nSELECT 2;"))

    def test_record_keeps_old_values(self) -> None:
        import datetime

        data = self.locked()
        data["launched"][0]["files"]["0001_accounts_and_ledger.sql"] = "keep"
        again = migration_lock.record(self.ROOT, data, self.DIR, "다시", datetime.date(2026, 12, 1))
        self.assertEqual(again["launched"][0]["files"]["0001_accounts_and_ledger.sql"], "keep")
        self.assertEqual(again["launched"][0]["launchedAt"], "2026-11-01")


class DataClassSamples(unittest.TestCase):
    def test_docs(self) -> None:
        files = sorted((FIXTURES / "data-model").glob("*.md"))
        self.assertGreaterEqual(len(files), 3)
        for path in files:
            text = path.read_text(encoding="utf-8")
            got = {p.rule for p in data_classes.check_text(path.name, text)}
            with self.subTest(path.name):
                self.assertEqual(got, expected(text, r"<!-- expect: (.*?) -->"))


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
            "S-MONEY-2 앱 계정이 `audit_events`에 UPDATE",
            "S-MONEY-2 덧붙이기만 하는 `audit_events`에 막기 트리거 없음: TRUNCATE",
            "S-TYPE `audit_events.amount` 형식 `numeric`",
            "S-MIG-3 `loose_rows`에 기본 키가 없음",
            "S-BND-2 앱 계정이 `loose_rows`에 TRUNCATE",
        ):
            self.assertIn(needle, out)


if __name__ == "__main__":
    if os.environ.get("MOOKKO_REQUIRE_TEST_POSTGRES") == "1" and not os.environ.get("MOOKKO_TEST_POSTGRES"):
        print("MOOKKO_REQUIRE_TEST_POSTGRES=1인데 MOOKKO_TEST_POSTGRES가 없음")
        sys.exit(1)
    unittest.main(verbosity=1)
