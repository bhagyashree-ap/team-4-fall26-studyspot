# Testing

Tests live with the code they verify.

| Scope | Location | Runner |
|---|---|---|
| Frontend components | `src/frontend/src/**/*.spec.ts` | Vitest |
| Study-spot routes | `src/backend/spots/tests/test_spots_api.py` | pytest with pytest-django |
| Dataset loader | `src/backend/spots/tests/test_load_spots.py` | pytest with pytest-django |
| Data import | `data/test_ingest.py` | pytest |
| Search ranking | `src/backend/spots/tests/test_search.py` | pytest with pytest-django |
| Filter counts | `src/backend/spots/tests/test_facets.py` | pytest with pytest-django |
| Public-board routes and ownership | `src/backend/board/tests/` | pytest with Postgres |
| Public-board browser workflow | `src/frontend/qa/public-board.mjs` | Node test runner with Playwright and the real local API |
| A running deployment | `tests/e2e/` | pytest over HTTP |

Run every currently supported check:

```shell
just check
```

This verifies the toolchain and Compose configuration, then runs the frontend formatting/linting/type checks/build, the backend formatting/linting/type checks, Django's own system checks, the proof that the models and migrations agree, and a warning-free Sphinx documentation build.

Run the test suites:

```shell
just start-db
just test
```

Both `just check` and `just test` run on every pull request and on the pre-push hook.

## End-to-end tests are separate

`tests/e2e/` drives a *running* StudySpot over HTTP, so it needs a base URL and
is skipped without one:

```shell
STUDYSPOT_E2E_URL=https://d1ulyrfyi06kwp.cloudfront.net just test-e2e
```

It is deliberately outside `just check` and `just test`, which have to pass on
a checkout with nothing running.

These exist because every other suite substitutes something for the part it is
not testing -- a test database, a mocked `fetch`, committed fixtures -- so none
of them can see a failure in the seams: CloudFront routing `/api/*` to the
wrong origin, a migration never applied, a deployed database nobody loaded. The
first run of this suite found exactly such a bug, a mistyped URL serving a raw
S3 error document instead of the application's 404 page.

They assert invariants rather than counts, because `data/spots.json` is
regenerated whenever the upstream data changes and a test pinned to "48 spots
in the Bronx" would fail on a perfectly good snapshot. Everything in them is a
`GET`, so they are safe to run against the deployed site.

The public-board browser tests are separate from these deployment-safe HTTP
tests. They use isolated browser sessions against the real local API and
Postgres. They cover post and comment ownership, persistence, tags, search,
failed-write draft recovery, private report evidence, staff access, and mobile
layouts. The startup regression delays the real capabilities request and checks
that loading does not erase a typed filter.

From `src/frontend`, with a dedicated migrated database, imported study spots,
and a local staff account:

```shell
DJANGO_DEBUG=true \
PUBLIC_BOARD_URL=http://127.0.0.1:7500 \
PUBLIC_BOARD_BACKEND_URL=http://127.0.0.1:7501 \
DATABASE_URL="$LOCAL_BOARD_DATABASE_URL" \
PUBLIC_BOARD_ADMIN_USERNAME="$LOCAL_ADMIN_USERNAME" \
PUBLIC_BOARD_ADMIN_PASSWORD="$LOCAL_ADMIN_PASSWORD" \
node --test qa/public-board.mjs
```

This command writes test-owned discussions and leaves private moderation
evidence in the dedicated database. It refuses non-local application URLs.
It does not verify hosted Auth0 login. Component tests elsewhere still use
mocked API responses.

## The tests need Postgres

The backend suite runs against a real Postgres rather than a substitute, because the behaviour under test is Postgres behaviour: the database's own case folding on both sides of every case-insensitive filter, the expression indexes those filters need, and the check constraints the loader relies on the database to enforce. A test double would pass while leaving exactly those properties unverified.

`just start-db` is enough to satisfy that. pytest-django creates and drops its own test database on the same server, so the suite never touches the one `just load-data` fills, and no fixture has to clean up after itself. CI does the same thing with a Postgres service container.

Nothing else has to be exported. `pyproject.toml` points pytest at `studyspot.settings_test`, which supplies the debug flag and a test secret key and then defers to the real settings module, so `uv run pytest` works in a fresh checkout and the suite still exercises the configuration every other environment uses. That cannot be done from a `conftest.py`: pytest-django sets Django up from `pytest_load_initial_conftests`, before any conftest module is imported. An explicit `DATABASE_URL` still wins, which is how CI points the suite at its service container.

`just test` also runs the data suite in `data/`. pytest exits 5 when it collects nothing, which `just test` treats as success rather than failure: the importer and its tests arrive on their own branch, and the API suite should not fail because they have not landed yet.

## Validating the Terraform

```shell
just infra-check
```

This formats and validates `infra/terraform/` without touching an AWS account. `terraform validate` evaluates the deployment package's hash, so build the package with `just aws-build` first, or create a placeholder at `infra/build/studyspot-api.zip`. CI creates a placeholder, which is why its Terraform job needs no credentials.

## Container smoke test

```shell
just start
curl --fail http://localhost:7500/
curl --fail http://localhost:7501/health/live
just shutdown
```

This is the boundary CI's `Container smoke test` probes: that the images build, that every health check passes in order, and that both public boundaries answer.

## What the suites cover

The route tests exercise the published contract end to end: the pagination envelope and its `total`, `count`, and `has_more` fields, every filter, deterministic ordering across pages, LIKE wildcards matched literally, the structured error envelope, `422` for an unknown query parameter, identifiers that keep their dataset prefix through URL routing, and routes that reverse without a trailing slash. They assert the shape of each response and not only its contents, because that shape is what the frontend, the importer, and any future search index agree on — and because they are the check that the move from a previous framework did not quietly change the API.

The loader tests cover repeatable loading, records dropped upstream disappearing from the table, an empty snapshot emptying it, borough casing and spacing normalization, and the rejection of any record the API could not serve — including the proof that a rejected snapshot leaves the previous contents untouched.

The data tests cover source mapping, coordinate and borough validation, university derivation, and the committed `spots.json` itself.

Each product milestone adds meaningful tests for its public behavior. Readiness reporting and search have none yet, because neither is implemented.
