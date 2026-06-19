# FLOW_WALKTHROUGH.md — manual cross-portal lifecycle check

> Drives **one ticket** from submit → close across all five portals in the browser,
> covering the JS/visual layer the Django test client can't (modals, toasts, tab
> switching, global search, empty states, detail-modal action buttons). The
> automated coverage lives in `tickets/tests_e2e_flow.py`; this doc is the human
> companion for the visual/interaction layer.

## Setup

```powershell
.\venv\Scripts\Activate.ps1
python manage.py seed_demo        # demo users + clients + tickets
python manage.py runserver
```

Demo logins (all password `TweedleDemo!2026`): `demo_admin`, `demo_client`,
`demo_subuser`, `demo_dev`, `demo_tester`. Log in/out between roles (use the profile
menu → Sign Out, or an incognito window per role). Org for the demo client/subuser is
**GMEC**.

> **Two expected anomalies — do NOT treat as walkthrough failures:**
> - **(A) Client "Respond" dead button** (defect #3): on an *Awaiting Client* ticket the
>   client/sub-user detail shows a **disabled** "Respond"/"Reply in Chat" button — chat
>   posting isn't wired yet. The loop is driven by the admin (Resume). Expected.
> - **(B) Sub-user-submitted tickets can't be approved** (finding #2, escalated): a ticket
>   *submitted by a sub-user* cannot be moved to Resolved by any portal — the client's
>   Approve is engine-blocked (not the requester) and the admin portal has no Approve
>   control. Only admin **Recall** or **Cancel** work. The main walkthrough below uses a
>   **client-submitted** ticket, which approves normally. The sub-user path is exercised
>   separately in §B at the end and is expected to stick at UAT.

---

## MAIN WALKTHROUGH — client-submitted ticket, submit → close

### 1. Client submits  (`demo_client`)
1. Go to **/client/** → click **Submit a Ticket** (or `/client/submit/`).
2. Fill subject, a description (≥20 chars), pick a **Category** and **Priority** → **Submit**.
3. **Expect:** success toast; redirected to the dashboard; the new ticket row shows the
   badge **"New — Received"**.

### 2. Admin triages & assigns  (`demo_admin`)
1. Go to **/admin-portal/**. The **Inbox** tab shows the ticket with badge **"New"**.
2. Click the row → the **assignment modal** opens (Assign Developer / Reject).
3. Select a **Developer** and a **Tester** (keep "Assign tester now") → **Assign Ticket** →
   confirm.
4. **Expect:** toast "assigned…"; the ticket leaves Inbox and appears in **In Progress**
   with Stage **"Development"**.
5. Open the **global search** (top bar), type the ticket ID/subject → the result row shows a
   proper **"Development"** status pill (correct label + color).

### 3. Developer submits for testing  (`demo_dev`)
1. Go to **/developer/** → the ticket is in the list with badge **"Development"**.
2. Open it → the **Update Progress** card shows **"Submit for Testing"** → click → confirm
   in the modal.
3. **Expect:** toast; badge becomes **"In Testing"**; the action card is now read-only
   ("In Testing"). (Admin In-Progress Stage shows **"Testing"**.)

### 4. Tester passes  (`demo_tester`)
1. Go to **/tester/** → the ticket now appears in the queue with badge **"Testing"**
   (it was *not* visible during Development — that's correct).
2. Open it → **Testing Decision** card → **Pass — Mark Ready for UAT** → confirm.
3. **Expect:** toast; badge becomes **"Passed"** (read-only). (Developer sees **"Ready for
   UAT"**.)

### 5. Admin sends to client UAT  (`demo_admin`)
1. **/admin-portal/** → **In Progress** tab → the ticket's Stage is **"Ready for UAT"** with
   a green **Send to Client UAT** icon on the row.
2. Click it → confirm.
3. **Expect:** toast; the ticket moves to the **UAT Approval** tab. Open its detail → header
   badge **"UAT Approval"**, action **Recall to In Progress**.

### 6. Client approves  (`demo_client`)
1. **/client/** → the ticket badge is **"Ready for Your Review"** (with a "your action needed"
   dot).
2. Open it → **Ready for Your Review** card with **Approve & Close** and **Request Changes**.
3. Click **Approve & Close** → confirm in the overlay.
4. **Expect:** toast; badge becomes **"Awaiting Closure"**; a **Reopen** control is offered.

### 7. Admin closes  (`demo_admin`)
1. **/admin-portal/** → **Resolved** tab → open the ticket → detail shows **Close Ticket**
   and **Reopen Ticket**.
2. Click **Close Ticket**.
3. **Expect:** toast; ticket moves to the **Closed** tab (badge **"Closed"**). Client now
   sees **"Completed"** with a Reopen (≤14d) option.

### 8. Visual spot-checks (any time)
- **Empty states:** click a tab with no tickets (e.g. **Rejected** or **Cancelled** on a
  fresh DB) → "No … tickets." placeholder row renders.
- **Tab switching / headings:** each tab updates the heading + the "N tickets · …" meta.
- **Cancelled tab:** exists between Rejected and (end); cloned from Closed.
- **Toasts** appear bottom-right on every action; **modals** close on backdrop click / Esc.

---

## BRANCH SPOT-CHECKS (optional, pick any)

- **Tester fail → developer resubmit:** at step 4 click **Fail** with notes → tester badge
  **"Failed"**, developer badge **"Returned from QA"** + **Resubmit for Testing**.
- **No-tester path:** at step 2 uncheck "Assign tester now" and assign a developer only →
  the developer detail shows **"Mark Ready for UAT"** instead of "Submit for Testing"; tester
  never sees the ticket.
- **Client Request Changes:** at step 6 click **Request Changes**, enter feedback → ticket
  returns to **Development** (developer sees it again).
- **Admin Recall:** on a UAT ticket, admin detail → **Recall to In Progress** → back to
  Development.
- **Request Info → Resume (anomaly A):** admin detail on an In-Progress ticket → **Request
  Info** with a message → ticket → **Awaiting Client**; client badge **"Your Input Needed"**
  and a **disabled** "Respond" button *(expected anomaly A)*; admin detail → **Resume Ticket**
  → back to In Progress.
- **Reject → Restore:** admin assignment modal → **Reject Ticket** with a reason → **Rejected**
  tab (client badge **"Not Accepted"**); open it → **Restore to Inbox** → back to **Inbox /
  New**.
- **Reopen:** on a Resolved or Closed ticket, admin detail → **Reopen Ticket** (reason
  required) → back to **Development**, same developer.
- **Cancel → Cancelled tab:** on an In-Progress or Awaiting-Client ticket, admin detail →
  **Cancel Ticket** (reason optional) → confirm → ticket appears in the **Cancelled** tab
  (badge **"Cancelled"**), opens read-only; the requester gets a notification.

---

## §B. SUB-USER PATH (exercises anomalies A + B)

1. **`demo_subuser`** at **/subuser/** → **Submit a Ticket** → submit. Badge
   **"New — Received"**.
2. Drive it to **UAT** via admin/dev/tester exactly as steps 2–5 above (the sub-user's
   ticket is visible to the **primary client** `demo_client` too, via the org dashboard).
3. **`demo_subuser`** → open the ticket → **Please Verify** card → **Confirm — Issue
   Resolved** → confirm.
   - **Expect:** the sub-user badge/card becomes **"Confirmed — Awaiting Approval"**; the
     primary client (`demo_client`) sees **"Ready for Your Review (sub-user confirmed)"**; the
     admin detail badge reads **"UAT — sub-user confirmed, awaiting client approval"**.
4. **`demo_client`** → open that ticket → you'll see **Approve & Close / Request Changes**
   buttons **(anomaly B: present-but-broken)**. Clicking **Approve** produces an **error
   toast** and the ticket **stays at UAT** — the primary client is not the requester, so the
   engine blocks it.
5. **`demo_admin`** → the admin portal has **no Approve control** for this ticket; the only
   forward moves are **Recall** (→ Development) or **Cancel**.
   - **Expect / FINDING:** a sub-user-submitted ticket currently **cannot be moved to
     Resolved by any portal** — it is stuck at UAT pending a fix decision (see finding #2,
     escalated). This is a known, captured gap, not a walkthrough error.
