# TheRock-PR-Bot

[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)

TheRock-PR-Bot is the central, reusable pull request policy gate for ROCm
repositories. On every pull request it runs a set of deterministic checks —
PR description quality, forbidden files, unit tests, and required CI checks —
then posts a single results-table comment summarising what passed or failed and
manages a `Not ready to Review` label. It saves reviewer time by automating the
first-pass checks a human would otherwise perform manually.

The bot code lives here once and is consumed by other ROCm repositories through
a reusable GitHub Actions workflow (`workflow_call`), so policy is defined in a
single place and shared across repos.

> [!NOTE]
> This is **not an AI bot and does not use any LLMs**. It is a deterministic,
> rule-based checker driven entirely by [`policy.yml`](rocm_pr_bot/policy.yml).

For general information about the ROCm software platform, see the
[ROCm documentation](https://rocm.docs.amd.com/).

## Features

- A single self-updating results-table comment per pull request
- PR description validation (minimum length + JIRA/ISSUE/closing-keyword reference)
- Forbidden-file detection (keys, certificates, `.env`, etc.) — warning-only
- Unit-test presence check for source-code changes — warning-only
- `Not ready to Review` label management, driven only by the missing tracking reference
- Pass-through reporting of required CI checks (e.g. `pre-commit`) in the same table
- Automatic auto-approval of dependency "bump" PRs from configured bot accounts
- Opt-out per PR via the `@skip-pr-bot` tag
- Graceful degradation on fork PRs where write access is unavailable

## How it works

The bot is published as a reusable workflow,
[`rocm-pr-bot.yml`](.github/workflows/rocm-pr-bot.yml). A consuming repository
calls it from its own workflow, and the bot:

1. Reads all pull request data through the GitHub REST API (it never checks out
   or executes PR head code).
2. Loads the shared [`policy.yml`](rocm_pr_bot/policy.yml) and evaluates each
   policy in [`policy_check.py`](rocm_pr_bot/policy_check.py).
3. Snapshots the state of required check-runs (such as `pre-commit`) and renders
   them as Pass / Fail / Pending rows, without ever waiting or polling.
4. Posts or updates one results-table comment and adds/removes the
   `Not ready to Review` label.

The table refreshes automatically when a tracked CI workflow completes, via a
`workflow_run` trigger — no human push required.

> [!IMPORTANT]
> The workflow uses `pull_request_target` so it can comment on fork PRs. This is
> safe **only** because it never checks out or runs PR head code and installs
> only fixed, trusted dependencies. Do not add steps that execute PR-provided
> code or change the checkout to the PR head.

## Usage

### Consuming the bot from another repository

Add a caller workflow (for example `.github/workflows/rocm-pr-bot-scan.yml`) to
the repository you want to gate:

### Opting a PR out

Add `@skip-pr-bot` anywhere in the PR description to skip all checks. The bot
removes the `Not ready to Review` label and posts a short notice. Removing the
tag re-enables the checks on the next edit/push.

## Configuration

All policy is defined in [`rocm_pr_bot/policy.yml`](rocm_pr_bot/policy.yml),
including:

- `pr.description` — minimum length and accepted JIRA/ISSUE/closing-keyword patterns
- `pr.unit_tests` — which file extensions count as code and which patterns count as tests
- `pr.bump_bot_authors` — bot accounts whose PRs are auto-approved
- `diff.forbidden_paths` — file patterns flagged as forbidden
- `checks.required_check_runs` — default required check-run names (overridable per caller)

See the [Policy FAQ](docs/ROCM_PR_BOT_FAQ.md) for a per-check explanation of what
each policy means, why it exists, and how to resolve a failure.

## Development

The bot targets Python 3.11 and depends only on `requests` and `pyyaml`.

```bash
# Create a virtual environment and install dependencies
python -m venv .venv && source .venv/bin/activate
pip install --upgrade pip requests pyyaml

# Run the unit + integration tests
python -m unittest rocm_pr_bot/test_unittests.py -v
```

The tests exercise the validators and regex patterns directly, so policy changes
can be iterated locally without pushing branches or running workflows.

## Contributing

Contributions are welcome! Please read [`CONTRIBUTING.md`](CONTRIBUTING.md) for
the development workflow, coding standards, and how to submit pull requests. This
project follows the
[ROCm Project Governance](https://github.com/ROCm/ROCm/blob/develop/GOVERNANCE.md),
which also defines the code of conduct.

## Security

Please follow [SECURITY.md](SECURITY.md) for reporting vulnerabilities. Do not
open a public GitHub issue for security reports.

## License

This project is licensed under the terms described in the [LICENSE](LICENSE) file.
