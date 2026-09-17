# Explore Jobs: saved role data, candidate page only

Approval: DM 80160054299576 responding to scope proposal 80160054298869. Implemented on feat/teamrecrut-separated-workspaces only. No deployment, role mutation, migration, recruiter changes, new provider or account provisioning.

## Source of truth

Read the existing /api/roles endpoint after candidate identity is checked. No screenshot text is copied into a seed or database write. Sales, Operations, AI Marketing and AI Engineer continue to use the records maintained by the existing recruiter workflow. Job text, punctuation and whitespace are retained. The longer AI Engineer details contain responsibilities and a Requirements section; display these verbatim with pre-wrap instead of flattening the lines. Do not guess or manufacture separate requirement/experience/eligibility values. Additional structured fields are displayed only if actually returned; internal role version/notes are excluded.

## Search and filtering

Search covers titles, skills, descriptions, details and saved labels, using case-insensitive AND keyword matching. Six filters use distinct exact values from returned jobs: department, experience, location, work mode, employment type, skills. There is currently no independent work-mode field in the persisted role model. The Work mode filter explicitly uses the stored combined location/work-mode label when no work_mode field is returned; it does NOT infer Remote, On-site or Hybrid from free text. For example Remote/On-site - Both Available remains that value. The page explains this. Missing fields show Not specified. Experience is a label filter, not a candidate eligibility calculation. Clear filters resets search and all filters; result count is computed, not hard-coded.

## Flow

Only /candidate/workspace/jobs changes. Preserve the purple/lilac candidate shell with fixed desktop sidebar, Workspace/Account navigation, no recruiter links, and top-right My Profile. Existing Resume link-only disclosure remains. View role uses the same Dialog primitives, colours and application language as the approved prior version. Saved role details are plain text, not executable HTML. Existing hiring-process copy is explicitly the common application/interview/human-review flow, not a fabricated per-role process.

Apply checks the candidate's actual applications first: an active application resumes its existing interview; completed applications open My Applications. New applications use the existing CareersDialogs form and submitCareerApplication helper. Existing consent, validation, uniqueness/idempotency and role closure checks remain server-side. No recording is started from this page. Busy guards prevent repeated local submissions; timeouts warn to check My Applications before retrying. Server role-bank mapping failures are errors, not fabricated interview readiness.

## Verification and rollout

Eight Node logic/transport tests and two Python scope tests; isolated browser coverage for filters, exact multiline content, modal, clear/no-results, error retry, candidate denial, responsive layout and Apply/resume. Synthetic browser data never represents live vacancies. Existing full application/voice/report journey remains enabled. Broader known report/sync failure is outside this page scope and is not waived. No schema/environment/runtime or live role changes. Staging and Google deployment approvals/backup guards remain unchanged.
