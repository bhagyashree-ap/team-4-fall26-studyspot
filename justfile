set shell := ["bash", "-euo", "pipefail", "-c"]

# Picks up .env if there is one, so a checkout that copied .env.example needs no
# exporting. A missing .env is not an error.
set dotenv-load := true

# Local commands run against Django's development settings unless the
# environment says otherwise. Without this, settings.py refuses to start without
# a DJANGO_SECRET_KEY, which is correct for a deployment and useless for `just
# test`. Nothing deploys through just; see infra/README.md.
export DJANGO_DEBUG := env("DJANGO_DEBUG", "true")

# Terraform is always run against infra/terraform, from the repository root.
tf := "terraform -chdir=infra/terraform"

default:
    @just --list

# Install locked application and documentation dependencies and repository hooks.
setup:
    cd src/frontend && bun install --frozen-lockfile
    cd src/backend && uv sync --frozen
    uv sync --project docs --frozen
    uv run --project src/backend pre-commit install --hook-type pre-commit --hook-type pre-push

# Verify the toolchain and run every supported static check and build.
check:
    bun --version
    python3.12 --version
    uv --version
    docker --version
    docker compose version
    python3.12 -c 'import re, subprocess; value = subprocess.check_output(["docker", "compose", "version", "--short"], text=True).strip(); match = re.match(r"v?(\d+)\.(\d+)\.(\d+)", value); assert match and tuple(map(int, match.groups())) >= (2, 23, 0), f"Docker Compose 2.23.0+ is required, found {value}"'
    just --version
    docker info >/dev/null
    docker compose config --quiet
    docker compose watch --help >/dev/null
    cd src/frontend && bun run lint
    cd src/frontend && bun run check
    cd src/frontend && bun run build
    cd src/backend && uv run ruff format --check .
    cd src/backend && uv run ruff check .
    cd src/backend && uv run ty check
    just django-check
    uv run --project docs sphinx-build --fail-on-warning --keep-going --builder html docs/source docs/build/html

# Django's own system checks, and proof that the models and migrations agree.
django-check:
    cd src/backend && uv run python manage.py check
    cd src/backend && uv run python manage.py makemigrations --check --dry-run

# Validate the Terraform configuration. Requires `just aws-init` once first.
infra-check:
    {{tf}} fmt -check -recursive
    {{tf}} validate

# Start the frontend development server.
dev-frontend:
    cd src/frontend && bun run dev -- --host 127.0.0.1 --port 7500

# Start the backend development server. Needs Postgres: `just start-db`.
dev-backend:
    cd src/backend && uv run python manage.py runserver 127.0.0.1:7501

# Run frontend + backend together without Docker (needs local Postgres on :5432).
# Frontend → http://127.0.0.1:7500  Backend → http://127.0.0.1:7501
dev-local:
    #!/usr/bin/env bash
    trap 'kill 0' SIGINT SIGTERM EXIT
    (cd src/backend && uv run python manage.py runserver 127.0.0.1:7501) &
    (cd src/frontend && bun run dev -- --host 127.0.0.1 --port 7500) &
    wait

# Start only Postgres, for working on the backend outside Compose.
start-db:
    docker compose up --detach --wait postgres

# Seed sample communities and conversations (idempotent, DEBUG only).
seed:
    cd src/backend && uv run python manage.py seed_sample_communities

# Apply database migrations to the local database.
migrate:
    cd src/backend && uv run python manage.py migrate

# Generate migrations after changing a model.
makemigrations:
    cd src/backend && uv run python manage.py makemigrations

# Run the backend and data test suites. Needs Postgres: `just start-db`.
test:
    cd src/backend && uv run pytest
    cd data && uv run --project ../src/backend pytest .

# Refresh the subway station list the detail pages measure against. Rarely
# needed: the output is committed and the subway system changes slowly.
ingest-subway:
    cd data && uv run --project ../src/backend python subway.py

# Refresh the OpenStreetMap cafe list the importer merges over DOHMH. Rarely
# needed: the output is committed. One Overpass request takes about 45 seconds
# against a volunteer-run service, which is why it is not part of `just ingest`.
ingest-osm:
    cd data && uv run --project ../src/backend python osm.py

# End-to-end tests against a running deployment. Needs STUDYSPOT_E2E_URL; see
# tests/e2e/README.md. Deliberately outside `just test`, which must pass with
# nothing running.
test-e2e:
    cd tests/e2e && uv run --project ../../src/backend pytest .

# Regenerate data/spots.json from NYC Open Data, then `just load-data` to serve
# it. The snapshot stays in version control, so this is only needed when the
# upstream data or the mapping changes. Set NYC_OPEN_DATA_APP_TOKEN in .env for
# a personal rate limit instead of the shared anonymous one.
ingest:
    cd data && uv run --project ../src/backend python ingest.py

# Copy data/spots.json into the local database.
load-data:
    cd src/backend && uv run python manage.py load_spots

# Build and start the complete local system with live source updates.
dev:
    docker compose up --build --watch

# Start the complete local system in the background.
start:
    docker compose up --build --detach --wait

# Stop the local system without deleting data.
shutdown:
    docker compose down

# Follow logs from the local system.
logs:
    docker compose logs --follow

# Stop the local system and delete its database and search data.
clean:
    docker compose down --volumes --remove-orphans

# Format supported source files.
format:
    cd src/frontend && bun run format
    cd src/backend && uv run ruff format .
    {{tf}} fmt -recursive

# Build and serve the Sphinx documentation at http://localhost:7503.
docs:
    uv run --project docs sphinx-build --builder html docs/source docs/build/html
    python3.12 -m http.server 7503 --bind 127.0.0.1 --directory docs/build/html

# Validate the Nix development environment.
nix-check:
    nix --extra-experimental-features "nix-command flakes" flake check --print-build-logs

# -- AWS ----------------------------------------------------------------------
#
# See infra/README.md. The order for a first deployment is:
#
#     just aws-init aws-build aws-apply aws-migrate aws-load aws-frontend

# Download the Terraform providers. Run once per checkout.
aws-init:
    {{tf}} init

# Cross-compile the Lambda deployment package for arm64 Linux.
aws-build:
    infra/scripts/build-lambda.sh

# Show what an apply would change, without changing it.
aws-plan:
    {{tf}} plan

# Create or update the AWS infrastructure.
aws-apply:
    {{tf}} apply

# Apply Django migrations, from inside the VPC where the database is reachable.
aws-migrate:
    aws lambda invoke --function-name "$({{tf}} output -raw manage_function_name)" \
      --payload '{"command":"migrate"}' --cli-binary-format raw-in-base64-out /dev/stdout

# Load the bundled data/spots.json snapshot into the deployed database.
aws-load:
    aws lambda invoke --function-name "$({{tf}} output -raw manage_function_name)" \
      --payload '{"command":"load_spots"}' --cli-binary-format raw-in-base64-out /dev/stdout

# Extract the NYC basemap from the Protomaps daily planet build.
#
# About 31 MB at maxzoom 14, which MapLibre overzooms past for the close-in
# views the detail pages use. Zoom 15 would be 103 MB for sharper labels.
#
# The planet builds expire after roughly two weeks, so this takes a date rather
# than hardcoding one that will rot. Needs the pmtiles CLI: `brew install
# pmtiles`. Writes to infra/build/, which is gitignored -- a basemap does not
# belong in the repository.
tiles-build date:
    pmtiles extract "https://build.protomaps.com/{{date}}.pmtiles" \
      infra/build/nyc.pmtiles --bbox=-74.30,40.47,-73.68,40.93 --maxzoom=14

# Upload the basemap to the site bucket.
#
# The same bucket and distribution as the site, so the browser fetches it
# same-origin and no CORS configuration is needed. It is served by HTTP range
# request: a reader downloads the handful of tiles in view, not the 31 MB.
#
# `aws-frontend` excludes this prefix from its `--delete`, or every frontend
# deploy would remove it.
aws-tiles:
    aws s3 cp infra/build/nyc.pmtiles \
      "s3://$({{tf}} output -raw site_bucket)/tiles/nyc.pmtiles" \
      --content-type application/octet-stream \
      --cache-control 'public, max-age=604800'

# Build the static frontend, publish it, and invalidate the CloudFront cache.
aws-frontend:
    cd src/frontend && bun run build
    aws s3 sync src/frontend/build/ "s3://$({{tf}} output -raw site_bucket)/" --delete \
      --exclude 'tiles/*'
    aws cloudfront create-invalidation \
      --distribution-id "$({{tf}} output -raw cloudfront_distribution_id)" --paths '/*'

# Print the deployed URL and check that both boundaries answer.
aws-verify:
    @url="$({{tf}} output -raw site_url)"; \
      echo "site: $url"; \
      test "$(curl --silent --output /dev/null --write-out '%{http_code}' "$url/")" = 200; \
      curl --fail-with-body --silent --show-error "$url/api/health/live" | grep -Eq '"status":[[:space:]]*"ok"'; \
      echo "both boundaries answered"

# AWS restarts a stopped instance by itself after seven days, so this is a
# recurring chore rather than a one-off.

# Stop the database to preserve credits: storage is billed, compute is not.
aws-db-stop:
    aws rds stop-db-instance --db-instance-identifier "$({{tf}} output -raw database_identifier)"

# Start the database again after `just aws-db-stop`.
aws-db-start:
    aws rds start-db-instance --db-instance-identifier "$({{tf}} output -raw database_identifier)"

# Nothing here is irreplaceable: the infrastructure is this repository and the
# data is data/spots.json, so a destroyed stack is one apply away from returning.

# Tear the whole AWS stack down.
aws-destroy:
    {{tf}} destroy
