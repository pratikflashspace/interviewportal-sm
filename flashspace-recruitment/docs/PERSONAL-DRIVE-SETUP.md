# Personal Google Drive — recording integration setup

No company Google Workspace or Shared Drive is required. Use owner OAuth with offline access. Candidate uploads ultimately consume the consenting owner's My Drive storage. Never share Google passwords, tokens, downloaded OAuth client JSON or credential output in chat/GitHub.

## Current implementation status
This branch provides a local OAuth connection utility, private-folder validation, exact-ID upload initialization/reconciliation, a resumable Drive upload adapter and mocked security tests. It does NOT yet record camera media, provide an authenticated candidate upload route, persist upload sessions/chunks, implement private recruiter playback/ClickUp links, or deploy anything. A Drive resumable request alone does not preserve browser bytes across reload or Render restarts; the end-to-end recording pipeline must do so.

## Owner setup: personal account, one path
1. Sign into https://console.cloud.google.com/ with the Google account that owns recordings. Create/select a project named Flashspace Interview Recordings. No billing upgrade should be approved for this setup.
2. APIs & Services -> Library -> Google Drive API -> Enable.
3. Google Auth Platform (or OAuth consent screen) -> Branding: set application name/support contact. Audience: External. For a small staging test keep Testing and add only the Drive owner's email as a test user.
4. Data Access -> add scope https://www.googleapis.com/auth/drive.file. Do NOT choose full https://www.googleapis.com/auth/drive access.
5. Clients -> Create client -> Desktop app -> name Flashspace Drive Setup -> download the client JSON privately on the owner's computer. This is a local loopback consent tool, not a web OAuth client; do not set a Render callback for it.
6. On a computer with Python 3.12 and Git, use a private working directory:

```bash
git clone --branch feat/personal-drive-recordings https://github.com/pratikflashspace/interviewportal-sm.git
cd interviewportal-sm/flashspace-recruitment
python -m venv .venv
```

Activate the virtual environment (`source .venv/bin/activate` on macOS/Linux or `.venv\Scripts\activate` on Windows), then:

```bash
python -m pip install -r tools/drive-setup-requirements.txt
python tools/connect_personal_drive.py --client /PRIVATE/PATH/client.json --output /PRIVATE/PATH/render-drive.env
```

Replace paths with actual private local paths OUTSIDE the repository. Keep both client JSON and generated secrets private; don't upload or commit either file. If the desktop is shared, protect the output with OS account permissions; mode 0600 alone is not an ACL guarantee on Windows.
7. A Google consent window opens locally. Use the intended personal Drive account and verify the app/scope. Do not approve an unrelated/unrecognized app. The tool receives consent on localhost, creates an app-authorized folder and writes four settings to the requested private local file. No credentials are printed.
8. Enter those values in the existing staging Render Environment (Save only where supported): GOOGLE_DRIVE_CLIENT_ID, GOOGLE_DRIVE_CLIENT_SECRET, GOOGLE_DRIVE_REFRESH_TOKEN, GOOGLE_DRIVE_FOLDER_ID. Values in the file are JSON-quoted: when entering individual fields, use the decoded value without surrounding quotes. Do not change DATABASE_URL, current branch/start command, or Sarvam credentials.
9. Confirm in Google Drive that the new folder Flashspace Interview Recordings - Staging is Restricted. Add only authorized human reviewers individually when needed, not Anyone with the link. The tool creates no sharing permissions.

## Why a new folder instead of the pasted folder link?
The least-privilege drive.file scope only authorizes files created/opened through the app. Pasting an existing folder URL does not grant API access. This utility creates a dedicated new restricted folder automatically, avoiding broad access to the owner's personal Drive or additional Picker setup. The earlier shared folder is left untouched. Reusing that exact folder would require an explicit Google Picker authorization flow; do not expand to full-Drive scope just to avoid it.

## Testing-token and space limits
Google OAuth apps in External Testing with Drive access may receive refresh tokens expiring after seven days. This setup is for staging; re-consent may be necessary. Durable production authorization requires appropriate publishing/verification review, not repeatedly bypassing Google's consent. Drive storage quota is shared with the account's other data; API enablement does not create unlimited/free storage.

## Before recording is enabled
- Wire consent-based camera preview and audio/video capture, bounded chunk persistence and verified resumable upload finalization.
- Bind each upload/file ID to the authenticated candidate application; never accept arbitrary client Drive IDs/destination URLs.
- Enforce retention policy, delete failed/abandoned upload material and protect upload-session URIs as secrets. Retention is not approved yet: do not silently delete existing files or activate indefinite candidate collection.
- Provide an authenticated recruiter review page and stable ClickUp link. Do not place refresh tokens, upload session URIs or public video URLs in ClickUp.
- Confirm 30-day retention or another period and test permission denial, storage-full, interruption/restart, duplicate retries, missing camera, synchronized interviewer audio and authorized playback with fictional data.

## Scope of safety claims
No service account/domain delegation is required. The Drive account owner authorizes uploads. Folder validation denies public/domain-wide permissions visible to the adapter; it is not a full account-security audit. Only synthetic tests have run. No camera, live upload, paid resource, deployment or end-to-end success is claimed.

References:
https://developers.google.com/identity/protocols/oauth2/web-server
https://developers.google.com/identity/protocols/oauth2
https://developers.google.com/workspace/drive/api/guides/api-specific-auth
https://developers.google.com/workspace/drive/api/guides/manage-uploads
