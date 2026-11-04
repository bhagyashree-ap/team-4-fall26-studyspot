# Communities

The static `/communities` page discovers public groups through the Django API. After starting Postgres with `just start-db` and the app with `STUDYSPOT_CHAT_DEMO=true just dev-local`, open `http://localhost:7500/communities` to browse, create or join as a browser-session guest. Open a copied channel link in a private window and select **Join community** to chat as a second guest. Outside this opt-in debug demo, the chat API requires an active account. Local guests get stable fictional names. Use the theme button in the top bar to switch between light and dark. A group has an owner, members, text channels, optional school and course, and shareable invitations. Members can read and post channel messages, reply, react, edit their own messages, and delete their own messages. Owners and moderators can delete and pin messages. Search covers nondeleted messages in a community. Community members can also start private one-to-one conversations from a member or channel message. Channel chat and DMs support threads, emoji reactions, polls, file attachments, Markdown, code blocks, spoilers and a searchable Unicode emoji picker.

All community paths have no trailing slash. `GET /communities?q=&limit=&offset=` requires an active account. Community details, members and channels require the same access. The list returns `{items, has_more}` with a default page size of 20 and maximum of 50. `mine=true` shows communities joined or owned by the current account or browser session. Member listings page account members in `items` and active guest members in `guest_items`, with separate continuation flags and a `guest_count`. Guest identities are shown as stable pseudonyms; their session IDs are never returned.

In the local demo, joining, leaving, and invite redemption support guest sessions. Browser sessions identify guest members and owners of existing guest-created groups. Session writes require a CSRF token. Guest memberships expire with their session and stop counting after expiry. Visitors can join up to 100 communities in one session. Clearing site cookies loses guest ownership and membership; a future claim flow can transfer them to an account. Guest creators manage channels, invitations and moderation through the same permission policy as account owners. Auth0 bearer tokens supply `request.user` for signed-in account actions; foreign keys use `settings.AUTH_USER_MODEL`. StudySpot admins must be marked `is_staff`. No client-supplied actor or role is trusted.

| Route | Method | Rule |
|---|---|---|
| `/communities` | POST | Create a group, owner membership and `general` channel. |
| `/communities/{id}` | PATCH, DELETE | Owner edits or deletes. |
| `/communities/{id}/join`, `/leave` | POST | Join or leave with an account or browser session; owners transfer or delete first. |
| `/communities/{id}/members/{user_id}` | PATCH, DELETE | Owner appoints moderators; owner or moderator kicks eligible members. |
| `/communities/{id}/transfer` | POST | Owner transfers to a current member. |
| `/communities/{id}/channels` | POST | Owner creates a channel. |
| `/communities/{id}/channels/{channel_id}` | PATCH, DELETE | Owner sets the name, topic, slowmode, visibility and posting permissions, reorders channels, or archives, restores or removes a channel. |
| `/communities/{id}/channels/{channel_id}/messages` | GET, POST | Members read pages of up to 50 messages or post up to 2,000 characters. `before` loads older messages; `after` loads newer ones. |
| `/communities/{id}/channels/{channel_id}/messages/{message_id}` | GET, PATCH, DELETE | Open a message by ID. Author edits; author or moderator deletes. Deleted messages remain as empty tombstones for replies. |
| `/communities/{id}/channels/{channel_id}/messages/{message_id}/reactions` | POST | Add a reaction once per member. |
| `/communities/{id}/channels/{channel_id}/messages/{message_id}/reactions/{emoji}` | DELETE | Remove your reaction. |
| `/communities/{id}/channels/{channel_id}/messages/{message_id}/pin` | POST, DELETE | Owner or moderator pins or unpins. |
| `/communities/{id}/channels/{channel_id}/pins` | GET | Members list the latest 50 pins. |
| `/communities/{id}/messages/search?q=` | GET | Combine optional keyword `q`, exact display name `sender` and UTC calendar `date` (YYYY-MM-DD). At least one filter is required. Results include only visible channels. |
| `/communities/{id}/channels/{channel_id}/messages/{message_id}/dm` | POST | Start a private conversation with a current community member who posted the message. |
| `/communities/{id}/dms` | POST | Start a private conversation with an account member by `user_id` or an active guest by `guest_member_id`. |
| `/dms` | GET | List the current account's or guest session's latest 50 private conversations. |
| `/dms/{id}/messages` | GET, POST | Either participant reads paged history or posts a private message. |
| `/dms/{id}/messages/{message_id}` | PATCH, DELETE | The author edits or deletes their private message. |
| `/communities/{id}/invites` | GET, POST | Owner or moderator lists or creates links. |
| `/communities/{id}/invites/{invite_id}` | DELETE | Owner or moderator revokes a link. |
| `/communities/invites/{token}` | GET | Preview the community without joining or consuming an invite use. |
| `/communities/invites/{token}/redeem` | POST | Join through a valid link. |
| `/communities/{id}/moderation` | GET, POST | Owner or moderator reads events and bans, or kicks, bans and unbans. |
| `/communities/{id}/admin` | DELETE | StudySpot admin removes a group. |

Account owners are stored on the community; guest ownership is in the browser session. Account membership records store `member` or `moderator`; guest memberships have no moderator role. A moderator cannot act against an owner or another moderator. Account bans prevent joining, including through an invite, while public content remains readable. Guest membership cannot be banned reliably because clearing cookies creates a new identity. Invitation tokens are returned once at creation; only their SHA-256 hashes are stored. A maximum-use link increments only for a newly joined account or guest.

The current limits are five owned and 100 joined communities per account or browser session, 1,000 active members, 20 channels and ten active invites per community. Channel names are lowercase letters, digits and hyphens. Invites may expire after one to 720 hours and may cap successful joins at 1,000. These limits live in `communities/services.py` and serializers.

The browser fetches up to 50 channel messages at a time and requests newer IDs every three seconds while visible. It periodically reconciles loaded messages to pick up edits, deletions, pins, votes and reactions. Archived channels remain readable and reject new messages. Guest messages remain after the browser session expires, but the guest can no longer edit them once its membership expires. Clearing cookies loses the ability to manage a guest-created community or its messages.

On the `/communities` landing page, select **Join community** on an Explore card to join and enter its chat. For existing members the same card says **Open community**. The left sidebar lists communities by name. On phones, use the navigation button for communities and direct messages, or the channel button for channels in the current community. A community's Main tab fills the available workspace with channels, chat and a member list on wider screens. Members shows the full paged roster, including guests. Owners use the add button beside Channels to create a channel; Edit channel opens visible rename, archive and delete controls, while the three-dot menu also offers reordering. Deletion asks for confirmation. Share channel copies a URL containing the community and channel IDs; because communities are public, recipients join from that page and then land in the chosen channel. Private conversations are accessible only to their two participants, and a new conversation can be started only with a current member of a shared community. Guest DMs are bound to the browser session, so clearing cookies loses access to them.

## Using chat

- **Find a person.** Choose **New message** from any chat and enter at least two characters of a shared member’s name, or search in **Search people and communities**. Choose a name under **People in your communities** to open a private conversation. Results include current account and guest members of groups you have joined.
- **Set up a DM.** Use the gear in the conversation header to choose all messages, mentions only, or muted. The pin and search buttons open their respective panels.

- **Share a destination.** Copy channel link opens the selected channel. Create a seven-day invite from community settings to join and open that channel. Copy link on a message opens it directly, including messages outside the latest history page. Access checks still apply.
- **Compose a message.** Use Markdown for emphasis, backticks for inline code, triple backticks for code blocks and `||hidden text||` for a spoiler. Attach one file up to 2 MiB from the **+** menu or use the smile button to search emoji by name. Members open attachments on demand. Supported image, GIF and video formats have previews.
- **Respond.** Reply quotes a message in the current conversation. Thread opens a separate discussion attached to its starter. Either DM participant can pin a message. In channels, owners and moderators can pin. A poll takes a question and two to ten distinct choices. A voter can change their selection.
- **Control attention.** Choose all messages, mentions only or muted for each room. The in-app Inbox displays up to 30 unread notifications. Mark as read clears a room through its newest message. Mark unread moves the boundary back to the selected message. The mention picker includes people and, for channel moderators and owners, built-in roles, `@everyone` and `@here`. The latter targets people recently active in that channel. Typing indicators expire seven seconds after the last typing signal.
- **Manage a channel.** In Edit channel, owners can set a topic of up to 256 characters, restrict visibility or posting to moderators and the owner, or set a member cooldown of up to 21,600 seconds. Zero turns slowmode off. Editing or deleting a post does not reset the sender's cooldown.

The School field opens with familiar institutions and searches 6,089 distinct operating US postsecondary institution names from the October 2026 [College Scorecard institution download](https://collegescorecard.ed.gov/data/). The snapshot is in `src/frontend/static/schools.json` and can be refreshed with `uv run --project src/backend python data/schools.py`. The Course field opens with common course names and any course codes already used by communities at the chosen school. Both fields filter as students type, support keyboard selection, and allow other values. The federal institution file does not contain each school's course catalog.

Community creation, membership changes, invite redemption, moderation, and ownership transfers use database transactions. The account implementation should choose its `AUTH_USER_MODEL` before applying these migrations. Owners must transfer or delete their communities before account deletion. Other account deletion does not depend on historical invite or moderation actor rows.

On AWS, session-authenticated writes require the public CloudFront origin in Terraform's `django_csrf_trusted_origins`. Set this variable to the distribution's printed `https://...cloudfront.net` origin before enabling guest writes.

For a local demo, run `just seed` to populate the study groups with named participants and sample conversations. To add a sample conversation to an existing local channel, use its numeric channel ID in the following command from the repository root:

```sh
cd src/backend
DJANGO_DEBUG=true uv run --env-file ../../.env python manage.py seed_sample_communities --demo-channel 26
```

The inbox button opens a scrollable list of unread message cards. Each card opens its message. Right-click a community in the sidebar or open **⋯** beside its name for community actions. To role-play, choose **Invite people**, copy the link into a private browser window and choose **Accept invite**. Owners and moderators can also open **Manage** in the member list to view community settings. Owners can edit details, and changes save automatically.

To run the chat layout checks on a running local frontend with Chrome installed:

```sh
cd src/frontend
bunx bombadil browser test --headless --exit-on-violation --time-limit 30s http://localhost:7500/communities qa/chat.bombadil.ts
```

Use `--width 390 --height 844` to exercise the mobile navigation. The specification explores visible controls, checks for uncaught errors, and verifies the document and inbox fit the viewport. Set `CHROME` to a Chrome headless shell executable if the default browser cannot capture frames.

With the local demo running and at least one community present, run `node --test qa/community-menu.mjs` from `src/frontend` to check secondary-click menus and keyboard focus in Chromium.
