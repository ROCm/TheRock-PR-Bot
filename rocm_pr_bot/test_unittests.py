# Copyright Advanced Micro Devices, Inc.
# SPDX-License-Identifier: MIT
"""
Unit + integration tests for policy_check.py.

These let us iterate on policies WITHOUT pushing branches or running workflows:
  • Unit tests   — exercise individual validators / regex patterns.
  • Integration  — feed blobs of [branch, title, description, files] through
                   the higher-level ensure_* functions.

Run locally:
    python -m unittest .github/therock_pr_bot/test_unittests.py -v
    # or
    pytest .github/therock_pr_bot/test_unittests.py
"""

import os
import re
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

# The bot code lives in .github/therock_pr_bot/. Make it importable and record
# where the shipped policy.yml lives, regardless of the working directory.
THIS_DIR = Path(__file__).resolve().parent
BOT_DIR = THIS_DIR.parent / "rocm_pr_bot"
POLICY_PATH = BOT_DIR / "policy.yml"
sys.path.insert(0, str(BOT_DIR))

import policy_check as pc

# ----------------------------- helpers ---------------------------------------

_ISSUE_PATTERNS = [
    r"(?im)^\s*JIRA\s*ID\s*[:\-]?\s*(#?\d+|[A-Z][A-Z0-9]+-\d+|https?:\/\/\S+)",
    r"(?im)^\s*ISSUE\s*ID\s*[:\-]?\s*(#?\d+|[A-Z][A-Z0-9]+-\d+|https?:\/\/\S+)",
    # JIRA/ISSUE ID on a separate line (blank lines + trailing spaces allowed).
    r"(?im)^[ \t]*JIRA[ \t]+ID[ \t]*\r?\n[ \t\r\n]*([A-Z][A-Z0-9]+-\d+)",
    r"(?im)^[ \t]*ISSUE[ \t]+ID[ \t]*\r?\n[ \t\r\n]*([A-Z][A-Z0-9]+-\d+|\d+)",
    (
        r"(?im)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b\s*:?\s*"
        r"(?:[A-Za-z0-9._\-]+\/[A-Za-z0-9._\-]+)?#\d+"
    ),
    # Bare GitHub issue reference, e.g. #123
    r"(?m)(?:^|\s)#\d+\b",
    # GitHub issue URL
    r"(?i)https?:\/\/github\.com\/[^\/\s]+\/[^\/\s]+\/issues\/\d+",
]

_CHECKLIST_PATTERNS = [
    r"(?im)^\s*-\s*\[[xX]\]\s*.*contributing guidelines",
]


def make_policy(**overrides: Any) -> pc.Policy:
    """Build a Policy with sensible defaults; override any field per-test.

    Independent of policy.yml so regex/validator behaviour can be pinned even
    if the shipped config changes. Note: title and branch-name policies have
    been removed — Policy no longer carries any title/branch fields.
    """
    defaults: dict[str, Any] = {
        "description_min_length": 30,
        "description_issue_patterns": [re.compile(p) for p in _ISSUE_PATTERNS],
        "description_checklist_patterns": [re.compile(p) for p in _CHECKLIST_PATTERNS],
        "block_draft": True,
        "forbidden_paths": ["**/*.pem", "**/.env", "**/id_rsa"],
        "unit_test_code_extensions": [".py", ".cpp"],
        "unit_test_patterns": [
            "test_*",
            "testing_*",
            "*_test.*",
            "*_tests.*",
            "*_gtest.*",
            "Test*",
            "**/test/gtest/**",
        ],
        "unit_test_exempt_paths": [],
        "bump_bot_authors": ["assistant-librarian", "systems-assistant", "dependabot"],
        "required_checks": ["pre-commit"],
        "precommit_failure_comment": None,
    }
    defaults.update(overrides)
    return pc.Policy(**defaults)


def make_file(
    filename: str,
    status: str = "modified",
    additions: int = 0,
    deletions: int = 0,
    changes: int | None = None,
) -> dict[str, Any]:
    return {
        "filename": filename,
        "status": status,
        "additions": additions,
        "deletions": deletions,
        "changes": changes if changes is not None else additions + deletions,
    }


# ----------------------------- PR description --------------------------------


class DescriptionTests(unittest.TestCase):
    def test_too_short(self) -> None:
        policy = make_policy()
        e: list[str] = []
        pc.ensure_pr_description(policy, "short", e)
        self.assertTrue(any("too short" in x for x in e))

    def test_missing_issue_reference(self) -> None:
        # No checklist patterns so only the reference check fires.
        policy = make_policy(description_checklist_patterns=[])
        e: list[str] = []
        pc.ensure_pr_description(policy, "A long enough description with no ref.", e)
        self.assertTrue(any("must reference a JIRA ID" in x for x in e))

    def test_issue_reference_in_comment_does_not_pass(self) -> None:
        # Isolate reference detection (skip min-length and checklist).
        policy = make_policy(
            description_min_length=0, description_checklist_patterns=[]
        )
        multiline_comment = """<!--
Fixes #1234
-->"""
        multiple_comments = """This description has no visible issue reference.
<!-- Related to #1234 -->
Some visible text between the comments.
<!-- https://github.com/ROCm/TheRock/issues/5678 -->"""
        for body in [
            "<!-- GitHub issue: https://github.com/ROCm/TheRock/issues/1234 -->",
            multiline_comment,
            multiple_comments,
        ]:
            with self.subTest(body=body):
                e: list[str] = []
                pc.ensure_pr_description(policy, body, e)
                self.assertTrue(any("must reference a JIRA ID" in x for x in e))

    def test_issue_reference_variants_pass(self) -> None:
        # Isolate reference detection (skip min-length and checklist).
        policy = make_policy(
            description_min_length=0, description_checklist_patterns=[]
        )
        for body in [
            "JIRA ID : TESTAUTO-6039",
            "JIRA ID - #330",
            "JIRA ID #330",
            "ISSUE ID : TESTUTO-3334",
            "ISSUE ID - TESTAUTO-3433",
            "ISSUE ID : https://github.com/org/repo/issues/1234",
            # Multiline format with JIRA ID
            "JIRA ID\nROCM-25757",
            "JIRA ID\n\nROCM-25757",
            "jira id\nROCM-25757",  # case-insensitive
            # Trailing spaces after label + blank line before key
            "JIRA ID  \n\nAIRUNTIME-2352",
            "JIRA ID\t\n\n\nROCM-25757",
            "JIRA ID  \r\n\r\nROCM-25757",  # CRLF line endings
            # Multiline format with ISSUE ID
            "ISSUE ID\nAIRUNTIME-2352",
            "ISSUE ID\n\nAIRUNTIME-2352",
            "issue id\nAIRUNTIME-2352",  # case-insensitive
            "ISSUE ID  \n\nAIRUNTIME-2352",  # trailing spaces + blank line
        ]:
            with self.subTest(body=body):
                e: list[str] = []
                pc.ensure_pr_description(policy, body, e)
                self.assertEqual(e, [])

    def test_closing_keyword_variants_pass(self) -> None:
        # GitHub closing keywords are also accepted as a tracking ref.
        policy = make_policy(
            description_min_length=0, description_checklist_patterns=[]
        )
        for body in [
            "Closes #10",
            "Fixes octo-org/octo-repo#100",
            "Resolves #10",
            "resolves #123",
            "resolves octo-org/octo-repo#100",
            "Closes: #10",
            "CLOSES #10",
            "CLOSES: #10",
            "This change fixes the bug.\nFixes #4321\n",
        ]:
            with self.subTest(body=body):
                e: list[str] = []
                pc.ensure_pr_description(policy, body, e)
                self.assertEqual(e, [])

    def test_plain_github_issue_refs_pass(self) -> None:
        # Bare '#<number>' and GitHub issue URLs are accepted without a keyword.
        policy = make_policy(
            description_min_length=0, description_checklist_patterns=[]
        )
        for body in [
            "Related to #123",
            "#4321",
            "See https://github.com/ROCm/TheRock/issues/6043",
        ]:
            with self.subTest(body=body):
                e: list[str] = []
                pc.ensure_pr_description(policy, body, e)
                self.assertEqual(e, [])

    def test_reference_inside_larger_body(self) -> None:
        policy = make_policy(description_checklist_patterns=[])
        body = "This change fixes the parser.\n\nISSUE ID : TESTUTO-3334\n"
        e: list[str] = []
        pc.ensure_pr_description(policy, body, e)
        self.assertEqual(e, [])

    def test_checklist_ticked_passes(self) -> None:
        policy = make_policy(description_min_length=0, description_issue_patterns=[])
        body = "- [x] Look over the contributing guidelines at https://..."
        e: list[str] = []
        pc.ensure_pr_description(policy, body, e)
        self.assertEqual(e, [])

    def test_checklist_unticked_fails(self) -> None:
        policy = make_policy(description_min_length=0, description_issue_patterns=[])
        body = "- [ ] Look over the contributing guidelines at https://..."
        e: list[str] = []
        pc.ensure_pr_description(policy, body, e)
        self.assertTrue(any("Checklist" in x or "checklist" in x for x in e))


# ----------------------------- forbidden files -------------------------------


class ForbiddenFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = make_policy()

    def _errs(self, files: list[dict[str, Any]]) -> list[str]:
        e: list[str] = []
        pc.ensure_no_forbidden_files(self.policy, files, e)
        return e

    def test_flags_secret_files(self) -> None:
        for name in ["secret.pem", "config/.env", "deploy/id_rsa"]:
            with self.subTest(name=name):
                self.assertTrue(self._errs([make_file(name)]))

    def test_allows_normal_files(self) -> None:
        files = [make_file("src/app.py"), make_file("README.md")]
        self.assertEqual(self._errs(files), [])

    def test_removed_forbidden_file_is_ignored(self) -> None:
        self.assertEqual(self._errs([make_file("secret.pem", status="removed")]), [])

    def test_forbidden_files_is_warning_only_row(self) -> None:
        # The Forbidden Files row is warning-only: passed=True + warn=True when a
        # forbidden file is present, so it never blocks the workflow.
        result = pc.CheckResult(
            "Forbidden Files",
            "⛔",
            passed=True,
            details=["Forbidden file present in PR: `secret.pem`"],
            warn=True,
        )
        marker = "<!-- test -->"
        body = pc.build_policy_table_comment([result], marker, ready=True)
        self.assertIn("⚠️ Warning", body)
        self.assertIn("secret.pem", body)
        # Forbidden Files is warning-only — it never adds the label.


# ----------------------------- unit tests check ------------------------------


class UnitTestRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = make_policy()

    def _errs(self, files: list[dict[str, Any]]) -> list[str]:
        e: list[str] = []
        pc.ensure_unit_tests(self.policy, files, e)
        return e

    def test_code_without_test_fails(self) -> None:
        self.assertTrue(self._errs([make_file("src/module.py")]))

    def test_code_with_test_passes(self) -> None:
        files = [make_file("src/module.py"), make_file("tests/test_module.py")]
        self.assertEqual(self._errs(files), [])

    def test_docs_only_passes(self) -> None:
        files = [make_file("README.md"), make_file("config/settings.yml")]
        self.assertEqual(self._errs(files), [])

    def test_source_anywhere_requires_test(self) -> None:
        # Unit tests are required for source code placed ANYWHERE in the repo —
        # no folder is special. Each non-test source file, on its own, fails.
        srcs = [
            "policy_check.py",
            "src/app.py",
            "deep/nested/dir/module.py",
            ".github/therock_pr_bot/policy_check.py",
            "lib/foo.cpp",
            # 'test.py' is NOT a test file — 'test_*' needs the 'test_' prefix.
            "test.py",
        ]
        for src in srcs:
            # On Windows fnmatch is case-insensitive, so 'test.py' wrongly
            # matches the 'Test*' pattern and is treated as a test file. The
            # production code runs on Linux CI (case-sensitive), where this
            # holds; skip only this one case off-Linux.
            if src == "test.py" and os.name == "nt":
                continue
            with self.subTest(src=src):
                self.assertTrue(self._errs([make_file(src)]))

    def test_test_file_anywhere_satisfies_requirement(self) -> None:
        # A real test_* file in ANY folder satisfies the requirement.
        for test_path in [
            "tests/test_module.py",
            "deep/nested/test_module.py",
            "any/where/module_test.py",
        ]:
            with self.subTest(test_path=test_path):
                files = [make_file("src/module.py"), make_file(test_path)]
                self.assertEqual(self._errs(files), [])

    def test_test_prefix_capitalized_satisfies_requirement(self) -> None:
        # The 'Test*' pattern recognises capitalised test files (e.g.
        # TestUtils.cpp, TestParser.py) as valid test files.
        for test_path in [
            "TestUtils.cpp",
            "tests/TestParser.py",
            "deep/nested/TestFeature.cpp",
        ]:
            with self.subTest(test_path=test_path):
                files = [make_file("src/module.py"), make_file(test_path)]
                self.assertEqual(self._errs(files), [])

    def test_path_based_pattern_satisfies_requirement(self) -> None:
        # Patterns containing '/' are matched against the full file path, not
        # just the basename. This allows entire test directories to be
        # recognised as test locations even if their files use no special naming
        # convention (e.g. hip-tests files named after the API they test:
        # atomicAdd.cc, acquire_release.cc).
        policy = make_policy(
            unit_test_patterns=[
                "test_*",
                "*_test.*",
                "**/test/gtest/**",
                "projects/hip-tests/**",
            ]
        )
        errs: list[str] = []

        # A .cpp file under projects/hip-tests/ satisfies the requirement even
        # though its basename ('atomicAdd.cpp') matches no name-based pattern.
        files = [
            make_file("projects/clr/hipamd/src/hip_memory.cpp"),
            make_file("projects/hip-tests/catch/unit/memory/atomicAdd.cpp"),
        ]
        pc.ensure_unit_tests(policy, files, errs)
        self.assertEqual(errs, [])

    def test_path_based_pattern_code_only_fails(self) -> None:
        # A path-based pattern only helps when the PR actually touches a file
        # under that path. Source changes with no matching test path still fail.
        policy = make_policy(
            unit_test_patterns=[
                "test_*",
                "*_test.*",
                "projects/hip-tests/**",
            ]
        )
        errs: list[str] = []
        files = [make_file("projects/clr/hipamd/src/hip_memory.cpp")]
        pc.ensure_unit_tests(policy, files, errs)
        self.assertTrue(errs)

    def test_unit_test_is_warning_only_row(self) -> None:
        # The Unit Test row is warning-only: passed=True + warn=True when a
        # code file has no accompanying test, so it never blocks the workflow.
        result = pc.CheckResult(
            "Unit Test", "🧪", passed=True, details=["missing test"], warn=True
        )
        marker = "<!-- test -->"
        body = pc.build_policy_table_comment([result], marker, ready=True)
        self.assertIn("⚠️ Warning", body)
        self.assertIn("missing test", body)


# ----------------------------- draft + bump ----------------------------------


class DraftAndBumpTests(unittest.TestCase):
    def test_draft_blocked_when_enabled(self) -> None:
        policy = make_policy(block_draft=True)
        e: list[str] = []
        pc.ensure_pr_not_draft(policy, True, e)
        self.assertTrue(e)

    def test_draft_allowed_when_not_draft(self) -> None:
        policy = make_policy(block_draft=True)
        e: list[str] = []
        pc.ensure_pr_not_draft(policy, False, e)
        self.assertEqual(e, [])

    def test_bump_author_detection(self) -> None:
        policy = make_policy()
        self.assertTrue(pc.is_bump_pr(policy, "assistant-librarian"))
        self.assertTrue(pc.is_bump_pr(policy, "assistant-librarian[bot]"))
        self.assertTrue(pc.is_bump_pr(policy, "SYSTEMS-ASSISTANT"))
        self.assertTrue(pc.is_bump_pr(policy, "dependabot"))
        self.assertTrue(pc.is_bump_pr(policy, "dependabot[bot]"))
        self.assertFalse(pc.is_bump_pr(policy, "some-human"))
        self.assertFalse(pc.is_bump_pr(policy, ""))


# ----------------------------- skip tag --------------------------------------


class SkipTagTests(unittest.TestCase):
    def test_skip_tag_detected(self) -> None:
        for body in [
            "@skip-pr-bot",
            "Please skip this one @skip-pr-bot thanks",
            "line one\n@SKIP-PR-BOT\nline three",  # case-insensitive
            "Skipping: @Skip-PR-Bot",
        ]:
            with self.subTest(body=body):
                self.assertTrue(pc.pr_wants_skip(body))

    def test_skip_tag_absent(self) -> None:
        for body in [
            "",
            "A normal description with a JIRA ID : ABC-1",
            "email me at skip-pr-bot@example.com",  # not the @-prefixed tag
            "@skip-pr-bottling",  # not a whole-word match
        ]:
            with self.subTest(body=body):
                self.assertFalse(pc.pr_wants_skip(body))

    def test_skip_tag_ignored_inside_comment(self) -> None:
        # Tags inside HTML comments (e.g. a PR template) do not trigger a skip.
        self.assertFalse(pc.pr_wants_skip("<!-- @skip-pr-bot -->"))


# ----------------------------- integration -----------------------------------


class IntegrationBlobTests(unittest.TestCase):
    """Feed full [title, description, files] blobs through validators."""

    def setUp(self) -> None:
        self.policy = make_policy()

    def _evaluate(
        self, *, title: str, body: str, files: list[dict[str, Any]]
    ) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}

        e: list[str] = []

        pc.ensure_pr_description(self.policy, body, e)
        out["title_desc"] = e

        e = []
        pc.ensure_no_forbidden_files(self.policy, files, e)
        out["forbidden"] = e

        e = []
        pc.ensure_unit_tests(self.policy, files, e)
        out["unit"] = e
        return out

    def test_fully_compliant_pr(self) -> None:
        result = self._evaluate(
            title="feat(ci): add policy unit tests",
            body=(
                "Adds unit tests for the policy checker.\n"
                "ISSUE ID : TESTUTO-3334\n"
                "- [x] Look over the contributing guidelines at https://..."
            ),
            files=[make_file("src/feature.py"), make_file("tests/test_feature.py")],
        )
        for key, errs in result.items():
            with self.subTest(check=key):
                self.assertEqual(errs, [])

    def test_fully_noncompliant_pr(self) -> None:
        result = self._evaluate(
            title="wip",
            body="too short",
            files=[make_file("secret.pem"), make_file("src/module.py")],
        )
        self.assertTrue(result["title_desc"])
        self.assertTrue(result["forbidden"])
        self.assertTrue(result["unit"])

    def test_docs_only_pr_is_compliant(self) -> None:
        result = self._evaluate(
            title="docs: clarify contributing guide",
            body=(
                "Improves the contributing docs.\n"
                "JIRA ID : DOCS-42\n"
                "- [x] Look over the contributing guidelines at https://..."
            ),
            files=[make_file("docs/CONTRIBUTING.md"), make_file("README.md")],
        )
        for key, errs in result.items():
            with self.subTest(check=key):
                self.assertEqual(errs, [])


# ----------------------------- load_policy -----------------------------------


class LoadPolicyTests(unittest.TestCase):
    """Smoke-test the shipped policy.yml so config drift is caught."""

    def test_load_shipped_policy(self) -> None:
        policy_path = THIS_DIR / "policy.yml"
        if not policy_path.exists():
            self.skipTest("policy.yml not present next to tests")
        policy = pc.load_policy(policy_path)
        # required_check_runs is now empty in the SHARED policy.yml by default:
        # each caller repo supplies its own check-RUN name(s) via the
        # `required_check_runs` input in rocm-pr-bot-scan.yml (handled in main()
        # through the REQUIRED_CHECK_RUNS env override). policy.yml no longer
        # hard-codes "pre-commit" because that name is repo-specific.
        self.assertEqual(policy.required_checks, [])
        # Title policy has been removed from policy.yml — the description
        # min-length is the meaningful text-length gate now.
        self.assertGreaterEqual(policy.description_min_length, 0)

    def test_multiline_jira_issue_patterns_loaded(self) -> None:
        """Verify multiline JIRA/ISSUE ID patterns are in the loaded policy."""
        policy_path = THIS_DIR / "policy.yml"
        if not policy_path.exists():
            self.skipTest("policy.yml not present next to tests")
        policy = pc.load_policy(policy_path)

        # Should have at least 5 issue reference patterns (inline + multiline + closing keywords + bare refs + urls)
        self.assertGreaterEqual(len(policy.description_issue_patterns), 5)

        # Verify multiline patterns work by testing them directly
        multiline_jira_pattern = None
        multiline_issue_pattern = None

        for pat in policy.description_issue_patterns:
            if pat.search("JIRA ID\nROCM-25757"):
                multiline_jira_pattern = pat
            if pat.search("ISSUE ID\nAIRUNTIME-2352"):
                multiline_issue_pattern = pat

        self.assertIsNotNone(
            multiline_jira_pattern, "Multiline JIRA ID pattern not found in policy"
        )
        self.assertIsNotNone(
            multiline_issue_pattern, "Multiline ISSUE ID pattern not found in policy"
        )

    def test_unit_test_patterns_exclude_unit_glob(self) -> None:
        """Verify 'unit/**' pattern is NOT in the loaded unit_test_patterns."""
        policy_path = THIS_DIR / "policy.yml"
        if not policy_path.exists():
            self.skipTest("policy.yml not present next to tests")
        policy = pc.load_policy(policy_path)

        # Per team lead request, 'unit/**' was removed from unit_test_patterns.
        # Test files are now recognized ONLY by basename (test_*, *_test.*, Test*).
        self.assertNotIn("unit/**", policy.unit_test_patterns)
        # Verify the allowed patterns ARE present.
        self.assertIn("test_*", policy.unit_test_patterns)
        self.assertIn("*_test.*", policy.unit_test_patterns)
        self.assertIn("*_tests.*", policy.unit_test_patterns)
        self.assertIn("*_gtest.*", policy.unit_test_patterns)
        self.assertIn("Test*", policy.unit_test_patterns)
        self.assertIn("**/test/gtest/**", policy.unit_test_patterns)


# ----------------------------- PR number resolution --------------------------


class ResolvePrNumberFromShaTests(unittest.TestCase):
    """Cover PR-number resolution used on check_run events (empty PR list)."""

    def test_empty_sha_returns_none(self) -> None:
        self.assertIsNone(pc.resolve_pr_number_from_sha("o", "r", "", "tok"))

    def test_prefers_open_pr_with_matching_head_sha(self) -> None:
        payload = [
            {"number": 11, "state": "closed", "head": {"sha": "abc"}},
            {"number": 22, "state": "open", "head": {"sha": "abc"}},
        ]
        with mock.patch.object(pc, "gh_get", return_value=payload):
            self.assertEqual(pc.resolve_pr_number_from_sha("o", "r", "abc", "tok"), 22)

    def test_falls_back_to_first_open_pr(self) -> None:
        payload = [
            {"number": 33, "state": "open", "head": {"sha": "zzz"}},
            {"number": 44, "state": "open", "head": {"sha": "yyy"}},
        ]
        with mock.patch.object(pc, "gh_get", return_value=payload):
            # No exact head match for "abc" -> first OPEN pr wins.
            self.assertEqual(pc.resolve_pr_number_from_sha("o", "r", "abc", "tok"), 33)

    def test_no_pulls_returns_none(self) -> None:
        with mock.patch.object(pc, "gh_get", return_value=[]):
            self.assertIsNone(pc.resolve_pr_number_from_sha("o", "r", "abc", "tok"))

    def test_api_error_returns_none(self) -> None:
        with mock.patch.object(pc, "gh_get", side_effect=RuntimeError("boom")):
            self.assertIsNone(pc.resolve_pr_number_from_sha("o", "r", "abc", "tok"))


# ----------------------------- required checks -------------------------------


class RequiredCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = make_policy(required_checks=["pre-commit"])

    def test_missing_check_reported(self) -> None:
        missing, failing, _ = pc.summarize_required_checks(self.policy, [])
        self.assertIn("pre-commit", missing)
        self.assertEqual(failing, [])

    def test_failing_check_reported(self) -> None:
        runs = [{"name": "pre-commit", "conclusion": "failure"}]
        missing, failing, _ = pc.summarize_required_checks(self.policy, runs)
        self.assertEqual(missing, [])
        self.assertTrue(any("pre-commit=failure" in f for f in failing))

    def test_pending_check_not_failing(self) -> None:
        runs = [{"name": "pre-commit", "conclusion": None}]
        missing, failing, _ = pc.summarize_required_checks(self.policy, runs)
        self.assertEqual(missing, [])
        self.assertEqual(failing, [])

    def test_success_check_passes(self) -> None:
        runs = [{"name": "pre-commit", "conclusion": "success"}]
        missing, failing, _ = pc.summarize_required_checks(self.policy, runs)
        self.assertEqual(missing, [])
        self.assertEqual(failing, [])


# -------- pre-commit resolution via Contents + Check-Runs (no actions:read) --


class PrecommitRowResolutionTests(unittest.TestCase):
    """Cover resolve_precommit_row — built on ALREADY-GRANTED permissions.

    Two data sources, neither needing `actions: read`:
      • Contents API (requests.get) → does .github/workflows/pre-commit.yml exist?
        404 → "Not applicable" (e.g. rocm-systems). We mock requests.get.
      • Check Runs API → the list is passed straight into resolve_precommit_row,
        so tests just hand it the check_runs they want. Matching is by NAME
        against the built-in candidates ("pre-commit", "Run hooks") plus any
        caller-supplied names.
    """

    def _mock_contents(self, *, present: bool):
        """Patch requests.get used by repo_has_precommit_workflow.

        present=True  → 200 (file exists)
        present=False → 404 (file absent → Not applicable)
        """
        resp = mock.Mock()
        resp.status_code = 200 if present else 404
        return mock.patch.object(pc.requests, "get", return_value=resp)

    def _resolve(
        self,
        *,
        present: bool,
        check_runs: list[dict[str, Any]],
        extra_names: list[str] | None = None,
    ) -> pc.CheckResult:
        with self._mock_contents(present=present):
            return pc.resolve_precommit_row(
                "o", "r", "deadbeef", "tok", check_runs, extra_names or []
            )

    def test_no_workflow_file_is_not_applicable(self) -> None:
        # rocm-systems case: no pre-commit.yml → ✅ Pass + "Not applicable" note,
        # regardless of any check-runs present.
        row = self._resolve(present=False, check_runs=[])
        self.assertEqual(row.name, "pre-commit")
        self.assertTrue(row.passed)
        self.assertFalse(row.pending)
        self.assertIn("Not applicable", row.note or "")

    def test_file_present_no_matching_check_is_pending(self) -> None:
        # Workflow exists but no pre-commit check-run on the commit yet.
        row = self._resolve(
            present=True,
            check_runs=[{"name": "some-other-check", "conclusion": "success"}],
        )
        self.assertTrue(row.pending)
        self.assertFalse(row.passed)

    def test_check_still_running_is_pending(self) -> None:
        row = self._resolve(
            present=True, check_runs=[{"name": "pre-commit", "conclusion": None}]
        )
        self.assertTrue(row.pending)

    def test_check_success_passes(self) -> None:
        row = self._resolve(
            present=True, check_runs=[{"name": "pre-commit", "conclusion": "success"}]
        )
        self.assertTrue(row.passed)
        self.assertFalse(row.pending)

    def test_check_failure_fails(self) -> None:
        row = self._resolve(
            present=True, check_runs=[{"name": "pre-commit", "conclusion": "failure"}]
        )
        self.assertFalse(row.passed)
        self.assertFalse(row.pending)
        self.assertTrue(any("failure" in d for d in row.details))

    def test_matches_run_hooks_name(self) -> None:
        # TheRock-PR-Bot names its job "Run hooks" → check-run is "Run hooks".
        # The built-in candidate set still matches it (no caller config needed).
        row = self._resolve(
            present=True, check_runs=[{"name": "Run hooks", "conclusion": "success"}]
        )
        self.assertTrue(row.passed)

    def test_caller_extra_name_matches(self) -> None:
        # A repo whose check uses a NOVEL name supplies it via required_checks;
        # resolve_precommit_row receives it as extra_names and matches it.
        row = self._resolve(
            present=True,
            check_runs=[{"name": "lint-and-format", "conclusion": "success"}],
            extra_names=["lint-and-format"],
        )
        self.assertTrue(row.passed)

    def test_contents_404_wins_over_present_check(self) -> None:
        # Even if a check named "pre-commit" somehow exists, a 404 on the
        # workflow file means the repo does not run pre-commit → Not applicable.
        row = self._resolve(
            present=False, check_runs=[{"name": "pre-commit", "conclusion": "failure"}]
        )
        self.assertTrue(row.passed)
        self.assertIn("Not applicable", row.note or "")


class BuildCheckResultRowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = make_policy(required_checks=["pre-commit"])

    def _row(self, runs: list[dict[str, Any]]) -> pc.CheckResult:
        rows = pc.build_check_results(self.policy, runs)
        return next(r for r in rows if r.name == "pre-commit")

    def test_missing_is_pending(self) -> None:
        row = self._row([])
        self.assertTrue(row.pending)
        self.assertFalse(row.passed)

    def test_success_row_passes(self) -> None:
        row = self._row([{"name": "pre-commit", "conclusion": "success"}])
        self.assertTrue(row.passed)
        self.assertFalse(row.pending)

    def test_failure_row_fails(self) -> None:
        row = self._row([{"name": "pre-commit", "conclusion": "failure"}])
        self.assertFalse(row.passed)
        self.assertFalse(row.pending)

    def test_include_self_adds_bot_row(self) -> None:
        rows = pc.build_check_results(self.policy, [], include_self=True)
        self.assertTrue(any(r.name == "therock-pr-bot" for r in rows))


# -------------------- per-caller required_check_runs override ----------------


class ParseCheckRunNamesTests(unittest.TestCase):
    """Cover _parse_check_run_names — the per-caller REQUIRED_CHECK_RUNS parser.

    policy.yml is shared across repos and cannot know each repo's job-level
    check-RUN name (e.g. "Run hooks"), so the caller workflow passes the names
    via the REQUIRED_CHECK_RUNS env var. Unset → keep policy.yml's list; set
    (even empty) → override it, where empty means "this repo has no required
    check-runs" so no permanently-pending row is shown.
    """

    def test_none_returns_none(self) -> None:
        # Unset env var → None → caller keeps whatever policy.yml specifies.
        self.assertIsNone(pc._parse_check_run_names(None))

    def test_empty_string_returns_empty_list(self) -> None:
        # Explicitly set but empty → [] (NOT None): repo opts out of all
        # required check-runs. Distinct from None so main() still overrides.
        for raw in ["", "   ", "\n", " , , \n "]:
            with self.subTest(raw=repr(raw)):
                self.assertEqual(pc._parse_check_run_names(raw), [])

    def test_single_name(self) -> None:
        self.assertEqual(pc._parse_check_run_names("Run hooks"), ["Run hooks"])

    def test_comma_separated(self) -> None:
        self.assertEqual(
            pc._parse_check_run_names("Run hooks, lint, build"),
            ["Run hooks", "lint", "build"],
        )

    def test_newline_separated(self) -> None:
        self.assertEqual(
            pc._parse_check_run_names("Run hooks\nlint\nbuild"),
            ["Run hooks", "lint", "build"],
        )

    def test_mixed_separators_and_whitespace(self) -> None:
        # Commas and newlines mix; surrounding whitespace and blank entries are
        # stripped. Internal spaces in a check name are preserved ("Run hooks").
        self.assertEqual(
            pc._parse_check_run_names("  Run hooks ,\n lint ,\n\n build \n"),
            ["Run hooks", "lint", "build"],
        )


class RequiredCheckRunsOverrideTests(unittest.TestCase):
    """Cover how REQUIRED_CHECK_RUNS replaces Policy.required_checks in main().

    main() is integration-heavy (network), so rather than drive it end-to-end we
    assert the override SEMANTICS on a Policy via dataclasses.replace — the exact
    operation main() performs when the env var is set.
    """

    def test_override_replaces_required_checks(self) -> None:
        policy = make_policy(required_checks=["pre-commit"])
        names = pc._parse_check_run_names("Run hooks")
        self.assertIsNotNone(names)
        overridden = pc.replace(policy, required_checks=names)
        self.assertEqual(overridden.required_checks, ["Run hooks"])
        # Original policy is untouched (frozen dataclass → new instance).
        self.assertEqual(policy.required_checks, ["pre-commit"])

    def test_empty_override_yields_no_required_checks(self) -> None:
        # A repo with no pre-commit passes "" → [] → no required-check rows, so
        # nothing is ever stuck as ⏳ Pending.
        policy = make_policy(required_checks=["pre-commit"])
        names = pc._parse_check_run_names("")
        overridden = pc.replace(policy, required_checks=names)
        self.assertEqual(overridden.required_checks, [])
        rows = pc.build_check_results(overridden, [])
        self.assertEqual(rows, [])

    def test_unset_override_keeps_policy_list(self) -> None:
        # None means "do not override" — main() leaves policy.required_checks
        # exactly as policy.yml defined it.
        policy = make_policy(required_checks=["pre-commit"])
        names = pc._parse_check_run_names(None)
        self.assertIsNone(names)
        # main() only calls replace() when names is not None, so the policy is
        # used as-is here.
        self.assertEqual(policy.required_checks, ["pre-commit"])

    def test_overridden_name_drives_check_row(self) -> None:
        # End-to-end-ish: after overriding to "Run hooks", a check-run of that
        # name flips the row to passed (proving the name match now works).
        policy = make_policy(required_checks=pc._parse_check_run_names("Run hooks"))
        runs = [{"name": "Run hooks", "conclusion": "success"}]
        row = next(
            r for r in pc.build_check_results(policy, runs) if r.name == "Run hooks"
        )
        self.assertTrue(row.passed)
        self.assertFalse(row.pending)


# ----------------------------- new tests -------------------------------------


class NewPolicyCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = make_policy()

    def test_strip_markdown_comments(self) -> None:
        # The comment text is removed in place; surrounding newlines are kept, so
        # a comment on its own line leaves a blank line behind.
        for body, expected in [
            ("", ""),
            ("plain text", "plain text"),
            ("<!-- comment -->", ""),
            ("line 1\n<!-- comment -->\nline 2", "line 1\n\nline 2"),
            (
                "Before comment\n<!-- Comment with JIRA ID: TEST-123 -->\nAfter",
                "Before comment\n\nAfter",
            ),
            (
                "Before comment\n<!-- Comment with ISSUE ID: TEST-123 -->\nAfter",
                "Before comment\n\nAfter",
            ),
        ]:
            with self.subTest(body=body):
                self.assertEqual(pc._strip_markdown_comments(body), expected)

    def test_matches_forbidden(self) -> None:
        # _matches_forbidden(filename, pattern) takes a SINGLE glob pattern.
        self.assertTrue(pc._matches_forbidden("config/.env", "**/config/*.env"))
        self.assertTrue(pc._matches_forbidden("path/to/secret.txt", "**/secret.txt"))
        # '**/<x>' also matches a root-level file.
        self.assertTrue(pc._matches_forbidden(".env", "**/.env"))
        self.assertFalse(pc._matches_forbidden("README.md", "**/secret.txt"))

    def test_is_test_file(self) -> None:
        # _is_test_file(filename, patterns) takes an iterable of glob patterns.
        patterns = ["test_*", "*_test.*", "**/test/gtest/**"]
        self.assertTrue(pc._is_test_file("test_module.py", patterns))
        self.assertTrue(pc._is_test_file("src/module_test.py", patterns))
        self.assertTrue(
            pc._is_test_file("projects/miopen/test/gtest/unit_conv.cpp", patterns)
        )
        self.assertFalse(pc._is_test_file("module.py", patterns))

    def test_pr_has_code_files(self) -> None:
        policy = make_policy()
        files_with_code = [make_file("src/app.py"), make_file("README.md")]
        files_without_code = [make_file("docs/CONTRIBUTING.md")]

        # pr_has_code_files(policy, pr_files)
        self.assertTrue(pc.pr_has_code_files(policy, files_with_code))
        self.assertFalse(pc.pr_has_code_files(policy, files_without_code))

    def test_build_bump_pr_results(self) -> None:
        # build_bump_pr_results(policy) returns an all-pass set of rows for an
        # automated dependency bump PR — including the configured required
        # checks and the bot's own row.
        policy = make_policy(required_checks=["pre-commit"])
        results = pc.build_bump_pr_results(policy)

        names = [r.name for r in results]
        self.assertIn("PR Description", names)
        self.assertIn("Forbidden Files", names)
        self.assertIn("Unit Test", names)
        self.assertIn("pre-commit", names)
        self.assertIn("therock-pr-bot", names)

        # Every row passes and carries the bump note.
        self.assertTrue(all(r.passed for r in results))
        self.assertTrue(all(r.note for r in results))

    def test_table_rendering_order(self) -> None:
        # Rows render in TABLE_ORDER regardless of input order: the fixed order
        # is PR Description -> Forbidden Files -> Unit Test.
        results = [
            pc.CheckResult("Unit Test", "🧪", passed=True, details=[]),
            pc.CheckResult(
                "Forbidden Files", "⛔", passed=False, details=[], warn=True
            ),
            pc.CheckResult("PR Description", "📜", passed=True, details=[]),
        ]
        marker = "<!-- t -->"
        body = pc.build_policy_table_comment(results, marker, ready=True)

        # Check order: PR Description -> Forbidden Files -> Unit Test.
        # Compile with DOTALL so '.*' spans the newlines between table rows
        # (assertRegex has no flags argument).
        order_re = re.compile(r"PR Description.*Forbidden Files.*Unit Test", re.DOTALL)
        self.assertRegex(body, order_re)

    def test_table_rendering_pending(self) -> None:
        # Test rendering of a pending check in the policy table.
        result = pc.CheckResult(
            "Unit Test", "🧪", passed=True, details=[], pending=True
        )
        marker = "<!-- test -->"
        body = pc.build_policy_table_comment([result], marker, ready=True)

        # A pending row shows the "⏳ Pending" status in its Status column.
        self.assertIn("🧪 **Unit Test**", body)
        self.assertIn("⏳ Pending", body)

    def test_table_rendering_note(self) -> None:
        # A note renders only when passed via `note=` (details are not shown for
        # a passing row); the row still displays the icon + name.
        result = pc.CheckResult(
            "Note", "ℹ️", passed=True, details=[], note="This is a note."
        )
        marker = "<!-- test -->"
        body = pc.build_policy_table_comment([result], marker, ready=True)

        # Notes should appear with the 'ℹ️' icon
        self.assertIn("ℹ️ **Note**", body)
        self.assertIn("This is a note.", body)

    def test_table_rendering_pending_only_shows_waiting(self) -> None:
        # When a required check is still pending (and nothing has failed), the
        # table must NOT claim "0 policy check(s) failed". It should render the
        # waiting heading/footer instead.
        result = pc.CheckResult(
            "pre-commit",
            "🔎",
            passed=False,
            details=["⏳ Still running…"],
            pending=True,
        )
        marker = "<!-- test -->"
        body = pc.build_policy_table_comment([result], marker, ready=False)

        self.assertIn("Waiting on Checks", body)
        self.assertNotIn("0 policy check(s) failed", body)
        self.assertNotIn("Action Required", body)


if __name__ == "__main__":
    unittest.main()
