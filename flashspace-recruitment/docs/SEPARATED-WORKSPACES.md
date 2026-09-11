# Teamrecrut separated workspaces — branch status

Scope: feat/teamrecrut-separated-workspaces only, based on staging 9f73a85e68a8908199737fe381da2068037c7e19. No deployment, main merge or actual account provisioning performed.

## Latest confirmed auth decision

Creator identified team@stirringminds.com as the sole recruiter account and explicitly deferred MFA. The branch now permits password login ONLY when that email already exists with the recruiter role and a matching salted password hash. Public signup and Google recruiter login remain forbidden. Candidate registration reserves the recruiter email even before provisioning. An environment override cannot silently substitute another recruiter. The email is an identifier, not a credential. No actual account/password was created.

MFA is not a first-release prerequisite. First-time provisioning and secure credential delivery remain an administrative action requiring authorization; no fake activation or recovery email is sent.

## Design and data

Role-first public entry -> separate auth -> role-specific workspace. Existing purple/lilac Manrope/Hind identity, top-right My Profile, shared role-detail/application dialog. WorkspaceApp is opt-in and uses tr_session rather than legacy fs_session. Role checks apply server-side to candidate/recruiter APIs, including inherited recording routes. Normalized email index prevents cross-role reuse. Profile and settings changes use versioned writes. New tables are additive; accounts/roles/interview answers are not erased.

Hiring decisions are stored separately from the interview's submission state, so changing a hiring stage cannot restart or discard answers. Stage changes append an event with actor, timestamp and stage. Candidate timelines omit actor/internal evaluation. No arbitrary assessment stages or scores are introduced.

## Sidebar coverage in this branch

Candidate:
- Dashboard: actual application, completed-interview, shortlist and open-role counts; similar published Stirring Minds roles from applied role skills/department.
- Explore Jobs: live data, keyword/location/skill search and department filter; full role dialog and v2 application submission. Existing applications resume.
- My Applications: current hiring stage, interview status, timeline, refresh/filter and resume/review links.
- My Interviews: completed/in-progress filtering and existing interview routes; legacy applications get an isolated legacy view, not the mixed dashboard.
- My Profile: persistent own-field editing, protected email/role.
- Resume: persistent HTTPS resume link and open-link action. FILE UPLOAD NOT IMPLEMENTED.
- Settings: persisted work-mode/location preferences; password change verifies current password and revokes every session. Email changes/deletion use support, not pretend instant actions.
- Help & Support: in-app request creation, own request history and recruiter replies. No email delivery claimed.

Recruiter:
- Dashboard: real counts and links to work.
- Jobs: existing create/edit/save draft/preview/publish/close functionality reused.
- Candidates: only people with applications; search, profile/resume-link details and application-specific evidence links.
- Applications: filter/refresh and human hiring-stage updates (applied, under review, shortlisted, contacted, hired, rejected) with version checks/timeline. Interview must be completed before review/selection stages. Contacted is a recorded status, not an email action.
- Interviews: status filters and protected evidence review.
- Analytics: application/interview counts, completion rate (unavailable for zero denominator), hiring-stage counts and per-job counts. NO candidate scores or rankings.
- Company: versioned Stirring Minds website/description editing. No multi-company switch.
- Settings: password change/session revocation; MFA deferred.
- Help & Support: persisted inbox with reply and resolution actions. Replies are in-app only.
- My Profile: top-right, persistent recruiter-specific fields.

No Team sidebar: additional recruiter accounts/team administration are outside the agreed single-account release. No assessments/scoring/ranking menu. Saving preferences is supported; no notification-email subscription is claimed.

## Remaining integration/release work

- Candidate Google OAuth setup, verified token/sub binding, state/nonce/PKCE and candidate-only linking. No fake Google button. Requires approved OAuth client/redirect configuration, no secrets in ClickUp.
- Resume file upload, scanning, authorized download and retention. Current link-based resume is usable but not file storage.
- Password recovery/verified email changes and first-time credential delivery require secure administrative/provider setup; existing password change works.
- Current integrated interview is retained, including earlier technical recovery controls; the revised interview cleanup/recovery/accessibility work and complete live voice journey remain unfinished.
- Reviewer legacy report coverage, application snapshots of profile data and support/admin decisions sync to ClickUp require further integration tests. New hiring events/company/support data are stored in app DB, not claimed synced to ClickUp.
- Production backup/migration/concurrency tests, durable recordings and security review. Automated GitHub secret scanning unavailable without Advanced Security. No claim of full security clearance.
- Validate all sidebar behavior in a full browser against the new backend, not just component mocks/builds.

## Local integration

Build web, then run `uvicorn backend.workspace_local_asgi:app --host 127.0.0.1 --port 8000 --workers 1` with synthetic local data. That harness refuses Render/DATABASE_URL. The frontend in this branch needs WorkspaceApp; do not deploy it with the old backend runtime. No production entrypoint changed. Existing deployed website is unaffected.

Tests: real WSGI requests against isolated SQLite for role/login policy, profile/settings persistence, stale writes, support ownership/replies, password/session revocation, actual counts and human hiring transitions. CI/build results are tracked in draft PR #15. Passing these does not prove Google, resume uploads, live speech or deployment readiness.
