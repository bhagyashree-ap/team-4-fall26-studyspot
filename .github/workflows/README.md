# Workflows

- `ci.yml` installs locked dependencies and runs `just check` on every pull request and push to `develop` or `main`.
- `compose.yml` builds the four-service local topology, waits for healthy containers, and checks the frontend and API liveness endpoint.
- `ci.yml` builds the warning-free Sphinx documentation as part of `just check`. The documentation is not published anywhere.

There is no automatic deployment. AWS is applied by hand with `just aws-*` from a checkout with credentials, so GitHub Actions needs no deployment secrets of any kind.

Configure the `develop` and `main` branches to require these checks before merging:

- `Repository checks`
- `Container smoke test`

Require resolved conversations and disable force pushes and branch deletion. GitHub does not permit pull-request authors to approve their own work, so a solo maintainer must use zero required approvals. Teams with an independent reviewer can require one or more approvals.

The canonical settings are stored in `.github/branch-protection.json` and can be reapplied through the GitHub branch-protection API.

Feature pull requests target `develop`. Release pull requests merge `develop` into `main`.

This repository's GitHub Pages site uses **GitHub Actions** as its source. Forks must enable that setting before their first documentation deployment.
