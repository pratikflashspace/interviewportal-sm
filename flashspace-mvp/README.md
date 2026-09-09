# Stirring Minds · Flashspace Careers

A focused recruitment MVP: candidate account → role application → four-question AI voice interview → ClickUp candidate task with profile, transcript, summary and evidence-based provisional scores.

**This implementation is independent of the earlier AI Recruitment System architecture.** It is deliberately small: React, a Python WSGI API, SQLite on a persistent Render disk, OpenAI, and ClickUp API v2.

## What is included

- Responsive candidate website, role search and department filters.
- Candidate registration, password login, logout and saved applications.
- Resume/portfolio **link** plus relevant experience. Binary resume uploads are not included.
- Four interview questions: one role-specific opening and three adaptive AI follow-ups.
- Push-to-talk audio recording (up to two minutes per answer), server-side transcription, editable transcript before submission, AI-generated spoken questions and a typed-answer alternative.
- Durable application records and interview progress across restarts.
- Background generation of a summary and three rubric scores with quote validation. A deterministic equal-weight formula converts the scores to /100.
- Recruiter-only application view, transcript/report downloads, task link and ClickUp retry action.
- Automatic ClickUp List per role, one task per candidate-role application, updated as the interview progresses.
- Durable sync/retry state. A failed AI report still allows the transcript to reach ClickUp.
- Render Blueprint, a prebuilt **live-mode** frontend, editable frontend source, server source and backend tests.

The ClickUp-hosted preview is intentionally a simulation, with fictional roles/candidates and tab-local storage. It does not authenticate candidates, call AI, or change ClickUp. This source package contains the live implementation. It has **not been deployed or tested against your paid provider accounts**.

## Deploy on Render

1. **Create a private Git repository** and upload this folder's contents into its root, including `web/dist`. Do not commit credentials. The included `.gitignore` excludes `.env` and local databases. This is a Python web service, **not** a Render Static Site.
2. **Set the real vacancies in `roles.json`.** The three examples are deliberately `published: false`. Replace their titles, descriptions, requirements, locations and skills with your actual vacancies, then set only approved roles to `published: true`. IDs must be unique lowercase letters/numbers/hyphens and should remain stable. Role-file changes require a redeploy but not a frontend rebuild.
3. **Create or choose a private ClickUp hiring Folder** with appropriate hiring-team access. Obtain its numeric Folder ID and a server-side API token that can read/create Lists and read/create/update tasks in that Folder. Use a dedicated, appropriately restricted account where possible. Do not use the personal List ID as a Folder ID. No existing workspace structure has been changed by this build.
4. **Create a Render Blueprint** from the repository. It reads `render.yaml`. Review the paid Starter plan, 1 GB persistent disk and the example `singapore` region **before accepting charges**. Change the region if needed for your data handling requirements. OpenAI and ClickUp have their own processing locations and terms; the compute region is not an end-to-end residency guarantee.
5. **Enter secrets only in Render's environment settings:**

   | Environment variable | Value |
   | --- | --- |
   | `OPENAI_API_KEY` | A server-side OpenAI project key with billing and access to the configured models |
   | `CLICKUP_API_TOKEN` | Token from your permitted ClickUp account |
   | `CLICKUP_FOLDER_ID` | Numeric ID of the private hiring Folder |
   | `ADMIN_EMAIL` | Exact email address for your recruiter login |
   | `ADMIN_PASSWORD` | A unique password of at least 16 characters |

   Defaults: `OPENAI_MODEL=gpt-4o-mini`, `OPENAI_STT_MODEL=gpt-4o-mini-transcribe`, `OPENAI_TTS_MODEL=gpt-4o-mini-tts`. These are configurable implementation choices, not requirements from an earlier plan. Verify availability and billing on your account. `MAX_AI_CALLS_PER_DAY=500` limits provider calls, **not currency spend**; also set provider budget alerts/limits.
6. **Wait for the service to deploy.** The build installs Gunicorn and runs 25 isolated backend tests; it serves the included prebuilt frontend. The SQLite file is created at runtime at `/var/data/flashspace.sqlite3`, not during the build. The health endpoint is `/api/health`.
7. **Open the Render URL and run the acceptance checks below.** The normal Render domain is picked up from `RENDER_EXTERNAL_URL`. If you add a custom domain, set `APP_ORIGIN=https://your-exact-domain` with no trailing slash and use that URL. This controls CSRF validation and Secure session cookies. Do not use wildcard origins.
8. **Log in via Recruiter workspace** using the admin credentials. The admin account is bootstrapped only when its email does not already exist. Changing `ADMIN_PASSWORD` later does not reset an existing database password; use the maintenance command below.

### How ClickUp records are organized

```text
Your private hiring Folder
└── Growth & Partnerships [Flashspace:growth]        ← List, created on first application
    └── Candidate | Growth & Partnerships | FS-…    ← one task per application
        Profile + email + portfolio + experience
        Consent version and timestamp
        Application/interview status
        Interview summary and provisional score
        Criterion scores, reasons and exact quotes
        Full question-and-answer transcript
```

List IDs and task IDs are retained locally for subsequent updates. Repeated application submissions return the existing candidate-role application. Remote creates are reconciled by a stable application reference before retrying. ClickUp has no cross-system transaction here, so a rare ambiguous timeout/eventual-consistency race can still require a recruiter to reconcile duplicates. This is not an exactly-once guarantee.

The app **owns the generated task name and description**. Put recruiter notes in task comments or separate custom fields; manual description edits will be replaced at the next sync. Interview status and scores are text in the generated description, not mapped to ClickUp custom fields or task statuses. Deleting/moving managed tasks or role Lists outside the app needs manual reconciliation of stored IDs. The app does not synchronize edits back from ClickUp.

The worker runs every 10 seconds and retries failures with a capped exponential delay up to 15 minutes. A candidate's application is saved before the external sync occurs. “Queued” and “Retry pending” are never presented as “Synced.” The recruiter can request another retry. Failed report generations are also bounded by per-application AI quotas; quota exhaustion requires waiting for its window to expire, not repeated retries.

## Acceptance checks before inviting real candidates

1. Confirm that only actual published vacancies appear. Confirm that there are no demo candidates in live mode.
2. Register two test candidates with different emails. Verify that each can only see their own applications and that candidate credentials cannot open recruiter reports.
3. Apply to a role, log out, log back in and resume. Reapplying to that role should return the same application rather than create another record.
4. Record a real answer over HTTPS. Check microphone permission denial, Safari/Chrome audio-format support, and the typed alternative. **Listen to and verify AI-generated audio disclosure and transcription quality with representative accents.** The practice screen uses browser speech synthesis; interview speech uses the server-side provider.
5. Complete all four questions. Check that answers persist on refresh, duplicate submissions do not advance twice, and unfinished interviews cannot be submitted.
6. As a recruiter, wait for/report-refresh the application. Verify the summary, score calculation and every quote against the actual transcript. Scores are unverified and advisory, not a hiring decision.
7. Verify the List and task in the intended private ClickUp Folder. Confirm the profile, consent timestamp, four Q&A turns, summary and scoring reasons all arrived.
8. In staging, temporarily use an invalid ClickUp token, submit a test application, and check retry status. Restore the valid token and verify recovery without losing data. Do not test outages against real candidate sessions.
9. Restart/redeploy the service. Verify existing accounts, applications and task identities remain intact on the disk.
10. Publish your actual candidate privacy notice, retention duration, privacy contact and process for accommodation/access/deletion before public launch. The included Help & privacy screen contains a launch reminder to replace in `web/src/generated/components.jsx`, then rebuild the frontend. Review provider data handling agreements; this app makes no zero-retention claim about external vendors.

## Local development

Python 3.12+ is required. The API and tests use the standard library; only the production server requires Gunicorn.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Export values from .env.example into your environment securely.
# No .env file is auto-loaded. Set APP_ORIGIN=http://localhost:8000 locally.
python -m backend.server
```

Open `http://localhost:8000`. The included frontend is live mode, so it uses local API endpoints. Publish a test role and set provider credentials to run real interviews. The Python development server is only for local use. Do not expose it publicly.

### Edit and rebuild the frontend

The prebuilt `web/dist` is included and is the frontend Render serves. After a source edit, **rebuild and commit the updated dist** before redeploying. Source edits alone do not change that prebuilt output.

```bash
cd web
npm install
npm run build
```

Node 20+ is required. Direct dependency versions are pinned in `package.json`. Generate, review and commit a lockfile on your machine, then use `npm ci` for future builds. The build uses esbuild, Tailwind and PostCSS, and creates hashed JS/CSS assets. `dist/runtime.js` sets live mode before the bundle runs. No API key belongs in that file, a frontend build variable, or client-side storage.

Key files:

```text
backend/server.py             API, auth, AI adapter, ClickUp adapter, worker, storage
roles.json                    Real roles and publication controls
web/src/App.jsx               Main candidate/recruiter website
web/src/generated/components.jsx  Interview UI, login/application/report dialogs
web/src/generated/api.js      Live API adapter and separately gated preview adapter
web/src/generated/styles.css  Brand and responsive styling
web/ui/                       Accessible interface components
web/build.mjs                 Standalone frontend build
web/dist/                     Prebuilt live frontend served on Render
render.yaml                   Service, secrets and persistent disk settings
manage.py                     Privileged password reset and consistent backup
```

The `generated` directory name is historical; these three files are editable source, not regenerated by the build.

### Test

```bash
python -m unittest discover -s tests -v
```

25 tests cover account/session behavior, CSRF, per-candidate authorization, consent, unpublished roles, duplicate applications and turns, completion, mocked audio transport, score privacy, evidence validation, AI/ClickUp failure recovery, and remote task reconciliation. **All pass in the build environment.** Provider transport is mocked in these tests: passing does not verify the actual accounts, provider models, microphone hardware, Render deployment or hiring fairness.

The interactive preview's full candidate journey was also exercised in a browser at desktop size, along with the recruiter report and a 390-pixel mobile layout. The standalone live frontend builds successfully; final live browser-to-provider acceptance must happen on your deployment.

## Operations and boundaries

- This is a **low-volume pilot**, not a production-hardened public hiring platform. Run **one Gunicorn worker** with threads and **one Render instance**. A local synchronization lock serializes interview writes/provider operations. Migrate the database and queue before scaling beyond a small pilot.
- Disk-backed services have brief deploy interruption and cannot horizontally scale. Do not switch to a free ephemeral service or remove the persistent disk. Keep tested, encrypted/off-service backups. ClickUp is a hiring record mirror, not an account/operational database backup.
- Opaque session tokens are stored hashed in SQLite. Cookies are HttpOnly, SameSite=Strict, and Secure over HTTPS. Passwords use salted scrypt. Candidate data is authorized server-side; admin status is never accepted from a registration request.
- The API requires an exact trusted Origin and an application-specific header for writes, enforces request sizes and quotas, and does not fetch arbitrary resume URLs. Provider calls have timeouts. Raw audio is held temporarily in process memory and never saved as an application file. External provider retention remains subject to the configured account terms.
- Logs omit application bodies and provider response bodies. App access logging is disabled in the provided Gunicorn command. Infrastructure-provider logs remain governed by that provider's settings.
- Registration has email-format validation but **no email verification, CAPTCHA or self-service password recovery**. Before a wider public launch, add verified-email ownership, abuse controls and a recovery channel. Current per-IP throttling uses the server-provided address, which can aggregate users behind a proxy; tune it after verifying Render's trusted proxy behavior rather than trusting arbitrary forwarded headers.
- No automated hiring, rejection, ranking, shortlisting or email notifications. No personality/emotion inference, camera monitoring, protected-attribute evaluation, resume parsing, calendar scheduling, binary uploads, ATS bidirectional sync, assessment engine or enterprise multi-tenancy.
- All three score dimensions have equal weight: `round((sum of 0–5 criterion scores) / 15 * 100)`. A quoted claim is not independent verification. Validate the rubric for each role and have a human review relevant evidence. No score threshold automatically changes a hiring outcome.
- Retention and deletion are **manual operational responsibilities in this MVP**. Do not assume deleting a ClickUp task deletes the SQLite data or vice versa. Before public launch, implement and test coordinated deletion/export across the database, ClickUp and backups, alongside your published retention policy.

### Privileged maintenance

Use the Render service shell (not a one-off job, which cannot access its disk). Verify the person's identity before account recovery.

```bash
python manage.py reset-password recruiter@example.com
# Enter the new password interactively, never as a command-line argument.
# Revokes all existing sessions for that exact account.

python manage.py backup /var/data/backups/flashspace-2026-09-09.sqlite3
# Copy the consistent backup to secure off-service storage and test restoration.
```

Do not copy a live SQLite file with ordinary `cp` while writes are happening; use the included database-native backup command. Backups contain candidate personal data and password hashes and require restricted access and retention controls.

## API references used for this implementation

- Render Blueprint configuration: https://render.com/docs/blueprint-spec
- Render persistent disk constraints: https://render.com/docs/disks
- ClickUp List creation: https://developer.clickup.com/reference/createlist
- ClickUp task creation: https://developer.clickup.com/reference/createtask
- OpenAI voice pipeline options: https://developers.openai.com/api/docs/guides/voice-agents
- OpenAI transcription: https://developers.openai.com/api/docs/guides/speech-to-text
- OpenAI structured outputs: https://developers.openai.com/api/docs/guides/structured-outputs
