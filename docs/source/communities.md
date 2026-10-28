# Communities

The static `/communities` page discovers public groups through the Django API. Anyone can create a community without signing in. A group has an owner, members, text channels, optional school and course, and shareable invitations. Members can read and post channel messages, reply, react, edit their own messages, and delete their own messages. Owners and moderators can delete and pin messages. Search covers nondeleted messages in a community. Community members can also start private one-to-one conversations from a member or channel message. Attachments, voice/video, and bots are outside this release.

All community paths have no trailing slash. Public `GET /communities?q=&limit=&offset=`, `GET /communities/{id}`, `GET /communities/{id}/members`, and `GET /communities/{id}/channels` need no account. The list returns `{items, has_more}` with a default page size of 20 and maximum of 50. `mine=true` shows communities joined or owned by the current account or browser session. Member listings page account members in `items` and active guest members in `guest_items`, with separate continuation flags and a `guest_count`. Guest identities are shown as stable pseudonyms; their session IDs are never returned.

Community creation, joining, leaving, and invite redemption work without an account. Browser sessions identify guest owners and members; the public list request sets a CSRF cookie for guest writes. Guest memberships expire with their session and stop counting after expiry. Visitors can own up to five communities and join up to 100 in one session. Clearing site cookies loses guest ownership and membership; a future claim flow can transfer them to an account. Guest creators manage channels, invitations and moderation through the same permission policy as account owners. Auth0 bearer tokens supply `request.user` for signed-in account actions; foreign keys use `settings.AUTH_USER_MODEL`. StudySpot admins must be marked `is_staff`. No client-supplied actor or role is trusted.

| Route | Method | Rule |
|---|---|---|
| `/communities` | POST | Create a group, owner membership and `general` channel. |
| `/communities/{id}` | PATCH, DELETE | Owner edits or deletes. |
| `/communities/{id}/join`, `/leave` | POST | Join or leave with an account or browser session; owners transfer or delete first. |
| `/communities/{id}/members/{user_id}` | PATCH, DELETE | Owner appoints moderators; owner or moderator kicks eligible members. |
| `/communities/{id}/transfer` | POST | Owner transfers to a current member. |
| `/communities/{id}/channels` | POST | Owner creates a channel. |
| `/communities/{id}/channels/{channel_id}` | PATCH, DELETE | Owner renames, reorders, archives, restores or removes a channel. |
| `/communities/{id}/channels/{channel_id}/messages` | GET, POST | Members read pages of up to 50 messages or post up to 2,000 characters. `before` loads older messages; `after` loads newer ones. |
| `/communities/{id}/channels/{channel_id}/messages/{message_id}` | PATCH, DELETE | Author edits; author or moderator deletes. Deleted messages remain as empty tombstones for replies. |
| `/communities/{id}/channels/{channel_id}/messages/{message_id}/reactions` | POST | Add a reaction once per member. |
| `/communities/{id}/channels/{channel_id}/messages/{message_id}/reactions/{emoji}` | DELETE | Remove your reaction. |
| `/communities/{id}/channels/{channel_id}/messages/{message_id}/pin` | POST, DELETE | Owner or moderator pins or unpins. |
| `/communities/{id}/channels/{channel_id}/pins` | GET | Members list the latest 50 pins. |
| `/communities/{id}/messages/search?q=` | GET | Members search community messages with Postgres full-text search. |
| `/communities/{id}/channels/{channel_id}/messages/{message_id}/dm` | POST | Start a private conversation with a current community member who posted the message. |
| `/communities/{id}/dms` | POST | Start a private conversation with an account member by `user_id` or an active guest by `guest_member_id`. |
| `/dms` | GET | List the current account's or guest session's latest 50 private conversations. |
| `/dms/{id}/messages` | GET, POST | Either participant reads paged history or posts a private message. |
| `/dms/{id}/messages/{message_id}` | PATCH, DELETE | The author edits or deletes their private message. |
| `/communities/{id}/invites` | GET, POST | Owner or moderator lists or creates links. |
| `/communities/{id}/invites/{invite_id}` | DELETE | Owner or moderator revokes a link. |
| `/communities/invites/{token}/redeem` | POST | Join through a valid link. |
| `/communities/{id}/moderation` | GET, POST | Owner or moderator reads events and bans, or kicks, bans and unbans. |
| `/communities/{id}/admin` | DELETE | StudySpot admin removes a group. |

Account owners are stored on the community; guest ownership is in the browser session. Account membership records store `member` or `moderator`; guest memberships have no moderator role. A moderator cannot act against an owner or another moderator. Account bans prevent joining, including through an invite, while public content remains readable. Guest membership cannot be banned reliably because clearing cookies creates a new identity. Invitation tokens are returned once at creation; only their SHA-256 hashes are stored. A maximum-use link increments only for a newly joined account or guest.

The current limits are five owned and 100 joined communities per account or browser session, 1,000 active members, 20 channels and ten active invites per community. Channel names are lowercase letters, digits and hyphens. Invites may expire after one to 720 hours and may cap successful joins at 1,000. These limits live in `communities/services.py` and serializers.

The browser fetches up to 50 channel messages at a time and refreshes the latest 50 every three seconds while the page is visible. This picks up posts, edits, deletions, pins, and reactions without a separate socket service on the current Lambda deployment. Archived channels remain readable and reject new messages. Guest messages remain after the browser session expires, but the guest can no longer edit them once its membership expires. Clearing cookies loses the ability to manage a guest-created community or its messages.

The `/communities` landing page shows public communities and a creation action. A community's Main tab fills the available workspace with channels, chat and a member list on wider screens. Members shows the full paged roster, including guests. Owners use the add button beside Channels to create a channel; Edit channel opens visible rename, archive and delete controls, while the three-dot menu also offers reordering. Deletion asks for confirmation. Share channel copies a URL containing the community and channel IDs; because communities are public, recipients join from that page and then land in the chosen channel. Private conversations are accessible only to their two participants, and a new conversation can be started only with a current member of a shared community. Guest DMs are bound to the browser session, so clearing cookies loses access to them.

The School field opens with familiar institutions and searches 6,089 distinct operating US postsecondary institution names from the October 2026 [College Scorecard institution download](https://collegescorecard.ed.gov/data/). The snapshot is in `src/frontend/static/schools.json` and can be refreshed with `uv run --project src/backend python data/schools.py`. The Course field opens with common course names and any course codes already used by communities at the chosen school. Both fields filter as students type, support keyboard selection, and allow other values. The federal institution file does not contain each school's course catalog.

Community creation, membership changes, invite redemption, moderation, and ownership transfers use database transactions. The account implementation should choose its `AUTH_USER_MODEL` before applying these migrations. Owners must transfer or delete their communities before account deletion. Other account deletion does not depend on historical invite or moderation actor rows.

On AWS, session-authenticated writes require the public CloudFront origin in Terraform's `django_csrf_trusted_origins`. Set this variable to the distribution's printed `https://...cloudfront.net` origin before enabling guest writes.
