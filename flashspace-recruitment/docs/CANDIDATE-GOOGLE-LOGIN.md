# Candidate Google login — branch implementation, not deployed

Scope: candidate Google signup/sign-in on `feat/teamrecrut-separated-workspaces`; preserve manual candidate login and single recruiter manual login. The approved compact lilac/white login layout is unchanged apart from the candidate Google section. No Google UI or endpoint is enabled for recruiters. No changes to unrelated dashboards or interview UI.

## Flow and security

GET `/api/auth/candidate/google/config` reports enabled/disabled. Disabled UI explains pending configuration and retains manual login; it never loads Google or fakes success. When enabled, POST `/challenge` creates a five-minute, one-use database nonce bound to an HttpOnly, Secure, SameSite=Strict, host-only cookie. GIS renders its official popup button with that nonce; One Tap and auto-select are not used. The callback sends the credential in a same-origin JSON POST with existing Origin/custom-header protection. The server uses google-auth signature verification and explicit issuer, audience, authorized-party, expiry, issued-at, verified-email and nonce checks. No ID token enters URLs, logs or browser storage.

Identities are keyed by Google subject, not email. Candidate users are created atomically with the identity mapping, with an unrecoverable random password hash. Existing manual accounts are not silently merged. Recruiter email and admin accounts cannot acquire candidate Google identities. Changed identity emails fail closed rather than being silently updated. Third-party Google email identities without an authoritative Gmail/Workspace domain use manual authentication pending an additional ownership-verification design. This is deliberate partial coverage, not support for all Google account types.

Expired/used challenges, provider timeout, invalid claims, account collision and rate limits produce actionable messages without disclosing provider payloads. A fresh explicit retry gets a new challenge. Cancelled popup does not disable manual login. Candidate tokens and newly provisioned synthetic test accounts are never real production credentials.

## External configuration remains unverified

The public Client ID and user-reported Web application / External audience / staging JavaScript origin are recorded in the code and prior discussion. Publishing status, test-user access and an actual Google popup sign-in are NOT independently verified. No client secret is needed for this GIS ID-token flow.

Activation is OFF by default. Only after approved secure provider setup and staging acceptance preparation may an operator set:
- `GOOGLE_CLIENT_ID`: the user-supplied public client identifier.
- `TEAMRECRUT_CANDIDATE_GOOGLE_ENABLED=true`.
- `TEAMRECRUT_GOOGLE_VERIFIED_ORIGIN`: the exact verified APP_ORIGIN.

No environment values were set by this implementation. `workspace_staging_asgi` uses the Google-capable subclass; the currently deployed old interview entrypoint is untouched. Do not deploy the frontend by itself against the old backend. Existing staging-only origin/database/schema approval guards remain enforced.

## Additive database changes

Two tables: `candidate_google_identities` (unique subject, unique user FK) and `candidate_google_challenges` (hashed cookie token, expiry). No existing credentials, users or applications are rewritten. Initialization is behind the existing staging schema-approval entrypoint when deployed. Backup and schema review are still required; do not set the staging approval flag without the creator's explicit acknowledgement. Existing ephemeral recording loss risk on redeploy remains.

## Verification

`python -m unittest discover -s tests -v` includes synthetic WSGI tests and real RSA-signed JWT validation with mocked Google public-key retrieval, plus executable Node transport tests. These tests do not contact Google, provision external accounts, or prove live microphone/interview/report behavior. Whole-branch CI and live Google acceptance must be checked separately; a known broader report-and-sync browser failure is not waived.

Live acceptance: Google new candidate; returning same subject; manual candidate login unaffected; manual-account collision safely rejected; recruiter Google unavailable; cancel popup/manual fallback; wrong test-user/origin errors; protected candidate workspace and sign-out. Use controlled test accounts only. No production release authorised.
