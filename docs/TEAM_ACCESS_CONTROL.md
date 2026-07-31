# Team-based access control for Repositories & Knowledge Sources

> Implementation plan, approved 2026-06-18. **Status: shipped and verified 2026-07-04** — see "Post-implementation notes" below for the points where the actual implementation diverged from this plan.

## Status

- [x] 1. Models + migration (`Team`, `TeamMembership`, `team_id` columns, backfill)
- [x] 2. `core/teams.py` helper + `ADMIN_EMAILS`
- [x] 3. `repositories.py` enforcement + tests
- [x] 4. `knowledge_sources.py` enforcement + tests
- [x] 5. `chat.py` enforcement (repo_id/source_id validation + global-sources fix) + tests
- [x] 6. `entity_links.py` enforcement + tests
- [x] 7. `knowledge_links.py` enforcement + tests
- [x] 8. `graph.py` enforcement + tests
- [x] 9. `search.py` / `services/search.py` enforcement + tests
- [x] 10. `topics.py` → admin-only router switch
- [x] 11. `link_chat.py` — shipped team-scoped (not admin-only)
- [x] 12. Admin API (`teams.py` + `users.py`) + `/auth/me` extension + schema additions + `main.py` wiring
- [x] 13. Frontend (api.ts, page.tsx state, Teams tab in SettingsModal.tsx, project-creation team selector)

## Post-implementation notes (2026-07-04 review)

Verified against the current code (`backend/api/*.py`, `backend/models/database.py`, `frontend/`): 23/23 backend tests green (`docker exec doctus-backend python -m pytest tests/`), `npx tsc --noEmit` clean. A few things landed differently than this plan originally spec'd:

- **`team_id` lives on `Project` and `KnowledgeSource`, not on `Repository`.** A `Project` layer was introduced after this plan was written (repos became a knowledge source grouped under a project); `Repository` inherits its team via `Repository.project.team_id` rather than its own column. `assert_team_visible`/`get_visible_team_ids` are used the same way this plan describes, just one hop further through `project`.
- **No separate `TeamsPanel.tsx` or Sidebar entry.** Team management shipped as a `teams` tab inside `SettingsModal.tsx` (nav item gated by `currentUser?.is_admin`), not a standalone component. Simpler, same admin-only visibility guarantee.
- **`link_chat.py`** ended up team-scoped (`get_visible_team_ids` filtering both `Project` and `KnowledgeSource` queries) rather than staying an open question.
- **Test coverage is consolidated, not per-file.** Coverage lives in `backend/tests/test_teams.py` (admin CRUD: create/list/members/delete) and `backend/tests/test_teams_helper.py` (unit tests for `is_admin`/`get_visible_team_ids`/`require_admin`/`assert_team_visible`), plus the `test_team`/`test_project` fixtures used throughout `conftest.py`. The itemized per-router cross-team 403/404 test matrix in the original "Tests" section below was not built out 1:1 — enforcement code is in place, but there's no standing regression test asserting e.g. "team-B repo returns 404 for a team-A user" per router. Worth adding if this area sees more changes.
- **A second, finer-grained layer sits on top of this one:** project-level membership (`ProjectMembership`/`ProjectAccessRequest`) gates access to individual `Project`s *within* a team. See [`PROJECT_ACCESS_CONTROL.md`](./PROJECT_ACCESS_CONTROL.md) — it was built after this plan and, until 2026-07-04, had no frontend surface at all.
- **Post-2026-07-04 addendum:** a further `Project`-layer refactor moved several routers from `repo_id`/`team_id`-shaped enforcement to `project_id`/`assert_project_visible`. The worked code samples and per-router tables further down in this plan (`repositories.py`'s list endpoint, `graph.py`, `entity_links.py`, `knowledge_links.py`, `search.py`) describe the **pre-refactor** shape and no longer match the current routers verbatim — e.g. `repositories.py` has no list/create endpoint anymore (repo CRUD moved to `projects.py`), `graph.py`/`entity_links.py`/`knowledge_links.py` are entirely `project_id`-keyed now, and `search.py` filters via `get_visible_project_ids` rather than a `repo_id` subquery. The *conclusion* (full per-router enforcement, no unauthorized cross-team/cross-project access) still holds and is arguably more granular than originally planned — treat the sections below as historical design rationale, not a current API reference; see [`PROJECT_ACCESS_CONTROL.md`](./PROJECT_ACCESS_CONTROL.md) for the current shape.

## Context

Today every authenticated user can see and modify every `Repository` and `KnowledgeSource` in a Doctus install — there is zero per-team isolation (confirmed: ~40+ endpoints across 8 router files take a `repo_id`/`source_id`/`entity_id`/`link_id` with no ownership check at all). The customer's real org structure is teams of people working on specific projects, with supervisors spanning multiple teams and admins seeing everything. This is needed **before** the first pilot customer launches (confirmed with the user), not a fast-follow.

Locked-in decisions (confirmed with the user):
- Team membership is managed natively in Doctus (not synced from the IdP's OIDC groups — left open for later).
- A `Repository`/`KnowledgeSource` belongs to **exactly one** team.
- Full coverage is required, not a partial fix.

## Design

**Team membership is the only access primitive.** A user can belong to N teams (many-to-many). A "supervisor" is simply a user who is a member of more than one team — no separate supervisor role. **Admin** is the one real extra role: a global bypass that sees and manages everything, bootstrapped via a comma-separated `ADMIN_EMAILS` env var in `backend/core/config.py` (same pattern as `OIDC_*`/`FRONTEND_URL`/`LOG_LEVEL`) rather than a `User.role` column — this avoids a chicken-and-egg "who grants the first admin" problem and needs no schema/UI to bootstrap.

**Data model:**
- New `teams` (id, name, created_at) and `team_memberships` (id, user_id FK, team_id FK, unique(user_id, team_id)) tables.
- `Repository.team_id` and `KnowledgeSource.team_id`: required FK columns. `KnowledgeSource` gets its own `team_id` even when `repo_id IS NULL` (a "global" source still needs a team).
- Downstream tables (`CodeEntity`, `CodeReference`, `DocumentChunk`, `EntityDocLink`, `KnowledgeLink`) get **no** `team_id` column — their team is derived by joining through their `repo_id`/`source_id` FK. Adding a redundant column there would be denormalization with no safety benefit (verified: every one of these rows already chains back to a `Repository` or `KnowledgeSource`).

**Topics — admin-only in v1, not team-scoped.** Topics/TopicNode exist specifically to group nodes *across* repos — exactly the boundary a supervisor most wants to cross. Giving `Topic` its own `team_id` would foreclose that and require resolving 4 different node types back to a team at attach-time. The safer, much simpler v1 choice: make the whole `topics` router admin-only (`dependencies=[Depends(require_admin)]` in `main.py`, replacing `_authenticated` — zero internal changes to `topics.py`, zero schema change). Documented gap, not a leak — revisit post-pilot if the customer needs team-scoped or cross-team topics.

**404 vs 403:** for team-scoped resources, a cross-team lookup returns **404** with the same wording the codebase already uses ("Repository nicht gefunden") — knowing "this exists, you're just not on the team" is itself a small leak of org structure. Use **403** only for true authorization failures on a request's own input that isn't a lookup (e.g. "create this repo under a team you're not in"). Leave the existing chat-session 403 (`delete_chat_session`) as-is — that's ownership, not team scope, a separate and already-correct mechanism.

**Migration mechanics:** there is exactly one existing Alembic revision, `backend/alembic/versions/b42f8210a7ea_baseline_schema.py` (`down_revision = None`). A real customer install already has it applied, so the new tables/columns must be a **new incremental revision** (`down_revision = 'b42f8210a7ea'`), not an edit to the baseline. The migration backfills non-disruptively: create one "Default Team", add every existing `users` row as a member, set `team_id` to that team on every existing `repositories`/`knowledge_sources` row — current single-team-implicit deployments keep working with zero admin action.

**Enforcement pattern:** confirmed there's no current per-endpoint user-injection beyond what each endpoint opts into — `main.py`'s router-level `dependencies=[Depends(get_current_user)]` only raises 401 on failure, it discards the resulting `User`. Every endpoint that touches `Repository`/`KnowledgeSource` (directly or via FK) needs `user: User = Depends(get_current_user)` added to its own signature (exactly the pattern already used and tested in `chat.py`'s recent ownership fix), then either filters a list query or 404s a single lookup via one new shared helper.

## New helper: `backend/core/teams.py`

```python
def is_admin(user: User) -> bool: ...                       # user.email.lower() in cfg.ADMIN_EMAILS
def get_visible_team_ids(user, db) -> Optional[list[int]]:  # None = admin/unrestricted, else the list
def require_admin(user=Depends(get_current_user)) -> User:  # 403 dependency for admin-only routers
def assert_team_visible(team_id, user, db, not_found_detail): # 404 if not visible
```
`backend/core/config.py` gains `ADMIN_EMAILS: set[str]` (comma-separated, lower-cased, same `.split(",")` shape proposed for env-driven lists elsewhere in this codebase).

## Representative endpoints (the pattern to copy everywhere else)

**List endpoint** — `GET /repositories` (`backend/api/repositories.py`):
```python
def list_repositories(db=Depends(get_db), user=Depends(get_current_user)):
    team_ids = get_visible_team_ids(user, db)
    q = db.query(Repository)
    if team_ids is not None:
        q = q.filter(Repository.team_id.in_(team_ids))
    return [_serialize_repo(r) for r in q.all()]
```
`_serialize_repo` gains `team_id` in its output (frontend needs it later).

**Create endpoint** — `POST /repositories`: `RepoCreate` schema gains `team_id: int`; validate `team_ids is None or repo.team_id in team_ids` else **403** (this is request-input validation, not a lookup).

**Single-resource endpoint** — `GET /repositories/{repo_id}/files` and siblings: look up the `Repository` row first (note: `list_repo_files`, `get_file_content`, `get_repo_stats` currently take **no `db` param at all** and only touch the filesystem — they need one added), 404 if missing, then `assert_team_visible(repo.team_id, user, db, "Repository nicht gefunden")` before doing the filesystem/DB work. Same shape for `/file-content`, `/stats`, `/entities`, `/knowledge-sources`, `/references`, `/sync`, `DELETE /{repo_id}`.

**Body-supplied scope ID** — `POST /chat` (`backend/api/chat.py`): validate `request.repo_id`/`request.source_id` against the user's team_ids *before* using them (404 if invalid), the same way path params are checked. Needs `Repository` added to `chat.py`'s imports.
**Important fix bundled into this same commit:** line ~201's `global_source_ids = db.query(KnowledgeSource.id).filter(KnowledgeSource.repo_id == None).all()` has **zero team filter** today and feeds into all three branches below it (explicit `source_id`, explicit `repo_id`, and the no-scope-at-all case) — must become `.filter(KnowledgeSource.team_id.in_(team_ids))` (skip the filter for admins). Verified live in the current code — this is the single biggest latent leak once teams exist: a non-admin user with no `repo_id`/`source_id` in their chat request currently gets answers grounded in every team's global knowledge sources.

## Remaining files — same mechanical pattern, one commit per file, tests green after each

| File | What needs the pattern |
|---|---|
| `backend/api/knowledge_sources.py` | create (schema gains `team_id`; when `repo_id` is set, force `team_id` to equal the parent repo's — don't trust the client), list, delete, sync, resolve, content, raw, upload |
| `backend/api/entity_links.py` | all `repo_id`-path endpoints (lookup-then-check); `update_link_status`/`delete_link` need `EntityDocLink.repo_id` → `Repository.team_id` join |
| `backend/api/knowledge_links.py` | `KnowledgeLink` rows reference two sides (`entity` or `document`) — resolve both sides' team, require **both** visible (conservative: avoids "something exists in another team" leaks) |
| `backend/api/graph.py` | `get_graph`/`get_graph_focus`/`get_graph_flowchart` take `repo_id`; `export_neo4j_cypher` calls `get_graph` as a plain function, so `team_ids` must be threaded through explicitly, not re-derived |
| `backend/api/search.py` + `backend/services/search.py` | `search_nodes()` is shared by the global search bar **and** Topics' node picker — fixing it here also closes the Topics attach-node leak surface. `CodeEntity`/`DocumentChunk` have no `team_id` directly; filter via a `repo_id IN (visible repo ids subquery)` / `source_id IN (...)` instead |
| `backend/api/link_chat.py` | `get_link_sources` and `send_link_chat_message`'s `DocumentChunk` search are currently **fully unscoped** (searches every repo/source globally) — confirm with the user whether this feature is pilot-exposed before investing here; document as a known gap if not yet user-facing |
| `backend/api/connectors.py` | no change — confirmed fully stateless, no `repo_id`/persisted data |
| `backend/api/chat.py` (rest) | `get_chat_sessions`/`delete_chat_session` already correctly owner-scoped, no change; `get_chat_messages` (by `session_id`) has no owner check at all today — pre-existing chat-ownership gap, separate from this feature, flag but don't fix here to avoid scope creep |

## Admin API — new `backend/api/teams.py` + `backend/api/users.py`

Both routers admin-only via their own `dependencies=[Depends(require_admin)]` (not nested under the global `_authenticated` list).

`teams.py`: `GET/POST /teams`, `PATCH/DELETE /teams/{id}`, `GET/POST /teams/{id}/members`, `DELETE /teams/{id}/members/{user_id}`.
`users.py`: `GET /users` (needed for the admin UI's "add member" picker — doesn't exist yet).

`backend/main.py`: register both new routers; switch `topics.router`'s dependency from `_authenticated` to `[Depends(require_admin)]`.

`backend/api/auth.py`'s `/auth/me` extends to:
```python
{"id", "email", "name", "is_admin": is_admin(user), "teams": [{"id", "name"}, ...]}
```

`backend/api/schemas.py` additions: `TeamCreate`, `TeamUpdate`, `TeamMemberAdd`; `RepoCreate.team_id: int`; `KnowledgeSourceCreate.team_id: Optional[int]` (required when `repo_id` is `None`, derived from the parent repo otherwise).

## Frontend

- `frontend/app/services/api.ts`: add `getTeams/createTeam/updateTeam/deleteTeam/getTeamMembers/addTeamMember/removeTeamMember/getUsers`.
- `frontend/app/page.tsx`: the existing `api.getMe()` call already runs but discards the response body beyond a login boolean — capture `is_admin`/`teams` into new state, prop-drill into `SettingsModal`/`Sidebar` (this codebase's existing convention; no React Context exists anywhere today, don't introduce one for this).
- New `frontend/components/TeamsPanel.tsx` (admin-only), mirroring `TopicsPanel.tsx`'s left-list/right-detail layout: left = team list + create form, right = selected team's members (`GET /teams/{id}/members`, add via a `GET /users` picker, remove button), delete-team button surfacing the backend's 409 ("N repos/sources still attached") as a toast.
- `frontend/components/SettingsModal.tsx`: add a team selector to both the repo-creation wizard and the knowledge-source modal, mirroring the existing `selectedSourceRepoId` Select pattern (lines ~354/663/1760-1792) — auto-select silently if the user has exactly one team, show a dropdown only if they have multiple (or, for admins, list all teams via `GET /teams` instead of their own).
- `frontend/components/Sidebar.tsx`: a "Teams" entry near the existing Settings button, rendered only when `isAdmin`.
- Empty state: a user with zero team memberships sees a dedicated "not yet assigned to a team — contact your administrator" message, distinct from "no repos exist yet."

## Sharp edges to handle explicitly

1. **Admin creating a repo while not being a member of any team** — the create-repo team-selector must source from `GET /teams` (all teams) for admins, not from `/auth/me`'s own `teams` field.
2. **Team deletion** — block with 409 if any `Repository`/`KnowledgeSource` still has that `team_id` ("Team kann nicht gelöscht werden — N Repositories/Wissensquellen sind noch zugeordnet"). Memberships alone cascade-delete on team delete; resources never silently orphan.
3. **New user with zero team memberships** (created after this feature ships) — do **not** auto-add to "Default Team". `get_visible_team_ids` returns `[]` (empty, distinct from `None`/admin) — they see nothing until an admin assigns them. The migration's one-time Default Team backfill is different in kind (preserving existing access for existing users at upgrade time), not a precedent for new users.
4. **`POST /chat`'s global-knowledge-source branch** (see above) — must be filtered, not optional.
5. **`KnowledgeSource.create` when `repo_id` is set** — force `team_id` to the parent repo's team server-side; never trust a client-supplied `team_id` that could attach a source to a repo cross-team.

## Tests

`backend/tests/test_teams.py`, mirroring `test_chat_sessions.py`'s `other_user`/factory-fixture pattern in `conftest.py`:
- Cross-team isolation: list + single-resource 404 for a team-B repo when logged in as a team-A user.
- Create-under-foreign-team → 403.
- Admin bypass sees both teams.
- `POST /chat` with a foreign `repo_id` → 404, no SSE content leak.
- Global-knowledge-source team filtering in chat (sharp edge 4).
- Team deletion blocked while resources attached → 409.
- New user, zero teams → empty list, not Default Team's contents, not an error.

Each backend commit (repositories.py, knowledge_sources.py, chat.py, entity_links.py, knowledge_links.py, graph.py, search.py, teams.py/users.py) keeps the full existing suite green and adds its own focused tests before moving to the next file — same incremental, verify-as-you-go style used earlier this session for the chat-session-ownership fix.

## Staged commits

1. Models + migration (`Team`, `TeamMembership`, `team_id` columns, backfill) — no enforcement yet, existing tests untouched and still green.
2. `core/teams.py` helper + `ADMIN_EMAILS` + a small dedicated unit test for the helper itself.
3. `repositories.py` (full pattern worked out above) + tests.
4. `knowledge_sources.py` + tests.
5. `chat.py` (repo_id/source_id validation + the global-sources fix) + tests.
6. `entity_links.py` + tests.
7. `knowledge_links.py` + tests.
8. `graph.py` + tests.
9. `search.py`/`services/search.py` + tests.
10. `topics.py` → admin-only router switch in `main.py` (no internal change).
11. `link_chat.py` — only after confirming with the user whether it's pilot-exposed.
12. New `teams.py` + `users.py` admin API + `/auth/me` extension + schema additions + `main.py` wiring.
13. Frontend: `api.ts`, `page.tsx` state, `TeamsPanel.tsx`, `SettingsModal.tsx` selectors, `Sidebar.tsx` entry.

## Verification

- After commit 1: `alembic upgrade head` against both a fresh DB and a DB already at `b42f8210a7ea` with real rows (the actual customer upgrade path) — confirm backfill populates Default Team correctly and existing tests still pass unmodified.
- After each backend commit: `docker exec doctus-backend python -m pytest tests/ -v` (rebuild the image first since this host runs without source bind-mounts — `docker compose build backend-api && docker compose up -d backend-api`, established this session).
- After commit 12: manual smoke test via curl/browser — create a second team, add a second test user to it, confirm cross-team 404s on `/repositories/{id}/files` and a clean `/chat` 404 on a foreign `repo_id`.
- After commit 13: `npx tsc --noEmit` in `frontend/`, then manually exercise the Teams admin panel and the repo/knowledge-source creation wizards in the browser as both an admin and a single-team regular user.
