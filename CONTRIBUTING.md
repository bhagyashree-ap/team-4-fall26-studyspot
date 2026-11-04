# Contributing to StudySpot

Thank you for taking the time to contribute. StudySpot welcomes bug fixes, features,
documentation improvements, tests, and code review.

Before starting, confirm the issue's public contract and definition of done. Shared contract
or root configuration changes affect multiple parts of the project, so ask the affected owners
to review them.

## Project structure

```text
studyspot/
├── .github/
│   ├── ISSUE_TEMPLATE/          # Bug and feature request templates
│   ├── workflows/               # GitHub Actions checks and documentation publishing
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── branch-protection.json   # Required checks and protected-branch settings
├── contracts/                   # Shared schemas and representative API data
├── data/                        # NYC Open Data ingestion and normalized spots snapshot
│   ├── fixtures/                # Trimmed upstream records, so the importer tests need no network
│   ├── ingest.py
│   ├── spots.json
│   └── test_ingest.py
├── docs/
│   ├── source/                  # MyST Markdown and Sphinx configuration
│   ├── pyproject.toml
│   └── uv.lock
├── infra/                       # AWS deployment: Terraform and its helper scripts
│   ├── terraform/
│   ├── scripts/
│   └── README.md
├── src/
│   ├── backend/                 # Django application, its tests, and both entry points
│   │   ├── studyspot/           # Settings, URLs, health, error envelope, middleware
│   │   ├── spots/               # Model, routes, serializers, migrations, loader, tests
│   │   ├── manage.py
│   │   ├── pyproject.toml
│   │   └── uv.lock
│   └── frontend/                # SvelteKit application and frontend tests
│       ├── src/
│       ├── static/
│       ├── package.json
│       └── bun.lock
├── tests/e2e/                   # Tests against a running deployment
├── compose.yaml                 # Local frontend, API, and Postgres services
└── justfile                     # Canonical development commands
```

Tests live with the behavior they verify: frontend tests belong beside frontend components,
backend tests belong in `src/backend/spots/tests/` beside the app they cover, data-import tests
belong in `data/`, and tests that need a running deployment belong in `tests/e2e/`.

The shared contract in `contracts/` is the boundary between the frontend, API, data importer,
database, and search implementation. Coordinate changes to it with every affected owner. Tool
configuration stays with its relevant package; repository-wide commands belong in `justfile`.

## Making changes

### Create a branch

Feature work starts from `develop`, not `main`. Update `develop`, then create a short-lived branch
for one issue:

```shell
git switch develop
git pull origin develop
git switch -c feat/short-description
```

Use a short, descriptive branch name. Useful prefixes include `feat/`, `fix/`, `docs/`, `test/`,
and `refactor/`.

### Keep the change focused

- Stay within the issue's ownership boundary when possible.
- Add dependencies only when the change uses them, and commit the appropriate lockfile.
- Add or update tests for changed behavior.
- Update documentation when behavior, setup, configuration, or a public contract changes.
- Never commit credentials, `.env` files, local databases, generated search data, or Terraform
  state. Copy `.env.example` to `.env` only when local overrides are needed.
- Changing a model means committing its migration. `just django-check` fails when the two
  disagree, and it runs as part of `just check`.
- Use `just clean` carefully: it stops the Compose services and deletes the Postgres volume.

Write small commits in the imperative mood:

```text
add neighborhood filter to spot search
fix API liveness error response
document local Postgres configuration
```

Avoid vague messages such as `updates`, `fixed stuff`, or `WIP` in the final branch history.

### Check the change

Set up the locked dependencies and Git hooks once:

```shell
just setup
```

The prerequisites for these commands are Bun, Python 3.12, uv, just, pre-commit, Git, and Docker Compose 2.23 or newer.

Before pushing, run the repository's complete supported check suite:

```shell
just check
```

This verifies the toolchain and Compose configuration, checks and builds the frontend, formats,
lints, and type-checks the backend, and builds the Sphinx documentation with warnings treated as
errors. Also run the tests relevant to your change. For suites that currently exist, use:

```shell
cd src/frontend && bun run test
just start-db
just test
```

`just test` runs the backend suite in `src/backend/spots/tests/` and the data-import suite in
`data/`. It needs Postgres running, which is what `just start-db` provides; pytest-django
creates and drops its own test database, so your loaded data is left alone. The pre-push hook
runs both `just check` and `just test`.

If your change touches `infra/`, also run `just infra-check`, which formats and validates the
Terraform without touching an AWS account.

Use `just start` for a local container smoke test and `just dev` for live source updates. See `just --list` for all supported commands.

## Opening a pull request

1. Push the feature branch and open a pull request into `develop`.
2. Link the issue with a closing keyword such as `Closes #123`.
3. Complete `.github/PULL_REQUEST_TEMPLATE.md`: explain the rationale, summarize the changes,
   describe the tests run, and identify user-facing or breaking API changes.
4. Run the change locally for user-facing work. There are no preview deployments, so include
   screenshots when they help reviewers evaluate the result.
5. Wait for all required checks to pass and resolve every review conversation before merging.
6. Do not push feature work directly to `develop` or `main`.

Keep pull requests small and focused. If a change is too large to review comfortably, divide it
into independently useful pull requests. Respond to every review comment; if you disagree with a
suggestion, explain the tradeoff instead of silently ignoring it.

Use this checklist before requesting review:

- [ ] The branch started from and is up to date with `develop`.
- [ ] The pull request closes or links the relevant issue.
- [ ] `just check` passes locally.
- [ ] Relevant behavioral tests pass, and new behavior has appropriate coverage.
- [ ] User-facing or contract changes are documented.
- [ ] No credentials, `.env` files, local databases, or generated search indexes are committed.
- [ ] User-facing changes have been run locally, with screenshots where they help.
- [ ] All review conversations are resolved.

Release pull requests merge `develop` into `main`. If an emergency fix lands on `main`, merge it
back into `develop` immediately so the branches do not diverge.

## Reporting issues

Search [existing issues](https://github.com/gcivil-nyu-org/team-4-fall26/issues) before opening a
new one. Use the repository's bug report or feature request template.

A useful bug report includes:

- a concise description of the problem;
- exact steps and commands that reproduce it;
- expected and actual behavior;
- complete error output or relevant logs;
- screenshots for visual problems;
- operating system, runtime versions, and relevant package versions; and
- the smallest reproduction you can provide.

A useful feature request explains the user problem, why existing behavior does not solve it, the
proposed outcome, and any public contract or user-interface changes. Include a concrete example
when possible. Do not include secrets, access tokens, private deployment URLs, or sensitive data
in issues, logs, or screenshots.

Security vulnerabilities should not be disclosed in a public issue. Contact the maintainers
privately through the repository owner's security-reporting channel instead.

## CI/CD

StudySpot uses GitHub Actions for validation only. Nothing deploys automatically, so CI stores
no deployment credentials of any kind.

| Check or workflow | What it does | When it runs |
|---|---|---|
| `Repository checks` | Installs locked dependencies and runs `just check` and `just test` against a Postgres service container, including a warning-strict Sphinx build | Every pull request and pushes to `develop` or `main` |
| `Terraform` | Formats and validates `infra/terraform/` with no AWS credentials | Every pull request and pushes to `develop` or `main` |
| `Container smoke test` | Builds the Compose services, waits for health checks, and probes the frontend and API | Every pull request and pushes to `develop` or `main` |

`Repository checks`, `Terraform`, and `Container smoke test` are
protected-branch requirements. Branches must also be current, review conversations must be resolved, and force
pushes and branch deletion are disabled.

The deployment flow is:

- feature pull requests are reviewed from the diff and a local run;
- release pull requests merge `develop` into `main`; and
- a maintainer deploys to AWS by hand when the team wants a change live.

The AWS deployment is deliberately outside CI: applying it needs long-lived AWS credentials,
which do not belong in this repository. Maintainers apply it from a checkout with the `just
aws-*` commands. See `infra/README.md`.
