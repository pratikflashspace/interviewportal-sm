# Staging workspace preview activation

Creator requested deploying the completed work in the active DM. This is staging preview only, not a main/production release. Do not merge the feature branch to main. Current tested entrypoint and scope are tracked in draft PR #15.

## One-time user actions before activation

1. Finish active interviews, download needed temporary recordings and take a fresh snapshot/backup of the staging Neon database. This preview creates additive workspace tables plus a normalized unique email index; duplicate normalized emails cause startup to fail rather than silently merge identities. Existing submitted answers/roles are not intentionally deleted. Recovery of a backup has not been rehearsed here.
2. In the existing Render service interviewportal-sm-1, choose branch `feat/teamrecrut-separated-workspaces` and set Start Command:
   `uvicorn backend.workspace_staging_asgi:app --host 0.0.0.0 --port $PORT --workers 1`
3. Add non-secret environment flag `TEAMRECRUT_STAGING_SCHEMA_APPROVED=true` ONLY after step 1 and approval of the additive schema initialization. Existing APP_ORIGIN must be `https://interviewportal-sm-1.onrender.com`; retain existing DATABASE_URL/Sarvam/ClickUp settings. Do not paste any secrets into chat.
4. Keep root directory `flashspace-recruitment` and current build command. Choose Save without deploy while preparing settings, if offered, so branch/runtime/flag are activated together. Then deploy once. Avoid duplicate manual deploy if Render has already started one automatically.

The connected Render integration cannot change branch or start command; this requires the dashboard. Triggering deploy before changing them would redeploy the old version. Do not switch to workspace_local_asgi; it deliberately refuses hosted environments.

## Preview limitations

Manual candidate registration/login and the approved dashboard features are included. Recruiter login is limited to a previously provisioned team@stirringminds.com account; the entrypoint does NOT provision it or reset a password, and MFA is deferred. If that approved account does not exist in staging, recruiter access remains unavailable until separately authorized secure provisioning. Other existing admin identities are not promoted or repurposed.

Candidate Google login, resume file uploads (links only currently), email recovery, production retention/security verification and real-provider end-to-end validation remain unfinished. Do not introduce real candidates to this preview. Existing legacy sessions do not become authenticated workspace sessions; users sign in again.

## Verification and rollback

Verify exact deployed commit, startup, /api/health, public roles, candidate login/profile/application flow, recruiter authorization and provider responses. Health alone is not feature acceptance. Synthetic CI does not prove live Sarvam/ClickUp configuration. GitHub Advanced Security scanning is unavailable; no full security clearance is claimed.

For a failed preview, restore the previous branch `feat/integrated-interview-recording` and start command `uvicorn backend.interview_release_asgi:app --host 0.0.0.0 --port $PORT --workers 1` in Render. Avoid destructive database rollback: new tables can remain, and a data restore requires separate approval. Temporary recording files lost during replacement are not recovered by reverting code.
