# Accounts

Students and business owners can sign up, verify their email, log in, log out and reset a forgotten password.

Sign-up starts on StudySpot's own page, `/signup`. It asks whether the account is for a student or a business, and for a username or a business name; a username's availability is checked as it is typed. It then hands over to [Auth0](https://auth0.com)'s hosted page for the email and password, which never pass through StudySpot. When the browser comes back and the email is verified, StudySpot finishes the sign-up with the answers it kept, so nobody is asked twice. Log-in, verification emails and password resets are Auth0's too.

StudySpot keeps an `Account` row per person, recording whether they are a student or a business owner.

Accounts are optional for running the site. With no Auth0 settings, `GET /auth/config` reports `{"enabled": false}`, the header shows no log-in controls, and search works exactly as before.

## How it fits together

```text
Browser ──(1) log in / sign up / reset password──▶ Auth0 hosted page
   ◀──(2) redirect to /callback with a one-time code─┘
   │
   ├──(3) exchange code for an access token (Auth0 SPA SDK)
   │
   └──(4) GET /api/account   Authorization: Bearer <access token>
                             X-ID-Token: <ID token>  ──▶ Django
                                   verifies both RS256 signatures against the
                                   tenant's public keys; no call to Auth0
```

The API never calls Auth0 at request time. It verifies each token's signature against the tenant's public keys (JWKS), its issuer, its audience and its expiry. The deployed API has no route to the internet (see `infra/terraform/network.tf`), so Terraform passes those public keys in as `AUTH0_JWKS`. Locally, leave `AUTH0_JWKS` blank and the API fetches them.

An access token says who someone is but not their email. The browser therefore also sends the ID token from the same log-in, which carries the email and whether Auth0 has verified it. The API trusts it only if its signature, issuer and expiry check out, it was issued to this application, and it names the same person as the access token; otherwise it is ignored, not refused.

The first `GET /account` after a sign-up creates the account. Its `account_type` stays `null` until sign-up is finished, which normally happens by itself with the answers from `/signup`, and otherwise on `/account`:

- **Student:** needs a verified email at a university domain (anything ending in `.edu` by default; set `STUDENT_EMAIL_DOMAINS` to change it) and a username. The username comes from Auth0 when the database connection requires one. Otherwise, as with "Continue with Google", the student picks one on the same page: 3 to 30 letters, numbers, dots or underscores, unique regardless of case.
- **Business:** needs a verified email and a business name.

The choice is made once.

## Setting up Auth0

Auth0's free plan covers this project. Do this once per team; everyone shares the tenant.

1. **Create a tenant** at <https://manage.auth0.com>. Its domain looks like `studyspot.us.auth0.com`.

2. **Create an API** (Applications → APIs → Create API).
   - Identifier: `https://api.studyspot.app`. This becomes `AUTH0_AUDIENCE`; it does not need to resolve.
   - Signing algorithm: RS256.
   - Under its settings, turn on **Allow Offline Access**, so the browser gets refresh tokens.

3. **Create an application** (Applications → Create Application → *Single Page Web Applications*). Its Client ID becomes `AUTH0_CLIENT_ID`. Under Settings, list both the local and the deployed origin:

   | Setting | Value |
   |---|---|
   | Allowed Callback URLs | `http://localhost:7500/callback, https://d1ulyrfyi06kwp.cloudfront.net/callback` |
   | Allowed Logout URLs | `http://localhost:7500, https://d1ulyrfyi06kwp.cloudfront.net` |
   | Allowed Web Origins | `http://localhost:7500, https://d1ulyrfyi06kwp.cloudfront.net` |
   | Allowed Origins (CORS) | the same two origins |
   | Refresh Token Rotation | on |

4. **Configure the database connection** (Authentication → Database → Username-Password-Authentication).
   - Optionally, turn on **Requires Username**, so students can also log in with a username instead of their email. Without it, students choose a username on StudySpot when finishing sign-up, and log in with their email.
   - Enable the connection for the application from step 3.
   - Auth0 sends verification and password-reset emails from this connection. The built-in email provider is rate-limited and meant for testing, which is fine for a demo. Connect a real provider under Branding → Email Provider before real users arrive.

5. **Allow the application to use the API.** If the API's User-delegated Access is set to "Per-app authorization", authorize the application on the API's Application Access tab. Otherwise Auth0 refuses every log-in with "Client … is not authorized to access resource server".

6. **Optional: add a claims Action** (Actions → Library → Create Action → *Login / Post Login*). Not needed: the API reads the email from the ID token. With this Action the access token carries the email itself, and the Auth0 username as well, which is useful to any other client of the API that has no ID token to send:

   ```js
   exports.onExecutePostLogin = async (event, api) => {
     const namespace = 'https://studyspot.app/';
     api.accessToken.setCustomClaim(`${namespace}email`, event.user.email ?? '');
     api.accessToken.setCustomClaim(`${namespace}email_verified`, event.user.email_verified === true);
     api.accessToken.setCustomClaim(`${namespace}username`, event.user.username ?? '');
   };
   ```

   Deploy it, then add it to the Login flow (Actions → Triggers → post-login). The namespace must match `AUTH0_CLAIM_NAMESPACE`, which defaults to the value above.

## Configuration

| Variable | Where | Meaning |
|---|---|---|
| `AUTH0_DOMAIN` | API | The tenant domain. Blank switches accounts off. |
| `AUTH0_CLIENT_ID` | API | The SPA's Client ID. Public: the browser reads it from `GET /auth/config`. |
| `AUTH0_AUDIENCE` | API | The API identifier from step 2. |
| `AUTH0_JWKS` | API | The JSON from `https://<domain>/.well-known/jwks.json`. Required when deployed; optional locally. |
| `AUTH0_CLAIM_NAMESPACE` | API | Prefix of the Action's claims. Defaults to `https://studyspot.app/`. |
| `STUDENT_EMAIL_DOMAINS` | API | Comma-separated domain suffixes a student email may end in. Defaults to `edu`. |

The frontend build needs none of these: it asks the API at runtime. Locally, put them in `.env`; `docker compose` and `just dev-backend` both read it. For a deployment, set `auth0_domain`, `auth0_client_id`, `auth0_audience` and `auth0_jwks` in `infra/terraform/terraform.tfvars`:

```shell
curl -s https://studyspot.us.auth0.com/.well-known/jwks.json
```

Auth0 changes these keys only when someone rotates the signing key in the dashboard. If that happens, re-apply with the new document, or every log-in will be refused with a 401.

## Routes

### `GET /auth/config`

Public. Returns either `{"enabled": false}`, or:

```json
{
  "enabled": true,
  "domain": "studyspot.us.auth0.com",
  "client_id": "abc123",
  "audience": "https://api.studyspot.app"
}
```

### `GET /account`

Needs `Authorization: Bearer <access token>`, and takes the ID token from the same log-in in `X-ID-Token`. Creates the account on first use, and copies the email and its verification from the tokens each time.

```json
{
  "email": "ada@nyu.edu",
  "email_verified": true,
  "username": "ada",
  "account_type": null,
  "business_name": "",
  "created_at": "2026-10-27T12:00:00-04:00"
}
```

### `POST /account`

Needs a bearer token. Finishes sign-up, once:

```json
{ "account_type": "student" }
```

```json
{ "account_type": "student", "username": "grace_h" }
```

The second form is for a student whose Auth0 log-in carried no username. One who already has an Auth0 username cannot choose a different one.

```json
{ "account_type": "business", "business_name": "Grumpy Coffee" }
```

Returns the account with `201`. Possible errors:

- `401` without a valid token.
- `409 conflict` when sign-up is already finished.
- `422 validation_error` with one of these in `details`:

| `field` | `type` | Meaning |
|---|---|---|
| `body.email` | `email_unverified` | Auth0 has not verified the address yet. |
| `body.email` | `not_a_student_email` | A student account needs a university address. |
| `body.username` | `required` | A student account needs a username and none was chosen. |
| `body.username` | `invalid_username` | The chosen username is not 3 to 30 letters, numbers, dots or underscores. |
| `body.username` | `username_taken` | Another account has that username, in any case. |
| `body.username` | `not_allowed` | A different username than the one Auth0 already holds. |
| `body.business_name` | `required` | A business account needs a name. |

### `GET /usernames/{username}`

Public. Whether a student could choose `username` now, with the same rules `POST /account` applies:

```json
{ "username": "grace_h", "available": true, "reason": null, "message": null }
```

```json
{ "username": "Ada", "available": false, "reason": "username_taken", "message": "That username is taken." }
```

`reason` is `invalid_username` or `username_taken`. The answer is advice: two people can see the same name as free, and `POST /account` decides.

## Not yet built

These parts of the accounts epic are still to come:

- Editing a student profile (university, courses, subjects).
- Choosing which profile fields other students can see.
- Editing a business profile (contact email, phone number).

Each will add fields to `Account` or a model beside it. Logging in will not change.
