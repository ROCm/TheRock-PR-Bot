# Contributing to TheRock-PR-Bot

We are enthusiastic about contributions to our code and documentation. Please
feel free to file issues where documentation or functionality is lacking or,
even better, volunteer to contribute to help close these gaps!

______________________________________________________________________

> **Security vulnerabilities** — do not open a public GitHub Issue. See [SECURITY.md](SECURITY.md) for the private reporting process.

______________________________________________________________________

## Developer policies

These policies apply to all forms of activity and engagement in this project.

> [!IMPORTANT]
> AMD employees must also follow the ROCm open source software
> contributing policies at http://u.amd.com/rocm-oss-policies.

### Governance

This project is covered by the
[ROCm Project Governance](https://github.com/ROCm/ROCm/blob/develop/GOVERNANCE.md),
which also defines the code of conduct.

### Licensing

Code contributions to this project are covered under the terms of the
[LICENSE](LICENSE) file.

### Communication channels

Issue tracking, project planning, and code contributions are managed in GitHub.
We use an open-source toolchain so that workflows can be easily replicated in any
fork. We are also active on the
[AMD Developer Community Discord Server](https://discord.com/invite/amd-dev).

______________________________________________________________________

## About this repository

TheRock-PR-Bot is the central, reusable PR policy gate consumed by other ROCm
repositories. Because a change here affects every repository that calls the bot,
contributions should be made carefully and always accompanied by tests.

Key files:

- [`rocm_pr_bot/policy_check.py`](rocm_pr_bot/policy_check.py) — the bot logic.
- [`rocm_pr_bot/policy.yml`](rocm_pr_bot/policy.yml) — the shared policy definition.
- [`rocm_pr_bot/test_unittests.py`](rocm_pr_bot/test_unittests.py) — unit and integration tests.
- [`.github/workflows/rocm-pr-bot.yml`](.github/workflows/rocm-pr-bot.yml) — the reusable workflow callers consume.
- [`docs/ROCM_PR_BOT_FAQ.md`](docs/ROCM_PR_BOT_FAQ.md) — the user-facing policy FAQ.

> [!IMPORTANT]
> The reusable workflow runs under `pull_request_target` and must never check out
> or execute pull request head code. Do not add build/test/install steps that run
> PR-provided code, and do not change the checkout to the PR head — doing so would
> create a "pwn request" vulnerability.

______________________________________________________________________

## Development workflows

### Issue tracking

Before filing a new issue, search through
[existing issues](https://github.com/ROCm/TheRock-PR-Bot/issues) to avoid duplicates.

General guidelines:

- If your issue is already listed, upvote it and add a comment with reproduction details.
- When in doubt, file a new issue — we'll mark duplicates accordingly.
- Provide as much information as possible: a link to the affected PR, the results
  table comment, and the expected vs. actual behavior. This significantly reduces
  triage time.
- Check your issue regularly — we may ask follow-up questions.

### Local setup

The bot targets Python 3.11 and depends only on `requests` and `pyyaml`.

```bash
# Create a virtual environment and install dependencies
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip requests pyyaml pre-commit
```

### Running the tests

All policy logic is covered by unit and integration tests that run without any
network access or GitHub credentials, so you can iterate on policies locally
without pushing branches or running workflows:

```bash
python -m unittest rocm_pr_bot/test_unittests.py -v
# or
pytest rocm_pr_bot/test_unittests.py
```

Any change to `policy_check.py` or `policy.yml` must keep these tests green and,
where behavior changes, add or update tests to cover it.

### Code style

Follow the [ROCm/TheRock style guides](https://github.com/ROCm/TheRock/tree/main/docs/development/style_guides):

- [Bash style guide](https://github.com/ROCm/TheRock/blob/main/docs/development/style_guides/bash_style_guide.md)
- [GitHub Actions style guide](https://github.com/ROCm/TheRock/blob/main/docs/development/style_guides/github_actions_style_guide.md)
- [Python style guide](https://github.com/ROCm/TheRock/blob/main/docs/development/style_guides/python_style_guide.md)

### pre-commit checks

We use [pre-commit](https://pre-commit.com/) to run lint checks and formatters.
See the configured hooks in
[`.pre-commit-config.yaml`](.pre-commit-config.yaml). Please run pre-commit on
your commits before sending pull requests for review:

```bash
# Run locally on all files.
pre-commit run --all-files --show-diff-on-failure

# Install the git hook so it runs automatically on every commit.
pre-commit install
```

### Security scanners

Separately from the correctness checks above, this repository is scanned for
secrets, unsafe Python, workflow vulnerabilities, and misconfigurations. These
run in CI via [`pr-security-scan.yml`](.github/workflows/pr-security-scan.yml)
and [`weekly-security-scan.yml`](.github/workflows/weekly-security-scan.yml),
which call the shared
[`ROCm/rocm-security-gh`](https://github.com/ROCm/rocm-security-gh) reusable
workflow. The scanner configurations live under
[`.github/scan_tools_configs/`](.github/scan_tools_configs/).

______________________________________________________________________

## Pull Requests

All contributions should be submitted through a Pull Request (PR). This
repository's own PR Policy Bot runs on incoming PRs, so your PR description
should follow the policies it enforces (see
[`docs/ROCM_PR_BOT_FAQ.md`](docs/ROCM_PR_BOT_FAQ.md)).

Before submitting a PR:

- Ensure the change addresses an existing issue or documented requirement.
- Reference a tracking item in the PR description (a GitHub issue via `Fixes #123`,
  or a `JIRA ID` / `ISSUE ID` line).
- Add or update unit tests for any change to the bot logic or policy.
- Run `pre-commit run --all-files` and the test suite locally.
- Ensure all required GitHub Actions checks pass.
- Resolve review feedback before requesting approval.

PRs require:

- Approval from the appropriate [CODEOWNERS](.github/CODEOWNERS).
- Successful completion of required status checks.
- Compliance with repository security and quality requirements.

### Branching

- Do not commit directly to protected branches.
- Create a feature branch for all changes (e.g. `users/<username>/<feature-name>`).
- Keep changes focused and atomic.
- Rebase or update branches regularly to minimize merge conflicts.

### Commit messages

- Use clear and descriptive commit messages.

______________________________________________________________________

## Security requirements

Contributors must not:

- Commit secrets, tokens, passwords, or credentials.
- Introduce vulnerable dependencies without justification.
- Bypass security controls or required security reviews.

All contributions may be subject to automated security scanning.
