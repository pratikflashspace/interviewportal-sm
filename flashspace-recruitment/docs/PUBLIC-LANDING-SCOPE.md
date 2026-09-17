# Common landing and authentication popup

Approved DM 80160054324020; user deferred email provider confirmation in DM 80160054326162 and requested next work. Implemented on feat/teamrecrut-separated-workspaces only, root / route. Existing direct login/signup and candidate/recruiter workspace routes remain intact.

Common public page: Teamrecrut branding; About / How it works / Open roles; real persisted public roles through existing /api/roles; factual process/consent copy, no fake statistics or benefits. View role uses safe plain text with preserved line breaks. Continue to apply leads to authentication and the existing candidate workspace, not direct recording.

Login / Sign up opens a Dialog: session check, role selection, candidate or recruiter manual login. Existing manual login transport reused. Candidate signup allowed; no recruiter signup/Google/account provisioning. Account identity from server must match before navigation. Existing signed-in visitors see only their own workspace link, not role switching. Candidate signup leads to optional Complete My Profile or Go to dashboard; resume stays an HTTPS link in My Profile. Direct signup page remains as before; optional setup is currently part of this popup signup flow only.

Google remains on dedicated candidate login until verified there. No Google SDK or CSP expansion on public landing. Password recovery explicitly pending: no placeholder reset-submit action or false sent-email success. Email provider setup and actual reset implementation/verification remain separate follow-up work. No environment configuration, schema changes or deployment in this task.

Tests: five Node transport/role tests, two Python contracts and isolated Chromium UI acceptance with mocked auth/public-role boundaries. Existing full browser journey remains enabled; report/sync failure is not waived. Passing scoped UI tests is not proof of live authentication, delivery or production readiness.
