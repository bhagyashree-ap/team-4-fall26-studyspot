# Public board

The `/board` page is a public discussion feed for questions, study-space information, and business announcements. Posts have a title, a body, and optional subject, university, and study-spot tags. Each post has its own comment discussion. The **Board** link appears in the shared site navigation.

The frontend prerenders an empty shell and loads discussions from the API in the browser. `/board?post=42` identifies a discussion. Search and tag filters are query parameters, so copied links and page reloads retain the selected discussion or filters. No private author state is included in prerendered HTML.

## Authors and ownership

Public reads do not require an account. With the existing `STUDYSPOT_GUEST_CHAT=true` setting, a browser-session guest can publish questions and information, comment, and report content. This is also the default when accounts are disabled. Guest authors use the same pseudonym as community chat.

Cookieless reads of posts, comments, and tag suggestions do not create stored guest sessions. `/board/access` and the first write establish the browser's guest identity. A new visitor can still see the report action on a shared discussion link after access loads.

A guest's browser session owns its posts and comments. Clearing cookies or letting the session expire loses editing access. The published content remains readable. Signing in does not claim earlier guest content.

Active accounts with completed student or business signup can write. Business accounts can additionally publish announcements under their business name. An announcement does not require a claimed listing and does not assert verified ownership of a tagged space. Incomplete and inactive accounts cannot write or fall back to guest access.

With `STUDYSPOT_GUEST_CHAT=false`, reading stays public and writing requires an eligible account. When accounts are also disabled, the page remains readable but does not offer a nonfunctional login flow.

Only the author can edit or delete a post or comment through the public API. Post deletion also deletes its comments. Report evidence has a separate lifetime and remains available to staff after deletion.

## Tags and search

A post has up to ten distinct tags. Subject and university tags accept text rather than a fixed catalog. University tags describe a topic, not verified attendance. Tag identity uses Unicode normalization, collapsed whitespace, and case-insensitive matching. Display labels retain readable spelling.

A study-spot tag identifies an actual API study spot. Its ID and display label are stored with the board, not linked by a cascading foreign key. Imported study spots are deleted and recreated during a dataset refresh. This storage keeps the discussion's tags intact through that refresh.

If a tagged spot disappears, the existing tag retains its saved label and is marked unavailable. An author can still edit the discussion without removing that tag. Attaching a missing spot as a new tag is rejected.

Keyword search matches post titles and bodies without case sensitivity. It does not search comments. Subject, university, study-spot, and post-kind filters combine with the keyword using AND. An unknown, well-formed tag produces an empty result rather than a validation error.

Posts are ordered by descending ID. The `before` cursor selects older posts. Comments are ordered by ascending ID, and `after` selects later comments. Both collections default to 20 results and accept a `limit` from 1 to 50. Each response is `{items, has_more}`. Editing does not move a post to the top of the feed.

## API routes

These are Django paths without trailing slashes. The browser and deployed site prefix them with `/api`.

| Route | Methods | Behavior |
|---|---|---|
| `/board/access` | GET | Public author capabilities, allowed post kinds, limits, and a CSRF cookie. |
| `/board/posts` | GET, POST | Search the public feed or create a post. |
| `/board/posts/{id}` | GET, PATCH, DELETE | Read a discussion or change the author's own post. |
| `/board/posts/{id}/comments` | GET, POST | Read comment pages or add a comment. |
| `/board/comments/{id}` | PATCH, DELETE | Change the author's own comment. |
| `/board/tags` | GET | Suggestions for existing tags. |
| `/board/posts/{id}/reports` | POST | Privately report a post. |
| `/board/comments/{id}/reports` | POST | Privately report a comment. |

The feed accepts `q`, `kind`, `subject`, `university`, `spot`, `before`, and `limit`. Tag suggestions accept `kind`, `q`, and `limit`. Tag kinds are `subject`, `university`, and `spot`.

Post creation accepts this shape:

```json
{
  "kind": "question",
  "title": "Quiet study rooms in the evening?",
  "body": "Which rooms stay quiet after 6 pm?",
  "tags": [
    {"kind": "subject", "value": "Calculus II"},
    {"kind": "university", "value": "New York University"}
  ]
}
```

Post kinds are `question`, `information`, and `announcement`. A post title contains 1 to 160 characters. Its body contains 1 to 10,000 characters. A comment body contains 1 to 3,000 characters. Report requests contain a `reason` of 1 to 2,000 characters. Required text is trimmed and cannot be whitespace alone. Subject tags have a maximum of 80 characters. University tags have a maximum of 120 characters. Study-spot IDs have a maximum of 255 characters.

Required text needs a visible base character. Whitespace, invisible fillers, format controls, and combining marks alone are rejected. Combining marks and emoji joiners remain unchanged when the text also contains visible content.

PATCH accepts writable fields only. Omitted fields retain their values. A supplied tag array replaces the post's tags. Authorship, ownership flags, reporter identity, and report snapshots are never accepted from clients.

Post responses contain `id`, `kind`, `title`, `body`, `tags`, `author`, timestamps, `comment_count`, and the current viewer's edit, delete, and report capabilities. Comment responses contain their post ID, body, public author, timestamps, and capabilities. Neither includes account emails, Auth0 subjects, internal author IDs, guest session identifiers, or private reports.

Unsafe session requests require a valid CSRF token. Auth0 bearer requests use the existing token verifier. Every board response uses `Cache-Control: private, no-store` because capabilities depend on the requester. Validation errors use the shared API envelope and status `422`. Missing authentication returns `401`, forbidden operations return `403`, and missing resources return `404`.

## Reports and staff access

Reporting sends the reason privately to staff. A repeated report from the same author for the same target returns the existing receipt rather than adding another report. The first report preserves the original content and attribution. Public responses do not reveal report reasons, reporter identities, or report counts.

Reports are reviewed through the existing Django admin at `/admin/board/report/` on the backend origin. The queue requires an active staff user with the relevant Django model permissions. Report evidence is read-only. The review action records the reviewer and review time. Report evidence survives edits and deletion of the reported content.

The admin defaults to enabled only in debug mode. Deployments must explicitly configure `DJANGO_ENABLE_ADMIN=true` and authorized staff access before relying on this review queue. This feature does not enable production admin or deploy the service.

## Browser failures

The page retains drafts after rejected or interrupted requests and does not claim success before the API acknowledges a write. Mutations are not automatically retried. A lost response can leave the outcome unconfirmed, so the discussion can be checked before a manual retry. Deletions require confirmation and remain visible if the server rejects them.
