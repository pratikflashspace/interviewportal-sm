# Step: recruiter hiring decisions → ClickUp

Branch-only enhancement to feat/teamrecrut-separated-workspaces. No deployment, real recruiter provisioning or live ClickUp writes performed by implementation/tests.

## Gap fixed

Previously a recruiter stage change saved workspace_records/workspace_events without incrementing the applications version. The existing worker would not know the record needed syncing, and its description omitted the hiring stage.

## New contract

- Authenticate the authorised recruiter using existing stored-role/session checks.
- Validate the hiring stage/version and current interview completion.
- Save stage, audit event and application sync-version increment in one database transaction. A failure rolls back all three. Existing interview JSON, evidence, recording reference and ClickUp task identity are not rewritten.
- Wake the existing worker only after commit. Pending work remains in the database across process restart.
- WorkspaceClickUp preserves the existing transcript/evidence/recording description and adds current human hiring stage and last-decision timestamp. No internal actor identifier or support/profile data is exported.
- Update the existing task description using existing reconciliation/retry behavior. No ClickUp status-list mapping, extra comments, notifications or emails are introduced. Contacted remains a recorded recruiter stage, not proof of message delivery.
- A new decision made while a previous sync is in flight increments version again; completion of the older sync cannot mark the newer version as synced.

## Verification scope

Regression tests exercise actual workspace/worker logic with ClickUp network calls mocked: existing-task PUT and preserved content, failed provider call/retry, stale decision rejection, atomic rollback, newer decision during sync, malformed payload rejection, no-decision compatibility. Existing role/auth/sidebar tests remain required. Automated CI results are recorded in draft PR #15.

This is implementation and automated verification, not live provider acceptance. PostgreSQL locking/concurrency/rollback must be verified on a separate disposable test database before rollout. Existing duplicate-task reconciliation is best-effort, not an exactly-once remote API guarantee. The existing deployment is unchanged.

## Subsequent steps

1. Complete resume file upload with persistent restricted storage and file validation/scanning, not just links.
2. Candidate-only Google OAuth and email recovery setup (credentials/provider approval required).
3. Final interview UI/recovery cleanup and full browser/API/media acceptance.
4. Security/backup/migration verification, then explicitly approved staging rollout and real-provider smoke tests.

This note supersedes earlier statements that hiring decisions are not wired to ClickUp in the branch; live sync remains unverified until an approved rollout.
