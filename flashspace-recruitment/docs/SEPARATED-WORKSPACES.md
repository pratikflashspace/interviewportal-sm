# Teamrecrut separated workspaces — branch implementation

Approved scope: implement on feat/teamrecrut-separated-workspaces, based on 9f73a85e68a8908199737fe381da2068037c7e19. No deployment, main merge or actual account provisioning is authorized by this branch work.

## Goal and design

Public role-first entry; separate candidate and recruiter workspaces with top-right My Profile; preserve purple/lilac Manrope/Hind identity. Candidates manage their own profiles and applications; one explicitly authorized Stirring Minds recruiter manages jobs and reviews evidence. Candidate-only Google plus manual login. No assessments or numeric rankings. Apply leads to the saved application's existing interview room after consent/device checks.

Architecture: WorkspaceApp subclasses the current integrated backend without replacing it. A distinct tr_session cookie prevents accepting legacy sessions. The stored account role, not user input, gates every inherited candidate/recruiter API. Existing users/applications/roles are retained. Profiles use an additive table keyed by authenticated user id and conditional version writes. Case-insensitive normalized email uniqueness spans both roles. Candidate recommendations use only their applied role snapshots and published jobs, with an explicit skills/department reason and no invented match percentage.

## Implemented foundation

- Candidate email/password signup/login; server-validated role selection; salted scrypt password hashes.
- Recruiter email/password validation limited to TEAMRECRUT_RECRUITER_EMAIL; no public signup or Google route. Access FAILS CLOSED pending activation/MFA integration; no password-only fallback.
- New-cookie authentication, old login endpoint rejection, role checks on APIs and recording routes.
- Own-profile read/write, role-specific field allowlists, optimistic version checks; email/role changes forbidden through profile. Resume link supported, file upload not yet implemented.
- Similar published Stirring Minds jobs based on applied roles.
- Regression tests cover cross-role access, email collisions, profile ownership, stale writes, logout and no automatic recruiter creation.

## Release blockers — not implemented/configured

1. Recruiter single-use activation delivery, TOTP enrollment/verification, secure secret storage and recovery. Confirm recovery policy and authorized recruiter email through secure setup. Do not paste passwords or secrets in ClickUp.
2. Candidate Google OAuth: authorized OAuth client, redirect origins, verified token/sub binding, state/nonce/PKCE and candidate-only account linking. No Google button until operational; no auto-linking privileged accounts.
3. Candidate password recovery and secure email-change flows require an email delivery service. Profile email is currently read-only deliberately.
4. Secure persistent resume uploads (type/size checks, scanning, restricted downloads, retention) and durable recording storage; existing temporary recording restrictions remain.
5. Remaining interview UX removals/recovery approval and full live media E2E. Existing interview module retained, not claimed to satisfy all revised UX.
6. PostgreSQL/concurrent-user integration testing of new migrations and a backup/recovery rehearsal before rollout.
7. Repository automated secret scanning unavailable without GitHub Advanced Security; require approved alternative/security review before deployment.

## Operations

Do not change the deployed entrypoint to WorkspaceApp. It intentionally has no production create_app factory until release blockers are resolved. No credentials embedded or fetched. Existing deployment remains unaffected. Regression tests use SQLite and fake AI, not live candidate/provider data. A frontend feature harness can exercise implemented APIs against a local WorkspaceApp instance, but that is not a live release.

Review in small increments. No dummy metrics, non-working menu entries, or statements that partially implemented authentication is release-ready. Existing recruiter account is NOT provisioned by this module.
