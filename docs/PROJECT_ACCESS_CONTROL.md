# Project-level access control (membership & access requests)

> Shipped 2026-07-04. Companion to [`TEAM_ACCESS_CONTROL.md`](./TEAM_ACCESS_CONTROL.md) — read that one first. This doc exists because the two levels were never contrasted anywhere, which is exactly why the gap described below went unnoticed for a while.

## The two levels, side by side

Doctus has **two** authorization layers, not one:

| | Team | Project |
|---|---|---|
| Purpose | Which org unit a user belongs to | Which specific `Project` within their team(s) a user can see/use |
| Model | `Team`, `TeamMembership` | `Project.team_id` (FK), `ProjectMembership` (`role`: `admin`/`pruefingenieur`/`member`, changeable after the fact via `PATCH /projects/{id}/members/{user_id}`), `ProjectAccessRequest` (`pending`/`approved`/`rejected`) |
| Admin-only actions | Create/rename/delete team, manage team membership | Add/remove project members, resolve access requests |
| Who can act | Global admin (`ADMIN_EMAILS`) | Global admin, the project creator, or any `ProjectMembership.role == "admin"` |
| UI | `SettingsModal.tsx` → Teams tab (admin-only nav entry) | `SettingsModal.tsx` → Projects tab, per-project expandable Members panel + "Discoverable Projects" section |
| Backend | `backend/core/teams.py`, `backend/api/teams.py` | `backend/core/projects.py`, `backend/api/projects.py` |

**Team membership is still the only access *primitive*** (per `TEAM_ACCESS_CONTROL.md`) — a user must be on a project's team before they can even request project access. Project membership is a second, finer-grained gate *within* a team: being on the right team makes a project discoverable and requestable, it does not itself grant access to the project's content.

Since 2026-07-09 (commit `2fc42f0`), `ProjectMembership.role` has a third value, `pruefingenieur`, sitting between `admin` and `member`: it grants no member-management rights but does gate one specific action — approving/reverting compliance alerts (`assert_can_approve_compliance` in `backend/core/projects.py`), which a plain `member` cannot do. See `docs/GAPS.md` #5 for the broader RBAC context this partially closes.

## Why this needed its own pass

The project-membership backend (`ProjectMembership`, `ProjectAccessRequest`, 7 endpoints under `/projects/{id}/...`) was built after the team layer and was already fully correct server-side, but had **zero frontend surface** — no way for a user to request access to a project, and no way for a project admin to see or approve requests, through the app. In practice only the project creator (auto-admin on `create_project`) could ever use a project; anyone else needed the API called directly. That gap is what this pass closed.

While auditing it, one real bug surfaced (not a documentation issue): `request_access` never checked that the target project's team was one the requesting user could see, so a user in Team A could request — and, if approved, receive — access to a Team B project, silently crossing the team boundary `TEAM_ACCESS_CONTROL.md` treats as the one access primitive. Fixed by adding the same `assert_team_visible` check already used everywhere else in `projects.py`.

## What shipped

- **`backend/api/projects.py`**: `request_access` now team-checks before creating a `ProjectAccessRequest` (404, matching the existing wording convention — see `TEAM_ACCESS_CONTROL.md`'s "404 vs 403" note). New `GET /projects/discoverable`: projects in the caller's own team(s) with no existing `ProjectMembership` for them (id/name/description only) — registered *before* `GET /{id}` in the router, since FastAPI's `int` path converter 404/422s on a literal `"discoverable"` segment if the routes are declared in the other order.
- **`frontend/app/services/api.ts`**: `getDiscoverableProjects`, `requestProjectAccess`, `getProjectAccessRequests`, `resolveProjectAccessRequest`, `getProjectMembers`, `addProjectMember`, `removeProjectMember`.
- **`frontend/components/SettingsModal.tsx`** (Projects tab):
  - Each project row gets a "Members" toggle (people icon) that expands to: the member list with role badges, an admin-only add-member picker (via `getUsers`, mirroring the Teams tab's pattern), and — for admins — a pending-access-requests list with approve/reject buttons.
  - A "Discoverable Projects" section below the active-projects list, populated from `GET /projects/discoverable`, with a "Request access" button per row that becomes "Requested" once clicked (no polling needed — the backend already no-ops a duplicate pending request).
  - `isProjectAdmin(project)` is computed client-side (`currentUser.is_admin || project.creator_id === currentUser.id || own membership role === "admin"`) rather than via a new `is_project_admin` field on `serialize_project`, since the members list (which any member, not just an admin, can already fetch) is enough to derive it.
- **Tests**: `backend/tests/test_project_membership.py` — cross-team request rejected (404, regression test for the bug above), `discoverable` excludes joined/foreign-team projects and doesn't break the `/{id}` route, approving a request creates membership, non-admin members get 403 on member/request management endpoints, the project creator can't be removed.

## Known non-goals (left as-is)

- No UI-side notification when a new access request arrives — an admin has to open the Projects tab and expand a project to see pending requests. Fine for the pilot's team sizes; revisit if this becomes a real workflow bottleneck.
- `GET /projects/discoverable` doesn't indicate "you already have a pending request" — the frontend tracks that locally per session (cleared on modal reopen) rather than round-tripping it from the backend. A user who re-opens the Settings modal after requesting will see the button reset to "Request access", but clicking it again is a harmless no-op server-side.
