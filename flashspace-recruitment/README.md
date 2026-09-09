# Stirring Minds · Flashspace Recruitment MVP

## ONE COMPLETE PACKAGE: use this for a fresh upload

This folder contains the original application plus the latest Render Free / Cloudflare updates already combined. **You do not need any earlier ZIP or patch.** It is not the Cloudflare Workers/D1 hosting version.

### What runs where

- **Render Free:** Python backend and the built React website.
- **External PostgreSQL (for example, Neon Free):** candidate accounts, sessions, applications, transcripts and retry state.
- **Cloudflare Workers AI through your AI Gateway:** speech-to-text, interview questions, summaries, provisional scores and text-to-speech.
- **ClickUp:** a List per role and one task per candidate-role application with the profile and interview report.

Cloudflare is used for AI inference, not website hosting or a CDN/security proxy. No OpenAI API key, Cloudflare Worker deployment, D1 or paid Render disk is required. Cloudflare AI usage may incur charges, and all free-tier quotas still apply.

## Fresh GitHub upload: exact steps

1. Extract `Flashspace-Final-Complete-Render-Cloudflare.zip` on your computer.
2. Open the extracted **`flashspace-recruitment`** folder. Inside you should see `backend`, `web`, `tests`, `README.md`, `roles.json`, `render.yaml` and the remaining root files.
3. Create a **new private GitHub repository** for the clean upload, or use an already-empty repository. Keep your old repository as a backup; these instructions do not require deleting it.
4. On GitHub, select **uploading an existing file** (or **Add file → Upload files**).
5. Drag **everything INSIDE `flashspace-recruitment`** into the upload area, not the enclosing folder and not the ZIP. Preserve `backend/`, `web/` and `tests/` as folders. Include the hidden `.gitignore` and `.env.example`; enable hidden-file display if needed.
6. Commit with message **Upload complete Render and Cloudflare MVP**.
7. Verify that **`render.yaml` appears directly on the repository main page**, and `web/dist` contains `index.html`, `runtime.js` and an `assets` folder with JS/CSS files.
8. Follow **[DEPLOY-ON-RENDER.md](DEPLOY-ON-RENDER.md)** for the database, environment settings, build/start commands and live acceptance checks. Connect Render to this newly uploaded repository/branch, not the older repository by accident.

If uploading into a nonempty repository instead, files at matching paths are overwritten, not merged. Review any teammate changes first. This complete download cannot include changes made privately in your GitHub repository, which was not accessible for verification.

Expected repository root:

```text
backend/
web/
tests/
.env.example
.gitignore
README.md
DEPLOY-ON-RENDER.md
manage.py
render.yaml
requirements.txt
roles.json
```

**Do not copy a separate `cloudflare/` folder or any earlier patch into this project.** All files needed for this chosen architecture are included. Real credentials must only be entered in Render Environment settings, never GitHub or chat. Revoke the Cloudflare API token exposed earlier and use a replacement.

## Before candidates can use it

The supplied `roles.json` contains fictional example vacancies with `published: false`. Replace them with your real vacancies and set approved roles to `true`. If you previously customized roles in GitHub, preserve/copy those real values into this file: they could not be retrieved from your private repository.

Create a dedicated PostgreSQL database and set the Render variables listed in DEPLOY-ON-RENDER.md. The application refuses to store production data in ephemeral local SQLite. Database tables are created at startup. This is a new installation, not an automatic migration of old Render/Cloudflare candidate data.

## Interview behavior

Candidate records an answer, stops recording, reviews the STT transcript, then submits it. The AI generates the next question and TTS speaks it when the candidate selects **Hear question**. Candidates can type instead. There are four questions.

STT uses Cloudflare-hosted Whisper Large V3 Turbo; TTS uses Deepgram Aura-2 English through Cloudflare. Follow-up questions/reports default to Llama 3.1 8B Instruct Fast through Cloudflare. **This is push-to-talk, not Flux WebSocket continuous streaming or automatic end-of-turn detection.** The app does not persist raw audio; external provider handling remains subject to account terms.

Scores are unverified advisory evidence. A human makes hiring decisions. The app checks quoted evidence against the transcript and does not silently save invented quotes as valid scores.

## Development

Python 3.12+:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Export required environment variables securely. No .env file is auto-loaded.
python -m backend.server
```

For local development use `APP_ORIGIN=http://localhost:8000`; do not set this on Render. Production commands are in DEPLOY-ON-RENDER.md. Keep one Gunicorn worker.

The built frontend is included in `web/dist`, so a first Render deployment does not need a Node build. To edit it, install Node 20+ and run:

```bash
cd web
npm install
npm run build
```

Commit the updated `web/dist` alongside source changes. The root Render build serves those prebuilt files. Direct frontend dependencies are pinned; create, review and commit an npm lockfile on your development machine for future repeatable builds. No lockfile was fabricated in the sandbox.

## Tests and validation limits

```bash
python -m unittest discover -s tests -v
```

At packaging: **46 tests passed; 1 live PostgreSQL integration test was skipped** because no disposable PostgreSQL connection was available. Cloudflare and ClickUp calls are mocked in the local tests. The complete frontend builds and its asset paths are verified; the updated screens were reviewed at desktop/mobile sizes.

The optional Postgres test requires `TEST_POSTGRES_URL` pointing to a dedicated test database. It creates and drops its own unique schema. Do not set it to a production database in Render's build configuration.

**This is a prepared pilot codebase, not a deployed or production-certified system.** Real database connectivity, provider permissions, billing, model response formats, audio hardware/browser support and scoring quality still need the acceptance checks in DEPLOY-ON-RENDER.md.

## Important pilot boundaries

Render Free sleeps when idle. Background jobs also stop polling after 10 minutes without non-health requests, allowing Neon to sleep; queued work remains durable and resumes when the website is visited again. Do not promise instant reports around the clock on free hosting.

No email verification, self-service password recovery, automated retention/deletion, binary resume uploads, proctoring or enterprise multi-tenancy is included. Publish your privacy contact and retention policy, establish coordinated deletion/export across PostgreSQL and ClickUp, and test backups before inviting real candidates.

The generated ClickUp task name/description belong to the app and can be overwritten on later sync. Put recruiter notes in comments or separate fields. There is no bidirectional ClickUp sync and no automatic hiring/rejection action. Ambiguous API timeouts may require manual duplicate reconciliation.
