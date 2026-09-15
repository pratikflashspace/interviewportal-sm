# Candidate Dashboard — page-scoped implementation

Approved in DM 80160054296651 in response to the Dashboard proposal. Branch: feat/teamrecrut-separated-workspaces. Only /candidate/workspace/dashboard receives the new component. Other pages, signup/login, recruiter dashboard, interview, backend schemas and runtime remain unchanged. No deployment or external configuration is authorized by this implementation.

## Design and data

Preserve Manrope/Hind, Teamrecrut purple/lilac/white cards, fixed desktop sidebar and slim header with top-right My Profile. Narrow screens use a wrapping candidate navigation rather than overflow. Workspace and Account groups only. Resume links point to the existing persisted HTTPS-link editor and are labelled Link only; file upload remains unavailable. No recruiter affordances.

Fetch /api/me before requesting dashboard data. Only stored candidate role AND admin=false may render the shell. Existing server endpoints enforce ownership/role rules. Then fetch candidate applications, own profile and applied-role recommendations concurrently, using same-origin credentials and no-store. Thirty-second abort timeout and unmount cancellation; an error never becomes a zero count. Refresh loads current data, not hard-coded metrics.

Cards: Applications = submitted application rows; Interviews = completed / total rows with an actual interview or completed status; Shortlisted = current shortlisted stage. No fabricated scheduling dates. Profile completeness = seven equally weighted supplied text sections: summary, education, experience, skills, projects, job preferences and resume link. A visible expandable checklist states what contributes and distinguishes supplied information from validation or suitability. No AI scoring, eligibility or ranking.

Recommendations use the existing server rule: other published Stirring Minds roles sharing applied-role snapshot skills or department. Candidate profile skills do not alter matches. Display only public job fields, no internal metadata. New candidates and candidates with no related vacancies see honest empty states. View role uses the existing CareersDialogs; Apply reuses existing application-to-interview behavior, including returning to an already submitted application rather than creating duplicates. It does not start recording.

## Tests and release gates

Node tests cover empty/real counts, unknown/malformed data, completeness denominator, whitespace, greeting boundaries, role checks, safe public fields and request semantics. Isolated real WSGI tests cover candidate data isolation, recruiter denial and applied-role rather than profile-based recommendations. Chromium tests use mocked candidate responses for precise UI scenarios; no real provider or production data. Existing full browser journey is not skipped.

No new database migration, environment value, recruiter provisioning, Google activation or deployment. Broader branch report/sync failure and prior deployment/backup/schema/Google acceptance gates remain separate. Do not describe this page as live until an authorized deployment is verified.
