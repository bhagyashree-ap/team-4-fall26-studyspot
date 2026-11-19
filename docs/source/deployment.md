# Deployment

StudySpot has one deployment target: AWS. The SvelteKit frontend is prerendered to S3 behind CloudFront, and the Django application runs as a Lambda function behind the same distribution, which strips the public `/api` prefix before Django sees the request so the application needs no second copy of its routes.

The `/favourites` route is a prerendered shell with no personal data. The existing CloudFront rewrite serves `/favourites.html` for direct visits and refreshes. The browser loads saved state through authenticated API requests. All favourites API responses, including errors, are `private` and `no-store`.

| Part | How it is served | Driven by |
|---|---|---|
| Frontend | S3 behind CloudFront, prerendered with `adapter-static` | `just aws-frontend` |
| API | Lambda behind CloudFront `/api/*`, via API Gateway | `just aws-build`, `just aws-apply` |
| Database | RDS Postgres, private subnets | `just aws-migrate`, `just aws-load` |

```{important}
**There is no automatic deployment, and no per-pull-request preview.** Deploying is a deliberate act from a checkout with AWS credentials. A Terraform apply from CI would need long-lived AWS credentials in the repository, and a course project with one environment does not need them.

Reviewers therefore read the diff and run the change locally rather than opening a preview URL. If the team later wants previews, that is a second CloudFront distribution and a second Terraform workspace, not a setting.
```

GitHub Actions validates the repository, Compose topology, documentation, and Terraform configuration. It deploys nothing and holds no AWS credentials.

## Environments

```text
feature/* -> pull request, reviewed from the diff
                  |
                  v
              develop -> deployed by hand when the team wants it live
                  |
                  v
                main -> release
```

Developers work on short-lived feature branches and open pull requests into `develop`. Nobody pushes feature work directly to `develop`. A reviewed release pull request promotes `develop` into `main`.

Protect both long-lived branches with required checks, resolved conversations, and disabled force pushes and deletion. Repositories with independent reviewers can require approvals; a solo maintainer should leave the approval count at zero because GitHub does not allow authors to approve their own pull requests. A hotfix merged into `main` must immediately be merged back into `develop`.

Configure GitHub manually:

1. Protect `develop` and `main`.
2. Require `Repository checks`, `Terraform`, and `Container smoke test`.
3. Require resolved conversations and linear history; disable force pushes and deletion.
4. Use zero required approvals for a solo maintainer, or require approvals only when an independent reviewer is available.

No database secret belongs in GitHub Actions, because nothing in CI deploys.

## AWS

The deployment is Terraform in `infra/`: one CloudFront distribution splitting on path, S3 for the prerendered site, an API Gateway HTTP API in front of a Lambda function running Django through Mangum, and an RDS Postgres instance in private subnets. A second Lambda function runs Django management commands from inside the VPC, because the database has no public endpoint and `manage.py migrate` from a laptop cannot reach it.

A first deployment is seven commands:

```shell
just aws-init
just aws-build
just aws-apply
just aws-migrate
just aws-load
just aws-frontend
just aws-verify
```

Redeploying later is `just aws-build` and `just aws-apply` for the backend, or `just aws-frontend` alone for the frontend. Ship additive, schema-compatible backend code, apply its migrations with `just aws-migrate`, and then publish frontend controls that require them. `just aws-plan` previews a change without applying it.

`infra/README.md` is the source of truth for this target and is not duplicated here. Read it before the first apply: it covers what the stack costs and which lever reduces it, the AWS credentials the Terraform needs, why there is no NAT gateway, how the database password reaches the function, why Terraform state has to move off a laptop before anyone else touches the stack, and the three account constraints the configuration works around.

Two things are worth repeating because they are easy to discover too late:

- `just aws-db-stop` stops the database and bills storage only. AWS restarts a stopped instance automatically after seven days, so this is a recurring chore.
- `just aws-destroy` can delete the database, including accounts and private favourites. Terraform and `data/spots.json` cannot recreate user-owned data. Keep a recoverable backup outside the stack before destruction.

## Data and search state

`data/spots.json` is generated and committed, and the `load_spots` management command copies it into a Postgres database. On AWS, `infra/scripts/build-lambda.sh` bundles the snapshot into the deployment package and `just aws-load` loads it from inside the VPC, so the deployed API serves data as soon as that step has run once. Until it does, `GET /api/spots` returns an empty page rather than an error.

Locally the same step is `just load-data`, after `just start-db` and `just migrate`. The Compose backend runs migrations itself on startup but does not load data, so a fresh volume serves an empty page until you load one.

Search needs no separate deployed component. It is Postgres full text over a generated `tsvector` column, with `pg_trgm` similarity behind it for misspellings, so the only deployment step it requires is the migration that creates the column, the extension and their GIN indexes.

Business-owned spots, accounts, and favourites are non-rebuildable user data. Backups and backward-compatible migrations are release requirements now. Use a consistent full-database backup or RDS snapshot, and restore spots, accounts, favourites, and migration history together. See [Backup and consistent restore](database.md#backup-and-consistent-restore) for retention, access, and restore requirements.

The feature-aware loader preserves favourites when imported spot IDs survive a refresh. It removes favourites only for imported IDs absent from the replacement. Business-owned spots and their favourites remain unchanged, including for an empty replacement. Validation errors, owned-ID collisions, and write failures leave all data unchanged. Review the replacement dataset before running `just aws-load`.

The additive `accounts.0002` migration depends on `accounts.0001` and `spots.0012`. Deploy the feature-aware backend and management package, apply migrations, and then publish the favourites frontend. Take a recoverable backup before changing an existing database.

## Rollback

Choose an application revision compatible with the applied schema. Preserve the feature-aware management package when rolling back the API. Do not replace it with an older management package as part of the rollback. Republish the frontend from the chosen application revision with `just aws-frontend`.

Normal application rollback leaves the additive favourites migration applied. Do not reverse it or reload an older snapshot to roll back application code. Reversing the migration deletes favourites, and an older snapshot can omit saved spot IDs.

Keep the feature-aware management package and `load_spots` command available after an application rollback. Do not run `just aws-load` from an older checkout against a database containing favourites. Compatibility of an older loader with saved relationships is an operational prerequisite, not an assumed property. If a schema or data restore is necessary, use a consistent full-database backup and account for writes made since that backup.
