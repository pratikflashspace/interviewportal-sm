# Approved login pages — implementation scope

Creator approved the proposed candidate/recruiter login pages in DM 80160054158475 after page-by-page design review. Work is on feat/teamrecrut-separated-workspaces. No staging/main merge, deployment, real account provisioning or provider changes authorized by this increment.

## Changed

New isolated LoginPage component + scoped CSS + login-client module. main.jsx intercepts only /candidate/login and /recruiter/login; existing candidate signup, account selection, dashboards and interview pages remain as-is. Compact white rounded card, lilac background, existing Manrope/Hind and Teamrecrut waveform identity. No workspace sidebar before authentication.

Manual login uses existing role-specific backend routes with same-origin credentials/CSRF header, a bounded request, no automatic retry, no credential logging or local/session storage. Required/email/password field validation, password visibility toggle, loading guard and cancellation on unmount. Successful response must match the selected role before navigating to that role's dashboard. Server remains the authority; client role checks grant no permissions. Existing cross-role backend checks and single recruiter identity are unchanged.

401 shows generic wrong credentials; 429 shows a wait message; missing endpoints, server errors and malformed/mismatched success responses show service-unavailable rather than invalid-email/Not found. Do not use friendly errors to claim the server problem is resolved.

Candidate login links to existing candidate signup. Google/recovery controls are intentionally not rendered because those integrations remain unconfigured. Recruiter has no Google/signup/MFA, and no public disclosure of the authorised email. No real recruiter password created.

## Preview vs application

The visual preview reuses LoginPage with fictional READ-ONLY details and injected simulation, not live login. It never calls the application or stores passwords. Scenario/role controls belong only to the preview wrapper; the actual website has separate role routes, not an in-workspace role switch. Preview navigation announces its destination without inventing unimplemented pages.

## Verification

JS transport tests cover both endpoints/destinations, password whitespace preservation, missing/invalid responses, credential and network failures, throttling, role mismatch, timeout and abort. Python CI wrapper runs these plus scoped route contracts. Browser tests are performed using the same component and simulated authentication, not real provider/backend credentials. Whole-branch report/media integration still requires its own passing result.

The currently deployed old staging backend cannot serve the new role-specific routes. This branch-only UI implementation must not be deployed alone against that backend. Broader staging backup/schema/report gates remain separate; no database export is needed to inspect this visual preview.
