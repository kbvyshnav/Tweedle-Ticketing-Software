# BROWSER_FIX_REVIEW.md — read-only investigation of browser-found issues

> No code changed, no git run. File:line evidence + proposed fixes for four issues
> surfaced in a manual browser walkthrough. Baseline: `python manage.py test` → **230
> green** (re-confirmed this run). Reference: TARGET §6 (labels), §7 ("the audit trail …
> is the timeline every portal renders").

---

## ISSUE 1 — Inbox/new-ticket detail shows hardcoded/shared data  → **BUG**

**What an Inbox row opens.** Inbox rows are `data-ticket-type="new"`
(`dashboard.html:380`). The row-click handler routes `new` → **`openNewTicketModal(...)`**
(`dashboard.html:1872-1874`), i.e. the **`#newTicketModal` assignment modal** — *not* the
server-rendered detail partial that every other tab uses.

**Why only subject/status are real.** `openNewTicketModal(ticketId, subject, status)`
(`dashboard.html:2016-2018`) sets only three nodes: `#newModalTicketId`,
`#newModalSubject`, and the status pill. Everything else in the modal body is **static
markup hardcoded inside a `{% verbatim %}` block** and is never updated per-ticket:
- `dashboard.html:1109-1136` — info grid literals: **"Rahul R Nair"**, **"10-12-2025"**,
  **High**, **Integration**, **BGEX**, **Development**.
- `dashboard.html:1138-1143` — description literal ("Federal bank API is returning 500
  errors…").
- `dashboard.html:1145-1166` — a fake attachment **`wallet_specs.pdf`**.
The only Django-bound part is the assignment form (`#newTicketForm`,
`dashboard.html:1170-1192`) whose developer/tester `<option>`s come from
`{{ developers }}`/`{{ testers }}`. So every Inbox ticket opens the *same* placeholder
detail; subject/ID/status are the only live fields.

By contrast the real detail partial already binds everything from the ticket:
`_ticket_detail.html:43-92` (Ticket Maker, Issue Date, Priority, Category, Client,
Developer, Tester, dates) + description `:94-97`.

### Fix options
- **(a) Bind the existing modal to the clicked ticket.** Either add more `data-*`
  attributes to the inbox `<tr>` (description/priority/category/requester — currently
  absent at `dashboard.html:380`) and populate the modal nodes in `openNewTicketModal`, or
  fetch the detail fields. *Trade-off:* keeps two detail surfaces (modal vs partial) and
  re-implements field binding in JS; perpetuates the drift risk; but minimal disruption to
  the assign/workload-stats UI which is modal-specific.
- **(b) Route `new` through the server-rendered detail partial (recommended).** Change the
  inbox row click to `openTicketDetails(pk)` (the same path the other tabs use), and add an
  **Assign/Reject** control block to `_ticket_detail.html` gated on `status == 'new'`
  (porting the developer/tester selects). *Trade-off:* one source of truth — real data +
  real **timeline** (this also fixes Issue 4 for new tickets) + real attachments — but it
  requires moving the assignment form (and its workload-stat JS `showDeveloperInfo`/
  `showTesterInfo`) into the injected partial, which is more work than (a).

**Recommendation:** (b) — it eliminates the static-data class of bug entirely and unifies
the new-ticket experience with every other tab (and dovetails with Issue 4).

---

## ISSUE 2 — "Send to Client UAT" on the row but not in the detail modal  → **BUG (gap)**

- **Row control exists:** `dashboard.html:483-493` renders an inline `send_to_uat` form on
  In-Progress rows, gated by `{% if ticket.sub_status == 'ready_for_uat' %}`, confirmed via
  `confirmInlineAction(...)` (the custom confirm box).
- **Modal has no such control.** The detail partial's action gate is
  `_ticket_detail.html:100` (`in_progress / awaiting_client / uat / resolved / closed /
  rejected`). For an `in_progress` ticket it renders **request_info** (`:114-124`),
  **reassign** (`:126-148`), and **cancel** (`:150-…`) — but **no `send_to_uat`** for the
  `ready_for_uat` sub-state. So opening a ready-for-UAT ticket's modal offers no way to
  promote it.
- **Whitelist is fine:** `"send_to_uat"` is already in admin `ALLOWED_ACTIONS`
  (`admin_portal/views.py:33`).

### Fix
Add a control block to `_ticket_detail.html` inside the Actions section, gated by
`{% if ticket.status == 'in_progress' and ticket.sub_status == 'ready_for_uat' %}`, posting
`action=send_to_uat` to `ticket_transition` — matching the existing modal-action form
pattern (and, per Issue 3, routed through the custom confirm box). No view change needed.

---

## ISSUE 3 — Inconsistent confirmation dialogs across admin actions  → **ENHANCEMENT (+ minor safety bug: Close fires immediately)**

**The custom confirm component:** `#confirmModal` (`dashboard.html:1213-1227`) driven by
`openConfirmModal(config)` / `closeConfirmModal()` / `executeConfirmAction()`
(`dashboard.html:2103-2138`). `config` accepts `{type, title, message, details,
confirmText, onConfirm}`; `onConfirm` fires on confirm. The reusable wrapper
**`confirmInlineAction(btn, title, message)`** (`dashboard.html:1841-1852`) grabs
`btn.closest('form')` and submits it from `onConfirm` — this is the canonical "route a form
through the confirm box" helper.

### Inventory — how each admin action confirms today

| Action | Where | Confirm mechanism |
|---|---|---|
| **assign** | newTicketModal `confirmAssignment()` | **Custom box** (`dashboard.html:2101`) |
| **reject** | newTicketModal `confirmRejection()` | **Custom box** (`dashboard.html:2115`, with `details`) |
| **resume** (list, Awaiting-Client row) | `confirmInlineAction` | **Custom box** (`dashboard.html:564-568`) |
| **send_to_uat** (list, In-Progress row) | `confirmInlineAction` | **Custom box** (`dashboard.html:487-489`) |
| **resume** (modal) | `_ticket_detail.html:104-111` | **None** — plain submit |
| **request_info** (modal) | `_ticket_detail.html:114-124` | **None** — plain submit (textarea `required`) |
| **reassign** (modal) | `_ticket_detail.html:126-148` | **None** — plain submit |
| **request_changes / Recall** (modal) | `_ticket_detail.html:150-160` | **None** — plain submit (textarea `required`) |
| **close** (modal) | `_ticket_detail.html` resolved block | **None — fires immediately** ⚠️ |
| **reopen** (modal) | `_ticket_detail.html` resolved/closed blocks | **None** — plain submit (textarea `required`) |
| **restore** (modal) | `_ticket_detail.html` rejected block | **None** — plain submit |
| **cancel** (modal) | `_ticket_detail.html:162` | **Native `confirm()`** (inconsistent) |

So three different behaviors coexist: custom box (list actions + assign/reject), native
`confirm()` (cancel), and nothing (every other modal action, including a destructive
immediate **Close**).

### Proposed single pattern
Route **every** action form through the custom box via the existing `confirmInlineAction`
shape: each modal form gets `onsubmit="return confirmAction(event, {...})"` (a tiny
generalization of `confirmInlineAction`) that (1) `preventDefault`, (2) validates any
required input on the form (since a JS-intercepted submit bypasses the `required`
attribute), (3) calls `openConfirmModal({title, message, type, details, onConfirm:
()=>form.submit()})`.

**Input-bearing actions** (request_info `message`, request_changes/reopen `reason`/
`feedback`) are accommodated by the box's existing **`details`** slot — echo the entered
text into the confirm box (exactly as `confirmRejection` already passes the rejection reason
into `details`). For optional input (cancel's reason) the same flow applies without the
required-field check. This removes the native `confirm()` (cancel) and gives Close/reopen/
restore/resume/request_info/reassign/request_changes a real confirmation.

### Other portals — destructive actions lacking the custom confirm
- **Client** (`client_portal/ticket-detail.html`): `approve` → **custom** overlay
  (`openApproveConfirm`, `:140/:519`); **but** `cancel` (new) → **native `confirm()`**
  (`:80`); `request_changes` → `showChangesForm` reveals a textarea then **plain submit, no
  confirm** (`:144/:529`); `reopen` (resolved/closed) → **plain submit, no confirm**.
- **Developer**: `submit_for_testing`/`resubmit_for_testing`/`mark_ready` → **custom**
  `devConfirmOverlay`. ✓
- **Tester**: `pass`/`fail` → **custom** `testerConfirmOverlay`. ✓
- **Sub-user**: `confirm`/`request_changes` ("Still Broken") → **custom**
  `subuserConfirmOverlay`. ✓

So dev/tester/subuser are already consistent; the **client** portal has the gaps (native
cancel; no confirm on reopen/request_changes). Worth standardizing client alongside admin if
we choose to.

---

## ISSUE 4 — Timeline is incomplete  → **BUG (4a + 4b are one root cause)**

### 4a — submission writes no event
Both submit views create the row directly with **no `TicketEvent`**:
`client_portal/views.py:92` and `subuser_portal/views.py:52` call
`Ticket.objects.create(...)` (submission is not a `transition()`, so the engine's
event-writing path never runs). `seed_demo` likewise creates rows directly. ⇒ a brand-new
ticket has **zero** `TicketEvent`s; the first event is `assign`. The admin timeline drawer
shows the `{% empty %}` fallback **"No timeline events yet."** (`_ticket_timeline.html:20-21`),
and dev/tester/subuser show nothing until the ticket is assigned.

### 4b — per-portal timeline construction
Every portal renders the **same full `ticket.events`** history — there is **no per-portal
event filtering**:

| Portal | Events queryset | Render | Synthetic "submitted" line? |
|---|---|---|---|
| **Client** | `client_portal/views.py:76` (`ticket.events…order_by`) | `ticket-detail.html:458-468` | **YES** — a hardcoded "Ticket Submitted" entry from `created_at` at `:448-456`, *before* the real-event loop |
| **Admin** | `admin_portal/views.py:175` (drawer) | `_ticket_timeline.html:2-22` (raw `ev.action`) | No |
| **Developer** | `developer_portal/views.py:52` | `developer_portal/ticket-detail.html:378` | No |
| **Tester** | `tester_portal/views.py:52` | `tester_portal/ticket-detail.html:363` | No |
| **Sub-user** | `subuser_portal/views.py:87` | `subuser_portal/ticket-detail.html:378` | No |

**Why dev/tester show "less" than the client:** they don't *filter* fewer events — they
show the identical real `ticket.events`. The client merely **synthesizes** an extra leading
"Ticket Submitted" line from `created_at` that the others don't. Combined with 4a (no real
submission event), the earliest *real* event is `assign` → so dev/tester/admin/subuser
"start at Assigned to developer," while the client appears to have the full history thanks
to its synthetic line.

### Fix (single change, satisfies TARGET §7)
Record a real **submission `TicketEvent`** at creation (e.g. `action="submitted"`,
`to_status="new"`) — written in both submit views (and `seed_demo`), or centralized via a
`Ticket` post-create hook so it can't be forgotten. Add `"submitted"` to the
`EVENT_LABELS` / `EVENT_ICONS` / `EVENT_DOT_CLS` maps in
`tickets/templatetags/shared_ticket_extras.py`. Then **remove the client's synthetic line**
(`ticket-detail.html:448-456`) so it doesn't duplicate, and every portal's existing
`{% for event in events %}` loop renders the **complete** history identically — dev/tester/
admin/subuser will match the client. (Optional polish: have the admin drawer render
`ev.action|event_label` instead of the raw `ev.action` so it reads like the other portals.)

---

## Bugs vs enhancements · independence

- **Issue 1** — BUG (static placeholder shown as real per-ticket detail).
- **Issue 2** — BUG/gap (modal missing the `send_to_uat` control the row has).
- **Issue 3** — ENHANCEMENT / consistency (+ a minor safety bug: modal **Close** submits
  with no confirmation).
- **Issue 4 (4a+4b)** — BUG (incomplete audit trail vs TARGET §7); **4a and 4b are one
  fix** (add the submission event, drop the client's synthetic line).

**Independent vs related:**
- **4a + 4b = one timeline fix** (as you expected).
- **Issue 1 (option b) is related to Issue 4**: routing new tickets through the detail
  partial gives them real data *and* a real timeline at once.
- **Issues 2 + 3 are related** (both live in `_ticket_detail.html`'s action layer — adding
  `send_to_uat` is the natural moment to standardize confirmations).
- Issue 4 is otherwise **independent** of 2/3 and can ship on its own.
