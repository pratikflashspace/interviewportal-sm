# Recruiter role management — staging only

## Scope
Existing authenticated admin/recruiter accounts can add, edit, preview, publish, close and move vacancies to draft. No account is promoted. Candidates and anonymous users cannot use management APIs. Existing session, SameSite cookie and Origin/X-Requested-With checks apply to every write. Text is rendered through React escaping, never HTML insertion.

UI: Recruiter workspace -> Manage roles, also in the sidebar for admins. Direct route `/recruiter/roles`. Fields: title, department, location/work mode, employment type, experience, short description, responsibilities/requirements and comma-separated skills. The editor requires complete fields even for drafts. New roles are always drafts regardless of submitted state/identity fields. Publishing/closing uses explicit confirmation and the last saved version. Editing an already-published role changes its public text on save; a visible notice explains this. Publish only real approved vacancies in production; staging remains synthetic.

## Architecture
`backend.role_server:create_app()` injects Sarvam into a RoleManagementApp extending the existing durable interview backend. It deliberately does not include the separate unapproved sync-watchdog branch.

- GET /api/admin/roles: all states, versions and timestamps for authenticated recruiters.
- POST /api/admin/roles: create a draft with a generated immutable role ID.
- GET /api/admin/roles/{id}: read saved preview data.
- POST /api/admin/roles/{id}: validated content update with expected version.
- POST /api/admin/roles/{id}/state: draft/published/closed transition with expected version.
- GET /api/roles returns only published candidate-facing fields.
- New applications reload database roles. Closed/draft roles reject new applications; existing applicants resume and finish using their saved role_snapshot.

There is no delete endpoint. Updates use a version predicate and return 409 for stale edits to prevent silent lost updates. One Gunicorn worker remains required as in the original app; do not scale workers until application mutations are designed for multiprocess concurrency. Refresh the candidate page to see newly published/closed roles; server-side validation still rejects a stale application to a closed role.

## Additive migration and stable mappings
On first startup, create `managed_roles` and seed the existing roles.json exactly once inside a transaction. Preserve IDs, content and published flags. A settings marker prevents future redeploys or roles.json edits from overwriting the database. Initialization serializes via PostgreSQL advisory lock or SQLite BEGIN IMMEDIATE. No existing application/settings tables or rows are dropped or rewritten.

The existing settings key `list:<role-id>` is preserved. Renaming does not change the role ID or an established ClickUp List mapping. The List may retain its earlier title intentionally. New Lists are created lazily by normal application sync, NOT when a role is published. If no mapping ever existed, first application sync resolves the List as before. Existing application role snapshots and task names remain unchanged. No candidate answers/reports are rescored by role edits.

## Rollout
Branch: feat/recruiter-role-management, based on feat/sarvam-interviews at b301c56fab4bb8ead909954320ded3fd6855dfb3. No Render changes were made as part of the branch implementation.

1. Confirm passing backend CI, frontend build and browser acceptance checks.
2. Use only the existing isolated staging service and its Test TeamRecrut database/private ClickUp test Folder. Take an approved database snapshot/backup before first deployment of this additive table; never copy production candidate data into staging.
3. Set branch to feat/recruiter-role-management and start command to:

```
gunicorn 'backend.role_server:create_app()' --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 120 --access-logfile /dev/null
```

Keep build/root/env settings and credentials unchanged. Do not trigger duplicate deploys if saving settings starts one. No paid resources, production deployment or merge is authorized by this guide.
4. Verify existing three roles preserve identities/content, candidate applications still resume, and existing ClickUp mapping remains unchanged. Publish only a fictional test role on staging, test candidate visibility/application creation, then close it and verify new applications fail while its existing interview continues.
5. Verify anonymous and candidate management access returns 401/403, duplicate edit versions return 409, and saved edits survive restart. Test narrow/mobile and keyboard form navigation, validation messages and preview before declaring UI ready.

Rollback restores feat/sarvam-interviews and backend.sarvam_server:create_app(). Leave managed_roles and marker intact; do not delete data. Old code reads roles.json and therefore temporarily hides newly database-managed roles, but existing application records/snapshots remain. Re-enable this version to restore managed vacancies. Do not accept applications during a rollback without reviewing visible roles.

## Tests and known release gates
Automated tests cover lifecycle, drafts/public filtering, auth/CSRF, version conflicts, stable identities/mappings, close/resume behavior, additive seeding and restart persistence, plus disposable real PostgreSQL persistence. Existing durable interview tests are inherited.

Frontend build: cd web && npm install --include=dev && npm run build. Browser tests and full live ClickUp sync must be verified separately. Backend CI alone is not proof of UI correctness.

Existing Sarvam provider disclosure/consent text still needs updating before real candidates. Existing Render Free/background sync limitations remain; this feature does not resolve the separate queue incident. Automated secret scanning may require repository security access; no credential values belong in code or test data.
