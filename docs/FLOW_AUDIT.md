# FLOW_AUDIT.md — Tweedle cross-portal flow verification

> **Read-only audit.** No source file, template, CSS, or migration was modified; no git
> command was run. The only file created is this report. Verified against the repo on
> **2026-06-18**. Test suite: **167 tests, all passing** (`python manage.py test` → `Ran 167
> tests in 249s … OK`, exit 0).
>
> Source of truth precedence followed: `BACKEND_BUILD_STATE.md` → `TARGET_TICKET_FLOW.md`
> (§3 states, §4 T1–T12, §5 S1–S5, §6 label matrix, §7 notify map) → `PROJECT_HANDOFF.md` →
> `FRONTEND_QA.md`. Where a doc claims "done", it was re-checked against code; claims that
> don't hold are flagged inline.

**Bottom line:** the guarded engine (`tickets/transitions.py`) is an essentially faithful
implementation of TARGET §4/§5/§7 — engine parity is clean. The happy-path lifecycle
(submit → assign → dev → test → UAT → approve → close) flows correctly end-to-end across all
five portals with correct status, visibility, and the required per-state actions. The
divergences are concentrated in **(1) client-facing labels** (the client badge map still
speaks internal language, violating TARGET §6 + design principle #4) and **(2) missing admin
authority controls** (cancel / reopen / restore are neither whitelisted nor surfaced). Plus
the documented-but-still-open gaps: static notifications, read-only chat, no Cancelled tab.

---

## A. ENGINE vs TARGET PARITY

### A.1 Full `TRANSITIONS` registry (`tickets/transitions.py:241-414`)

| Action | from_status | from_sub | to_status | to_sub | roles | required | guard | notify | event |
|--------|-------------|----------|-----------|--------|-------|----------|-------|--------|-------|
| `assign` | `{new}` | — | `in_progress` | `development` | admin | `developer` | — | assignees | assign |
| `reject` | `{new}` | — | `rejected` | None | admin | `reason` | — | requester | reject |
| `cancel` | `{new,in_progress,awaiting_client}` | — | `cancelled` | None | admin+client+subuser | — | `guard_cancel` (requester/admin) | requester | cancel |
| `request_info` | `{in_progress}` | — | `awaiting_client` | None | admin | `message` | — | requester | request_info |
| `resume` | `{awaiting_client}` | — | `in_progress` | RESTORE_PAUSED | admin | — | — | developer | resume |
| `send_to_uat` | `{in_progress}` | `{ready_for_uat}` | `uat` | None | admin | — | — | requester | send_to_uat |
| `approve` | `{uat}` | — | `resolved` | None | client+admin | — | `guard_approve` (requester/admin) | admins+assignees | approve |
| `request_changes` | `{uat}` | — | `in_progress` | `development` | client+subuser+admin | `feedback` | `guard_request_changes` (requester/admin) | admins+developer | request_changes |
| `close` | `{resolved}` | — | `closed` | None | admin | — | — | requester | close |
| `reopen` | `{resolved,closed}` | — | `in_progress` | `development` | client+admin | `reason` | `guard_reopen` (window) | admins+developer | reopen |
| `restore` | `{rejected}` | — | `new` | None | admin | — | — | None | restore |
| `confirm` | `{uat}` | — | (unchanged) | UNCHANGED | subuser | — | `guard_confirm` (org subuser) | primary client+admins | confirm |
| `reassign` | `{in_progress,awaiting_client}` | — | (unchanged) | UNCHANGED | admin | — | `guard_reassign` (≥1 assignee) | new assignees | **reassigned** |
| `submit_for_testing` | `{in_progress}` | `{development}` | — | `testing` | developer | — | `guard_tester_assigned` | tester | submit_for_testing |
| `pass` | `{in_progress}` | `{testing}` | — | `ready_for_uat` | tester | — | — | admins | pass |
| `fail` | `{in_progress}` | `{testing}` | — | `returned` | tester | `failure_notes` | — | developer | fail |
| `resubmit_for_testing` | `{in_progress}` | `{returned}` | — | `testing` | developer | — | `guard_tester_assigned` | tester | resubmit_for_testing |
| `mark_ready` | `{in_progress}` | `{development}` | — | `ready_for_uat` | developer | — | `guard_no_tester_assigned` | admins | mark_ready |

### A.2 Mapping to TARGET rows + divergence flags

| TARGET row | Registry entry | Verdict |
|------------|----------------|---------|
| T1 assign | `assign` | ✅ exact |
| T2 reject | `reject` | ✅ exact |
| T3 cancel | `cancel` | ✅ — roles admin+requester, reason optional, from the 3 pre-completion states all match |
| T4 request_info | `request_info` | ✅ exact (stashes `paused_sub_status` via `effects_request_info`) |
| T5 resume | `resume` | ✅ exact (RESTORE_PAUSED → `paused_sub_status or development`) |
| T6 send_to_uat | `send_to_uat` | ✅ exact (clears `subuser_confirmed`) |
| T7 approve | `approve` | ✅ exact (records `accepted_at`/`accepted_by`; notify admins+assignees) |
| T8 request_changes / recall | `request_changes` | ✅ exact (clears `subuser_confirmed`; admin trigger is the "Recall" UI) |
| T9 close | `close` | ⚠️ **MINOR**: TARGET roles = `admin, system`; code = `{admin}` only. "system" is the future `close_stale_resolved` command (TARGET §9), not yet built — acceptable for now. |
| T10/T11 reopen | `reopen` (merged) | ✅ exact — window enforced in `guard_reopen` (admin anytime; client ≤ `REOPEN_WINDOW_DAYS=14`); re-routes to original developer (stays `assigned_developer`) |
| T12 restore | `restore` | ✅ exact (notify None — consistent with TARGET §7 having no restore row) |
| sub-user confirm | `confirm` | ✅ exact (no status change, sets flag, notifies primary client + admins) |
| §5 reassignment | `reassign` | ✅ exact (no status change, `reassigned` event, notifies only the newly-named assignees) |
| S1 submit_for_testing | `submit_for_testing` | ✅ exact (guarded: tester required) |
| S2 pass | `pass` | ✅ exact |
| S3 fail | `fail` | ✅ exact (failure_notes required) |
| S4 resubmit_for_testing | `resubmit_for_testing` | ✅ exact (guarded: tester required) |
| S5 mark_ready | `mark_ready` | ✅ exact (guarded: **no** tester) |

**MISSING transitions:** none. **EXTRA transitions:** none. Every TARGET row has exactly one
registry entry, and every registry entry maps to a TARGET row.

### A.3 Notify-map parity (TARGET §7)
All 14 notify rows match the resolvers in `transitions.py:184-195`. The dispatch loop
(`transitions.py:516-528`) de-dups recipients and **skips the actor**, so a requester who
cancels/approves their own ticket isn't self-notified — correct behaviour, not a defect.

### A.4 Tester-gate guard — CONFIRMED CORRECT
- Route to `ready_for_uat` **with** a tester: only `submit_for_testing`(S1) → `pass`(S2).
  `guard_tester_assigned` (`transitions.py:98-102`) blocks S1/S4 if no tester.
- Route **without** a tester: `mark_ready`(S5), gated by `guard_no_tester_assigned`
  (`transitions.py:105-110`).
- "Adding a tester later disables `mark_ready`": enforced — `mark_ready` re-checks
  `assigned_tester_id` at call time. Covered by `tickets/tests.py:242
  test_adding_tester_later_disables_mark_ready`, `:227 test_mark_ready_blocked_when_tester_assigned`,
  `:235 test_submit_for_testing_requires_tester`. ✅

---

## B. PER-PORTAL LABELS vs TARGET §6

Each portal turns `(status, sub_status)` into a label via a pure-data dict in its own
templatetag library:
- **Admin** — `admin_portal/templatetags/admin_extras.py:17` `ADMIN_TICKET_BADGES` → `{% ticket_badge %}`
- **Client** — `client_portal/templatetags/client_extras.py:16` `CLIENT_TICKET_BADGES` → `{% client_ticket_badge %}`
- **Developer** — `developer_portal/templatetags/dev_extras.py:16` `DEV_TICKET_BADGES` → `{% dev_ticket_badge %}`
- **Tester** — `tester_portal/templatetags/tester_extras.py:13` `TESTER_TICKET_BADGES` → `{% tester_ticket_badge %}`
- **Sub-user** — `subuser_portal/templatetags/subuser_extras.py:14` `SUBUSER_TICKET_BADGES` → `{% subuser_ticket_badge %}` (plus a hardcoded `subuser_confirmed` branch at `:32`)

> Note: the CSS modifier token `"forwarded"` persists in every dict (e.g. `client_extras.py:22`)
> and as the admin tab key / dev context var (`admin_portal/views.py:23`,
> `developer_portal/views.py:32`). These are **cosmetic class/identifier names only** — the
> status *value* is `awaiting_client` everywhere. The `forwarded` **status string is gone**. ✅

### B.1 Admin (`{% ticket_badge %}`)
| §6 admin label | Code renders | Verdict |
|----------------|--------------|---------|
| New (Inbox) | "New" | ✅ (Inbox is the tab) |
| Development | "Development" | ✅ |
| Testing | "Testing" | ✅ |
| Returned from QA | **"Returned"** (title="Returned from Testing") | ⚠️ MINOR mismatch |
| Ready for UAT | "Ready for UAT" | ✅ |
| Awaiting Client | "Awaiting Client" | ✅ |
| UAT Approval | "UAT Approval" | ✅ |
| Resolved / Closed / Rejected / Cancelled | identical | ✅ |

### B.2 Client (`{% client_ticket_badge %}`) — **substantially divergent**
Used on the client **dashboard list** (`client_portal/dashboard.html:225`) **and** the detail
"Status" rows (`ticket-detail.html:33,379`), so the divergence is visible to clients everywhere.

| §6 client label | Code renders | Verdict |
|-----------------|--------------|---------|
| New — Received | **"New"** | ❌ mismatch |
| In Progress (all sub-stages) | "In Progress" | ✅ |
| Your Input Needed | "Your Input Needed" | ✅ |
| **Ready for Your Review** | **"UAT Approval"** | ❌ **MAJOR** — internal language leaks to client |
| Ready for Your Review (sub-user confirmed) | (no variant — still "UAT Approval") | ❌ missing confirmed-state label |
| **Awaiting Closure** | **"Resolved"** | ❌ **MAJOR** |
| **Completed** | **"Closed"** | ❌ mismatch |
| **Not Accepted** | **"Rejected"** | ❌ mismatch |
| Cancelled | "Cancelled" | ✅ |

The client **detail action cards** use the correct copy ("Ready for Your Review", "Work
Complete", "Ticket Closed", "Ticket Not Accepted") — but the **status badge** beside them
contradicts that copy with internal terms. This is the single biggest label defect and it
violates TARGET design principle #4 ("clients see outcome language").

### B.3 Developer (`{% dev_ticket_badge %}`)
| §6 developer label | Code renders | Verdict |
|--------------------|--------------|---------|
| Development / In Testing / Returned from QA / Ready for UAT | match | ✅ |
| **Paused — Awaiting Client** | **"Awaiting Client"** | ⚠️ MINOR (detail banner does say "Paused — Awaiting Client", only the badge is short) |
| In Client UAT / Resolved / Closed | match | ✅ |
- **"Uat" capitalization artifact: GONE** ✅ — the label comes from the dict, not `capitalize()`.
- `new`/`rejected`/`cancelled` rows exist in the dict but are N/A for developers (queryset
  never surfaces them) — harmless dead rows.

### B.4 Tester (`{% tester_ticket_badge %}`)
| §6 tester label | Code renders | Verdict |
|-----------------|--------------|---------|
| Testing | "Testing" | ✅ |
| Failed (read-only) | "Failed" | ✅ |
| Passed (read-only) | "Passed" | ✅ |
Only those three states are reachable (queryset restricted, `tester_portal/views.py:15`). ✅

### B.5 Sub-user (`{% subuser_ticket_badge %}`) — **fully matches §6**
| §6 sub-user label | Code renders | Verdict |
|-------------------|--------------|---------|
| New — Received | "New — Received" | ✅ |
| In Progress (all) | "In Progress" | ✅ |
| Your Input Needed | "Your Input Needed" | ✅ |
| Please Verify | "Please Verify" | ✅ |
| **Confirmed — Awaiting Approval** | "Confirmed — Awaiting Approval" (special-cased at `:32`) | ✅ |
| Awaiting Closure / Completed / Not Accepted / Cancelled | all match | ✅ |

**Specific checks requested:**
- *forwarded fully gone (awaiting_client everywhere)* — ✅ confirmed (status string never `forwarded`).
- *sub-user "Your Input Needed" on awaiting_client* — ✅ (badge `:20` + detail card `ticket-detail.html:159`).
- *developer no "Uat" capitalization artifact* — ✅.
- *sub-user real "Confirmed — Awaiting Approval"* — ✅ (`:32` + detail `ticket-detail.html:78`).

**Net:** sub-user (built last, Phase 4.7) is the correct reference implementation of §6;
**client (built first, Phase 4.4) was never updated to the §6 client column** and is the
outlier.

---

## C. VISIBILITY / QUERYSET SCOPING

| Portal | View | Queryset (file:line) | Scope |
|--------|------|----------------------|-------|
| Admin dashboard | `AdminDashboardView` | `admin_portal/views.py:51-57` `Ticket.objects…filter(status=status)` per tab over **all** tickets | all ✅ |
| Admin detail/timeline/chat | `admin_ticket_detail` etc. | `admin_portal/views.py:144,161,171` `get_object_or_404(Ticket, pk=pk)` (no owner filter) | all ✅ |
| Client dashboard | `ClientDashboardView` | `client_portal/views.py:33` `filter(client=self.request.user.client)` | own org ✅ |
| Client detail/transition | `client_ticket_detail` / `client_ticket_transition` | `client_portal/views.py:57,118` `pk=pk, client=request.user.client` | own org ✅ |
| Sub-user dashboard | `SubuserDashboardView` | `subuser_portal/views.py:29` `filter(requester=self.request.user)` | own submitted ✅ |
| Sub-user detail | `subuser_ticket_detail` | `subuser_portal/views.py:80` `pk=pk, requester=request.user` | own submitted ✅ |
| Sub-user transition | `subuser_ticket_transition` | `subuser_portal/views.py:99` `pk=pk, client=request.user.client` | **org-level** ⚠️ (see note) |
| Developer dashboard | `DeveloperDashboardView` | `developer_portal/views.py:24` `filter(assigned_developer=self.request.user)` | assigned ✅ |
| Developer detail/transition | `dev_ticket_detail` / `dev_ticket_transition` | `developer_portal/views.py:44,64` `pk=pk, assigned_developer=request.user` | assigned ✅ |
| Tester dashboard | `TesterDashboardView` | `tester_portal/views.py:24-32` `filter(assigned_tester=self.request.user, status=in_progress, sub_status in {testing,returned,ready_for_uat})` | assigned + relevant ✅ |
| Tester detail/transition | `tester_ticket_detail` / `tester_ticket_transition` | `tester_portal/views.py:43,61` `assigned_tester=request.user` | assigned ✅ |

**Confirmations:**
- admin sees all ✅ · client sees own org (client FK) ✅ · sub-user sees only own submitted
  (requester) ✅ · developer/tester see only assigned ✅.
- **New client ticket appears in (1) admin Inbox and (2) that client's dashboard** —
  CONFIRMED. `client_submit_ticket` (`client_portal/views.py:92-100`) creates `status=NEW,
  client=request.user.client`; admin inbox tab = `filter(status=new)` (all) so it appears;
  client dashboard = `filter(client=…)` so it appears. (Engine-driven equivalent covered by
  `admin_portal/tests.py:58`, `client_portal/tests.py:52`.)
- **Sub-user-submitted ticket appears to the primary client of the same org** — CONFIRMED.
  `subuser_submit_ticket` (`subuser_portal/views.py:52-60`) sets `client=request.user.client`;
  the client dashboard filters by that same `client`, so it surfaces. (No explicit test asserts
  this cross-portal hop — see G blind spots.)

⚠️ **Note (MINOR, not a hole):** the sub-user *transition* endpoint is scoped to the **org**
(`client=request.user.client`) while the sub-user dashboard/detail are scoped to the
**requester**. So a sub-user could POST `confirm`/`request_changes` against a co-worker's or the
primary client's ticket pk they cannot otherwise see. The engine still guards it correctly:
`guard_confirm` (`transitions.py:76-81`) intentionally allows **any** sub-user of the client org
to confirm (matches TARGET §4 "a sub-user under the ticket's client may confirm"), and
`guard_request_changes` requires `actor == requester` so a co-worker's `request_changes` is
rejected. No privilege escalation — but the view scope is inconsistent with the read views.

---

## D. ACTION AVAILABILITY PER STATE PER PORTAL

ALLOWED_ACTIONS whitelists (the engine re-checks each anyway):
- Admin — `admin_portal/views.py:32-35` → `{assign, reject, resume, send_to_uat, request_info, reassign, request_changes, close}`
- Client — `client_portal/views.py:23` → `{approve, request_changes, cancel, reopen}`
- Developer — `developer_portal/views.py:14` → `{submit_for_testing, resubmit_for_testing, mark_ready}`
- Tester — `tester_portal/views.py:13` → `{pass, fail}`
- Sub-user — `subuser_portal/views.py:19` → `{confirm, request_changes}`

### D.1 Admin — buttons rendered per state
| State | §6 admin verbs | UI control (file:line) | Verdict |
|-------|----------------|------------------------|---------|
| new | Assign / Reject | `#newTicketForm` → `confirmAssignment()`/`confirmRejection()` post `assign`/`reject` (`dashboard.html:1089-1198`) | ✅ |
| in_progress·ready_for_uat | Send to Client UAT | inline form on the row, only when `sub_status==ready_for_uat` (`dashboard.html:483-493`) | ✅ |
| in_progress (other) | (dev acts) | detail modal offers `request_info` + `reassign` (`_ticket_detail.html:114-148`) | ✅ allowed by engine |
| awaiting_client | (resume) | list `resume` (`dashboard.html:564-566`) + modal `resume`/`reassign` (`_ticket_detail.html:104-148`) | ✅ |
| uat | Recall | modal `request_changes` "Recall to In Progress" (`_ticket_detail.html:150-160`) | ✅ |
| resolved | **Close / Reopen** | modal `close` only (`_ticket_detail.html:162-170`) — **no Reopen** | ❌ Reopen missing |
| closed | **Reopen** | none (banner: "no further actions", `_ticket_detail.html:26-30`) | ❌ missing |
| rejected | **Restore** | none (rejected modal: "no further actions available", `dashboard.html:956`) | ❌ missing |
| any pre-completion | **(Cancel — T3)** | none anywhere | ❌ missing |

`reopen`, `restore`, `cancel` are **not in the admin whitelist** (`views.py:32`) — even a
hand-crafted POST returns "Unsupported action". So the admin portal cannot exercise three
documented admin authorities (TARGET §2 lists "reopen, cancel … restore"; §6 lists Reopen on
resolved/closed and Restore on rejected). **MAJOR functional gap.**

### D.2 Client
| State | §6 verbs | UI (file:line) | Verdict |
|-------|----------|----------------|---------|
| uat | Approve / Request Changes | `ticket-detail.html:140-163` (+ approve confirm overlay `:481-505`) | ✅ |
| resolved | Reopen | `ticket-detail.html:179-192` | ✅ |
| closed (≤14d) | Reopen ≤14d | `ticket-detail.html:197-224` gated by `reopen_available` (`views.py:61-65`) | ✅ |
| awaiting_client | **Respond** | button is **disabled** ("Chat reply coming soon", `ticket-detail.html:116-119`) | ⚠️ no functional respond (chat unbuilt) |
| new | (Cancel allowed by T3) | cancel button present (`ticket-detail.html:76-84`) | ✅ extra-but-valid |
| in_progress / awaiting_client | (Cancel allowed by T3) | no cancel button | ⚠️ MINOR — T3 permits, §6 doesn't require |

### D.3 Developer
`development` → **Submit for Testing OR Mark Ready depending on tester** — CONFIRMED. Context
booleans `show_submit_for_testing = is_development and tester_assigned`, `show_mark_ready =
is_development and not tester_assigned` (`developer_portal/views.py:54-55`), rendered mutually
exclusively (`ticket-detail.html:145-179`). `returned` → Resubmit (`show_resubmit`, `:157`). All
other states render read-only banners. ✅

### D.4 Tester
`testing` → Pass / Fail with required failure notes (`ticket-detail.html:96-141`); `returned`
and `ready_for_uat` render read-only banners (`:143-167`). ✅

### D.5 Sub-user
`uat` (unconfirmed) → Confirm / Still Broken(`request_changes`) (`ticket-detail.html:99-148`);
`uat` (confirmed) → read-only "Confirmed — Awaiting Approval" (`:72-85`). ✅ No portal renders an
action the engine would reject in the happy path; the gaps are *missing* controls (admin
cancel/reopen/restore, client respond), not illegal ones.

---

## E. TICKET DETAIL STRUCTURE COMPLETENESS

| Field | Admin `_ticket_detail.html` | Client `ticket-detail.html` | Developer | Tester | Sub-user |
|-------|------|--------|-----------|--------|----------|
| reference | ✅ :6 | ✅ :23 | ✅ :21 | ✅ :22 | ✅ :22 |
| subject | ✅ :8 | ✅ :22 | ✅ :20 | ✅ :21 | ✅ :21 |
| description | ✅ :96 | ✅ :305 | ✅ :204 | ✅ :191 | ✅ :248 |
| category | ✅ :60 | ✅ :391 | ✅ :347 | ✅ :333 | ✅ :349 |
| priority | ✅ :55 | ✅ :385 | ✅ :336 | ✅ :323 | ✅ :342 |
| requester | ✅ (Ticket Maker :46) | — (self) | — | — | — (self) |
| client | ✅ code :64 | — (self) | ✅ name :343 | ✅ name :330 | — |
| assigned_developer | ✅ :68 | ✅ :407 | ✅ (you) :356 | ✅ :343 | ✅ (cond.) :363 |
| assigned_tester | ✅ :72 | ✅ (cond.) :423 | ✅ (cond.) :364 | ✅ (you) :349 | ❌ hidden |
| created date | ✅ :50 | ✅ :45 | ✅ :56 | ✅ :57 | ✅ :46 |
| accepted date | ✅ (cond.) :83 | ❌ | ❌ | ❌ | ❌ |
| closed date | ✅ (cond.) :89 | ✅ (cond.) :431 | ❌ | ❌ | ❌ |
| TicketEvent timeline | ➖ separate drawer (`admin_ticket_timeline`) | ✅ inline :458 | ✅ inline :378 | ✅ inline (+notes) :363 | ✅ inline :378 |
| chat (TicketMessages) | ➖ separate drawer (`admin_ticket_chat`) | ✅ inline (RO) :320 | ✅ inline (RO) :253 | ✅ inline (RO) :240 | ✅ inline (RO) :270 |
| attachments | ❌ | ❌ | ✅ :218 | ✅ :205 | ❌ |

**Flags (all MINOR / by-design):**
- Admin detail partial deliberately excludes timeline+chat (they're separate fetched drawers;
  asserted by `admin_portal/tests.py:362`). Not a defect.
- `accepted_at`/`closed_at` shown only in admin; client shows `closed` only; dev/tester/sub-user
  show neither. Acceptance/closure dates are largely admin-facing — acceptable, low value.
- Sub-user intentionally hides the tester; **but reveals the developer's real name**
  (`ticket-detail.html:363`) and the admin's name in chat (`:280`). The original frontend intent
  (PROJECT_HANDOFF) was to mask internal staff as "Support Team" for sub-users; TARGET §6 does
  not mandate masking, so this is a MINOR product-intent divergence, not a flow defect.

---

## F. KNOWN-GAP CONFIRMATION (present/absent only)

| Gap | Status | Evidence |
|-----|--------|----------|
| Notification bell count + notifications pages | **STATIC / unbound** | `base.html:212` hardcoded `<span id="notifCount">8</span>` + dummy `.tw-notif-item` list (`:227-`); all five `*_base.html` only clear `.unread` in JS (`client_base.html:204`, `developer_base.html:206`, `subuser_base.html:226`, `tester_base.html:230`). No view passes notification context. Matches BACKEND_BUILD_STATE §6.3 "Notification feed binding" still open. |
| Chat posting (create `TicketMessage`) | **READ-ONLY everywhere** | admin compose disabled (`dashboard.html:1258-1267`); client textarea `disabled` + "coming soon" (`ticket-detail.html:341-353`); dev/tester send buttons call toast stubs (`developer ticket-detail.html:489`, `tester :487`); sub-user posts a toast (`ticket-detail.html:303`). |
| Cancelled tickets — admin tab/filter | **ABSENT** | dashboard has 7 tabs (`TAB_STATUS`, `admin_portal/views.py:20-28`) with no `cancelled`; comment at `views.py:42-43` confirms "cancelled tickets have no tab". Visible only via Django admin. |
| reopen / restore / cancel UI controls | **PARTIAL** | `cancel`: client `new` only (`ticket-detail.html:76`). `reopen`: client `resolved`/`closed≤14d` only (`:179,:209`). `restore`: **nowhere**. Admin has **none** of the three. |
| Remaining admin pages (clients, team, reports, settings, notifications) | **STATIC markup** | only `AdminDashboardView` + detail/timeline/chat views exist in `admin_portal/views.py`; no view/URL for those pages binds live data (BACKEND_BUILD_STATE §6.1 lists them as Phase 4.0b TODO). |

---

## G. TEST COVERAGE MAP

`python manage.py test` → **Ran 167 tests … OK** (exit 0; ~249s on SQLite test DB). Distribution
(`grep def test_`): `tickets` 50, `admin_portal` 39, `subuser_portal` 21, `developer_portal` 17,
`tester_portal` 16, `client_portal` 13, `core` 11.

**What the tests actually cover:**
- **Engine transitions** — strong. `tickets/tests.py`: legal happy paths with/without tester
  (`:97,:121`), fail→resubmit (`:130`), request_info→resume restore (`:139`), recall (`:152`),
  reject→restore (`:162`), cancel from all 3 states (`:171-192`), reopen window matrix
  (`:266-299`), all guards (`:227-242`), audit "exactly one event" (`:356`), notify targets
  (`:373,:380,:388`), DB CheckConstraint (`:396,:403`).
- **View-level ownership** — strong. `tickets/tests.py:409-544` (OwnershipTests) + each portal's
  404/403 scoping (`client:63,:184`, `developer:99,:156`, `tester:99,:150`, `subuser:116`).
- **View action wiring** — good for admin/dev/tester/sub-user (assign/reject/resume/send_to_uat
  `admin:188-241`; recall/close `admin:308-324`; dev `submit/mark_ready` `:123-133`; tester
  pass/fail `:113-137`; sub-user confirm/request_changes `:191-233`). Client transitions
  `:117-184`.
- **Label rendering** — **WEAK.** Only `admin_portal/tests.py:121
  test_stage_badge_reflects_sub_status` asserts a badge label. **No test** for the
  client/developer/tester/sub-user badge maps.
- **Action-button visibility** — partial: admin detail button-visibility per state is well
  covered (`admin:386-418`); dev/tester have form-markup tests (`developer:166-189`,
  `tester:171-181`); client and sub-user have **no per-state button-visibility tests**.

**Named blind spots:**
1. **Client label divergence (B.2)** — no test asserts client badge copy, so the "UAT
   Approval / Resolved / Closed / Rejected" leak (the top defect) is **completely uncaught**.
2. **Cross-portal visibility (C)** — no test creates a ticket in one portal and asserts it
   surfaces in another (client-submit → admin inbox; sub-user-submit → primary-client
   dashboard). Each portal is tested in isolation.
3. **Admin cancel/reopen/restore (D.1)** — no test, because the controls/whitelist entries
   don't exist; nothing flags their absence.
4. **Notifications & chat (F)** — untested (unbuilt).
5. **Sub-user transition org-vs-requester scope (C note)** — no test pins the intended scope.

---

## H. TOP DEFECTS (ranked punch-list)

| # | Sev | Defect | Evidence | TARGET rule violated |
|---|-----|--------|----------|----------------------|
| 1 | **MAJOR** | Client status badge speaks **internal language** to the client: `uat`→"UAT Approval", `resolved`→"Resolved", `closed`→"Closed", `rejected`→"Rejected", `new`→"New"; and there is no sub-user-confirmed variant. | `client_portal/templatetags/client_extras.py:16-28`; rendered on dashboard `dashboard.html:225` and detail `ticket-detail.html:33,379` | §6 client column = "Ready for Your Review / Awaiting Closure / Completed / Not Accepted / New — Received"; principle #4 (clients see outcome language) |
| 2 | **MAJOR** | Admin portal **cannot cancel, reopen, or restore** — actions absent from the whitelist and from all UI; rejected/closed open read-only. | `admin_portal/views.py:32-35` (whitelist omits all three); `_ticket_detail.html:26-30` (closed RO), `dashboard.html:956` (rejected RO); no reopen/cancel/restore form anywhere | §2 admin authority "reopen, cancel … restore"; §6 admin resolved=*(Close/Reopen)*, closed=*(Reopen)*, rejected=*(Restore)*; T3/T10–T12 |
| 3 | MINOR | Client `awaiting_client` "Respond" button is **disabled** — no functional way for the client to respond (chat unbuilt). | `client_portal/ticket-detail.html:116-119` | §6 client awaiting_client *(Respond)* |
| 4 | MINOR | Admin badge "Returned" vs §6 "Returned from QA"; Developer badge "Awaiting Client" vs §6 "Paused — Awaiting Client". | `admin_extras.py:21`; `dev_extras.py:22` | §6 admin/developer columns |
| 5 | MINOR | Sub-user transition endpoint scoped to **org** while its read views are scoped to **requester** — inconsistent (engine guards keep it safe; confirm-by-coworker is intended). | `subuser_portal/views.py:99` vs `:29,:80` | — (consistency / least-surprise) |
| 6 | MINOR | Client `cancel` only offered on `new`; T3 also permits requester cancel on `in_progress`/`awaiting_client`. | `client_portal/ticket-detail.html:76` (no cancel on other states) | T3 (permitted, not §6-required) |
| 7 | MINOR (known) | Notifications static, chat read-only, no Cancelled admin tab — documented open gaps, confirmed still open. | see §F | BACKEND_BUILD_STATE §6.1/§6.3 roadmap |
| 8 | MINOR | `close` engine role is `{admin}` only; TARGET T9 = `admin, system` (auto-close command not yet built). | `transitions.py:321-329` | T9 (deferred §9 enhancement) |

**Test gaps to close alongside fixes:** add label-render tests for client/dev/tester/sub-user
badges (would have caught #1); add a cross-portal visibility test (client-submit → admin inbox;
sub-user-submit → primary client); add admin cancel/reopen/restore view tests once #2 is built.

---

*End of audit. No code was changed. Awaiting direction before any fix.*
