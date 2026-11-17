# StudySpot frontend scaffold

This Bun project contains the Svelte 5 application shell for finding NYC cafés and other third places. Dataset loading, search requests, result rendering, and state handling are not implemented by this scaffold.

```shell
bun install
bun run dev
bun run check
bun run build
```

## Public board browser E2E

`/board` prerenders a public shell. Live posts, comments, tags, and author capabilities come from the board API after the browser session starts.

Run the local frontend, API, and dedicated migrated database with guest access enabled. The database needs real imported study spots and an existing local staff account. From this directory, run:

```shell
DJANGO_DEBUG=true \
PUBLIC_BOARD_URL=http://127.0.0.1:7500 \
PUBLIC_BOARD_BACKEND_URL=http://127.0.0.1:7501 \
DATABASE_URL=postgresql://studyspot:studyspot@127.0.0.1:55433/studyspot \
PUBLIC_BOARD_ADMIN_USERNAME="$LOCAL_ADMIN_USERNAME" \
PUBLIC_BOARD_ADMIN_PASSWORD="$LOCAL_ADMIN_PASSWORD" \
node --test qa/public-board.mjs
```

This test uses isolated real guest sessions, real HTTP writes, the backend's local Python environment, database reads, and the staff admin. It refuses non-local application URLs. It deletes only its own discussions. Private moderation evidence intentionally remains in the local database. No transport or authentication mocks are used. This does not verify hosted Auth0 login.
