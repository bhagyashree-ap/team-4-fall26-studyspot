# [StudySpot](https://d1ulyrfyi06kwp.cloudfront.net)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://python.org)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

**Live at <https://d1ulyrfyi06kwp.cloudfront.net>**

StudySpot is an open-source app for discovering cafés and other third places across New York City. The goal is to make finding a useful place feel immediate: search by a name, category, or neighborhood and get a small, consistent set of results derived from NYC Open Data and OpenStreetMap.

Public study communities are available at `/communities`. Anyone can create and join a group without signing in. Owners manage channels and members; members can share channel links, chat, search messages, and start private conversations. Guest ownership and membership are tied to the browser session.

> [!IMPORTANT]
> StudySpot is deployed and working. `data/spots.json` holds 2,422 real places — 2,158 cafés, 227 public library branches, 21 special libraries, and 16 academic libraries and NYU campus buildings — 429 of them with a free public Wi-Fi hotspot nearby, and 108 cafés with a sidewalk-dining licence. Every one is somewhere a person can go: the city's 126 campus records anchor the "near which campus" label but are not published as spots, because an institution's administrative point is not a room. Search runs entirely in Postgres: full text ranks across name, campus, neighborhood and address, with trigram similarity behind it for misspellings, and it searches as you type. Results filter by borough, type, campus, and Wi-Fi. A spot detail page is the notable gap.

## How will it work?

StudySpot is a small modular monolith: one application, one versioned public-data snapshot.

```text
Browser -> SvelteKit -> Django REST Framework -> Postgres

NYC Open Data  -\
OpenStreetMap  --- ingest.py -> spots.json -> Postgres
```

The [Svelte 5](https://svelte.dev/) frontend owns the search experience. A [Django](https://www.djangoproject.com/) application with [Django REST Framework](https://www.django-rest-framework.org/) provides the HTTP boundary, and one model defines the study spot that the routes, the loader, and the search ranking all share. [Postgres](https://www.postgresql.org/) is both the serving database and the search engine, and deliberately the only one. Full-text search over a generated, weighted `tsvector` column finds every word someone typed across the name, campus, neighborhood and address; `pg_trgm` similarity sits behind it for the misspellings full text cannot match. Both are GIN-indexed, which is ample for a few hundred records and removes a moving part from the deployment. The normalized NYC Open Data snapshot remains the reproducible source used to load it.

Local development uses Docker Compose for the browser app, the API, and Postgres. The same Postgres is published on `127.0.0.1:5432`, so a backend run outside Compose uses the same database as one run inside it. On [AWS](https://aws.amazon.com/) the same application runs against the same schema: the API is a Lambda function behind CloudFront, with an RDS Postgres instance in private subnets.

The shared study-spot summary contract is intentionally small:

```json
{
  "id": "facdb:eec118768e15a5e03d3354abda7b00da",
  "name": "125th Street Library",
  "category": "library",
  "address": "224 East 125 Street, New York, NY 10035",
  "neighborhood": "East Harlem (North)",
  "borough": "Manhattan",
  "latitude": 40.803027,
  "longitude": -73.934853,
  "university": "Touro University - Harlem",
  "operator": "New York Public Library",
  "free_public_wifi": true,
  "no_purchase_needed": true,
  "subway_station": "125 St",
  "subway_routes": "4 5 6",
  "subway_metres": 180,
  "subway_step_free": "full",
  "nearby_spots": 23,
  "outdoor_seating": false
}
```

`university` is proximity and never affiliation or a claim of access. `free_public_wifi` means the city publishes a free hotspot within 25 m; `false` means none is recorded rather than that there is no Wi-Fi, which is why a campus building with credentialled Wi-Fi reads as `false`. `operator` is who runs the place — for a branch, its library system, which nothing else in the record says. `no_purchase_needed` is true where sitting down costs nothing — every library and campus building, no café — and is about money rather than entry. `outdoor_seating` is true when a Dining Out NYC sidewalk licence matches the establishment's name *and* address; `false` means no licence matched rather than that there is nowhere to sit outside, and only cafés can carry it.

Six routes are available alongside `GET /health/live`, none of them with a trailing slash:

| Route | Purpose |
|---|---|
| `GET /spots` | Pages with `limit` and `offset`; filters on `name`, `category`, `neighborhood`, `borough`, `university`, `free_public_wifi`, and `no_purchase_needed` |
| `GET /spots/search?q=` | Ranks instead of filtering, across name, campus, neighborhood and address; tolerates misspellings, expands initialisms, and accepts the same filters |
| `GET /spots/facets` | The values the filter controls offer, with counts |
| `GET /spots/{id}` | One spot |
| `GET /auth/config` | Which Auth0 tenant the browser logs in with |
| `GET /account`, `POST /account` | The logged-in person's account, and finishing sign-up |

See the [HTTP API guide](docs/source/api.md).

Every spot also has its own page at `/spots/{id}`. All 3,772 are prerendered at build time from the committed snapshot, so each is real HTML in S3 rather than a route the browser assembles: the link works in a fresh tab, in a shared message, and to a crawler, with no request on load. The nearby-spots list on each page is computed at build time from the same coordinates the importer uses.

## Development

### Native local run (macOS)

Install Bun, Python 3.12, uv, just, and PostgreSQL 17. Start Postgres and set up the development database once:

```shell
brew services start postgresql@17
PG_BIN="$(brew --prefix postgresql@17)/bin"
"$PG_BIN/psql" postgres -c "CREATE ROLE studyspot LOGIN PASSWORD 'studyspot' CREATEDB;"
"$PG_BIN/createdb" -O studyspot studyspot
```

From the repository root, run `just setup` and `just migrate`, then run `just dev-backend` and `just dev-frontend` in separate terminals. Open <http://localhost:7500/communities>. The development connection defaults to `postgresql://studyspot:studyspot@localhost:5432/studyspot`. No account is required for community creation or joining.

To populate sample communities and channel conversations, run `cd src/backend && DJANGO_DEBUG=true uv run python manage.py seed_sample_communities`. Add `--guest-community ID` to include two private conversations for the sole active guest in a guest-owned community. The command is repeatable and only runs with `DJANGO_DEBUG=true`.

The container alternative requires Git and Docker Compose 2.23 or newer:

```shell
docker compose up --build --watch
```

Open <http://localhost:7500>. Source changes are synchronized into the frontend and backend containers; dependency changes rebuild only the affected image.

To try community writes before the account UI is integrated, run `docker compose exec backend uv run python manage.py createsuperuser`, sign in at <http://localhost:7501/admin/>, then visit <http://localhost:7500/communities>. The backend and frontend share the `localhost` session cookie. Public browsing needs no account.

For a pinned toolchain, use [Nix](https://nixos.org/). You will still need a running Docker engine.

```shell
nix develop
just setup
just check
```

Developers with `direnv` can run `direnv allow` once to activate the flake automatically when entering the repository.

Without Nix, install Bun, Python 3.12, uv, just, pre-commit, Git, and Docker, then run `just setup` followed by `just check`. Use `just --list` to see every supported repository command.

### Running the complete system

Build and start every container service with live source updates:

```shell
just dev
```

Or start them in the background and wait for their health checks:

```shell
just start
```

Once healthy, the services are available at:

| Service | Local address |
|---|---|
| Frontend | <http://localhost:7500> |
| API liveness | <http://localhost:7501/health/live> |
| Documentation (`just docs`) | <http://localhost:7503> |
| Postgres | `127.0.0.1:5432` |

The backend applies its migrations before it starts serving, so a fresh checkout gets a working schema without a separate step. Follow logs with `just logs`, stop services while preserving local data with `just shutdown`, or remove the data volumes with `just clean`.

### Running one application

Run the frontend development server:

```shell
just dev-frontend
```

Run the backend development server, which needs only the database:

```shell
just start-db
just migrate
just dev-backend
```

`just start-db` starts the Postgres container alone and waits for it; `just migrate` brings the schema up to date, and `just makemigrations` generates a migration after a model change. The frontend proxies `/api/*` requests to the Django API during local development.

### Loading data

The data boundary lives in [`data/`](data/): `ingest.py` normalizes four NYC Open Data datasets, the OpenStreetMap cafés `osm.py` fetches from the Overpass API, and a curated list of NYU buildings into `spots.json`. `test_ingest.py` and `test_osm.py` verify the mapping against a committed sample of upstream records. Copy the snapshot into the local database before using the study-spot routes:

```shell
just load-data
```

The snapshot is in version control, so this needs no network. Regenerate it from NYC Open Data when the upstream data or the mapping changes:

```shell
just ingest
```

The OpenStreetMap cafés are a committed snapshot of their own, refreshed separately, because one Overpass request takes about 45 seconds against a volunteer-run service:

```shell
just ingest-osm
```

The loader validates every record against the shared model and replaces the table's contents in one transaction, so it is safe to re-run and the table can only ever hold records the API can serve.

### Checks

Verify the toolchain, Docker daemon, Compose configuration, formatting, linting, type checking, production frontend build, and warning-strict documentation build:

```shell
just check
```

Run the backend and data test suites, which need the database running:

```shell
just start-db
just test
```

The suites run against a real Postgres because the schema depends on Postgres behaviour — trigram ranking most of all — so pytest-django creates and drops its own test database and loaded data is left alone.

Run `just nix-check` to validate the pinned development environment. Tests live beside the behavior they verify.

## Deployment

AWS is the deployment: CloudFront in front of S3 for the prerendered frontend and a Lambda function for the API, with RDS Postgres in private subnets. It is Terraform in [`infra/`](infra/), applied deliberately from a checkout rather than from CI, which would need long-lived AWS credentials in the repository:

```shell
just aws-init aws-build aws-apply aws-migrate aws-load aws-frontend aws-verify
```

Because the RDS instance has no public endpoint, migrations and data loads run as Lambda invocations rather than from a laptop. `just aws-plan` previews a change, `just aws-db-stop` and `just aws-db-start` pause the database between work sessions, and `just aws-destroy` removes the stack. [`infra/README.md`](infra/README.md) covers the stack, what it costs, and the three account constraints the configuration works around.

GitHub Actions runs repository, container, documentation, Nix, and Terraform checks, and performs no deployment of its own. Feature pull requests target `develop`; release pull requests merge `develop` into `main`. See the [deployment guide](docs/source/deployment.md) for the environment model and rollback behavior.

## Documentation

The documentation is written in MyST Markdown, built with Sphinx, and rendered with the Furo theme. Sources live in [`docs/source/`](docs/source/).

Run `just docs`, then open <http://localhost:7503>. The command builds the documentation before starting the local server. The build is warning-strict and runs as part of `just check`; it is not published anywhere yet.

Useful starting points include the [architecture](docs/source/architecture.md), [local development](docs/source/local-development.md), [deployment](docs/source/deployment.md), [testing](docs/source/testing.md), and [contribution guide](CONTRIBUTING.md).

## Technology

- **Frontend:** Svelte 5, TypeScript, SvelteKit, Vite, Tailwind CSS, Bun
- **Backend:** Python 3.12, Django 5.2, Django REST Framework, uv
- **Data sources:** NYC Open Data, OpenStreetMap
- **Database and search:** Postgres, with full-text search and `pg_trgm` — a container locally, Amazon RDS on AWS
- **Deployment:** AWS (CloudFront, S3, API Gateway, Lambda, RDS) with Terraform
- **Operations:** Nix, Docker Compose, just, pre-commit, GitHub Actions
- **Checks:** Prettier, ESLint, svelte-check, Ruff, ty, pytest, Django system checks, `terraform validate`

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) before changing the repository. Shared contract changes need review from every affected owner.

## License

StudySpot is available under the [MIT License](LICENSE).
