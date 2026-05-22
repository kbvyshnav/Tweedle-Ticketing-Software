# PROJECT HANDOFF — Tweedle Ticketing Software

> **Status as of 2026-05-22** — Phase 12 complete (Admin Portal fully complete — all flows, forms, filters, interactions, and component cleanup). No backend wired yet.
> This document is the single source of truth for any developer or AI continuing this project.

---

## 1. PROJECT OVERVIEW

### What Tweedle Is

Tweedle is a **multi-role B2B ticketing and support management SaaS** for organisations that manage software support across multiple clients, developers, and testers. Each role has a distinct interface with its own color identity, so users instantly recognise which workspace they are in.

### The Problem It Solves

Traditional support ticketing tools are single-audience. Tweedle gives every stakeholder — admin, developer, tester, client, sub-user — a purpose-built workspace with exactly the features they need and none they don't. Tickets flow through a defined lifecycle with full traceability.

### Target Users

| Actor | Role | Access Level |
|-------|------|--------------|
| Organisation admin | Admin | Full — tickets, team, clients, reports |
| Software developer | Developer | Assigned tickets, chat, status updates |
| QA engineer | Tester | Testing tickets, remarks, verification |
| External client | User | Submit and track own tickets only |
| Client team member | Sub-user | Limited view under a client account |

### Current Build Status

- **Phase 10 complete** — full Admin Portal UI (all pages, all modals, all interactions)
- **Pure frontend** — all data is static/dummy; no backend wired
- **Django-ready** — every template includes annotated `<!-- Django: … -->` comments showing exactly where to add template tags, context variables, URLs, and API calls
- **Not deployed** — runs locally via HTTP server only

---

## 2. TECH STACK

### Frontend (Current — All That Exists)

| Technology | Version | Why |
|-----------|---------|-----|
| **HTML5** | — | Semantic, Django-template-ready markup |
| **CSS3** | — | Custom design system via CSS custom properties |
| **Vanilla JavaScript** | ES5/ES6 | No framework dependency; all scripts are inline in templates |
| **Bootstrap 5** | 5.3.3 | Grid, responsive utilities, and `visually-hidden` class only |
| **Boxicons** | 2.0.9 | Icon library used for all UI icons |
| **Google Fonts** | — | Poppins (all UI content) + Lato (sidebar/topbar only) |

**All vendors load from CDN** — there is no `package.json`, no build step, and no node_modules. The project is a plain file collection.

### File-Serving Requirement

`fetch()` in the JS page router is blocked by the browser under `file://` protocol. The project **must be served via HTTP** to work:

```bash
# From the project root (Tweedle-Ticketing-Software/)
python -m http.server 8080
# Then open: http://localhost:8080/Tweedle/templates/login.html
```

### Planned Backend Stack

| Technology | Purpose |
|-----------|---------|
| **Python Django** | Web framework |
| **PostgreSQL** | Primary database |
| **Django REST Framework** | API layer for JS fetch() calls |
| **django-allauth** | Authentication |
| **django-otp** | Two-factor authentication (Phase 2) |
| **Google OAuth** | Social login (Phase 3) |

---

## 3. ROLE SYSTEM

### Role Color Identities

| Role | Body Class | Primary Color | Hex | Icon Family |
|------|-----------|--------------|-----|------------|
| Admin | `role-admin` | Blue | `#3C91E6` | `bx-grid-alt` dashboard |
| Developer | `role-developer` | Purple | `#8b5cf6` | — |
| Tester | `role-tester` | Teal | `#20b8a6` | — |
| User/Client | `role-user` | Orange | `#FD7238` | — |
| Sub-user | `role-subuser` | Amber | `#ecbe25` | — |

### How Theme Switching Works

1. `tweedle-tokens.css` defines four CSS custom properties with Admin defaults: `--tw-primary`, `--tw-primary-dark`, `--tw-primary-light`, `--tw-primary-text`
2. A **theme file** (`theme-{role}.css`) overrides exactly those four tokens at `:root` level
3. Every component that uses color references `var(--tw-primary*)` — so swapping the theme file instantly recolors the entire UI
4. The role is applied via `<body class="role-admin">` (or other role class). Django sets this based on `request.user.role`

### Which CSS File Controls Each Role

```
static/css/themes/
  theme-admin.css      → Blue #3C91E6 — currently active in base.html
  theme-developer.css  → Purple #8b5cf6
  theme-tester.css     → Teal #20b8a6
  theme-user.css       → Orange #FD7238
  theme-subuser.css    → Amber #ecbe25 (light — uses dark text on buttons)
```

---

## 4. PROJECT FOLDER STRUCTURE

```
Tweedle-Ticketing-Software/
├── README.md                          — Public-facing project overview
├── PROJECT_HANDOFF.md                 — This document
└── Tweedle/
    ├── static/
    │   ├── css/
    │   │   ├── tweedle-tokens.css     — All CSS custom properties (design tokens)
    │   │   ├── tweedle-base.css       — Reset, typography, sidebar/topbar/main layout
    │   │   ├── tweedle-components.css — All reusable UI components
    │   │   ├── themes/
    │   │   │   ├── theme-admin.css    — Blue role theme
    │   │   │   ├── theme-developer.css — Purple role theme
    │   │   │   ├── theme-tester.css   — Teal role theme
    │   │   │   ├── theme-user.css     — Orange role theme
    │   │   │   └── theme-subuser.css  — Amber role theme
    │   │   └── pages/
    │   │       ├── dashboard.css      — Dashboard: stat strip, tabs, toolbar, global search, overdue, bulk bar
    │   │       ├── clients.css        — Clients table page
    │   │       ├── team.css           — Team management page
    │   │       ├── reports.css        — Reports filters and TAT badges
    │   │       ├── chat.css           — Full chat panel (slide-in drawer)
    │   │       ├── ticket-details.css — Ticket detail modal and action panels
    │   │       ├── ticket-timeline.css — Full timeline modal and panel styles
    │   │       ├── notification.css   — Notification bell dropdown
    │   │       ├── settings.css       — Settings page sections and table (new in Phase 12)
    │   │       └── login.css          — Auth pages (shared by login + OTP)
    │   └── images/
    │       ├── favicon.svg
    │       ├── jinoy.jpg
    │       ├── MEFS.png
    │       └── Tweedle Logo/
    │           ├── tweedle-mark-black.svg
    │           ├── tweedle-mark-blue.svg  — Used in sidebar and auth pages
    │           ├── tweedle-mark-white.svg
    │           ├── tweedle-wordmark-black.svg
    │           ├── tweedle-wordmark-blue.svg
    │           └── tweedle-wordmark-white.svg
    └── templates/
        ├── base.html                  — SHELL: sidebar + topbar + JS page router
        ├── login.html                 — Standalone auth: sign-in form
        ├── otp-verify.html            — Standalone auth: 6-digit OTP verification
        ├── components/
        │   ├── confirm-modal.html     — Reusable confirm/cancel dialog (partial)
        │   └── notification-bell.html — Notification bell component (partial)
        └── admin_portal/
            ├── dashboard.html         — MAIN PAGE: 5 stat cards + 5 tab tables + all modals/panels
            ├── clients.html           — Clients table + full Onboard New Client modal form
            ├── team.html              — Team members table + full Add Developer/Tester modal form
            ├── reports.html           — Filter form + report table + download buttons
            ├── settings.html          — Settings page: Org form, Notification toggles, Branding (new in Phase 12)
            ├── chat.html              — DEV-ONLY standalone view for chat panel
            ├── notification.html      — Full notifications centre page (placeholder content)
            ├── ticket-details.html    — DEV-ONLY standalone view for existing-ticket modal
            ├── ticket-details-new.html — DEV-ONLY standalone view for new-ticket assignment modal
            └── ticket-timeline.html   — DEV-ONLY standalone view for ticket timeline
```

**File Classification:**

| Type | Files |
|------|-------|
| **Shell / layout** | `base.html` |
| **Standalone pages** (serve directly) | `login.html`, `otp-verify.html` |
| **Partial pages** (injected by router) | All `admin_portal/*.html` |
| **Dev-only standalone views** | `chat.html`, `ticket-details.html`, `ticket-details-new.html`, `ticket-timeline.html`, `notification.html` |
| **Component partials** | `components/confirm-modal.html`, `components/notification-bell.html` |

---

## 5. DESIGN SYSTEM

### CSS Token Architecture

The design system uses a strict **5-file load order**. Never change this order.

```
1. tweedle-tokens.css     — :root variables ONLY. No classes.
2. theme-{role}.css       — Overrides 4 role tokens + role utility classes
3. tweedle-base.css       — Reset + layout shell (uses tokens)
4. tweedle-components.css — All components (uses tokens)
5. pages/{page}.css       — Page-specific overrides (uses tokens + components)
```

### Color Tokens

**Role tokens** (the only 4 that change per theme):
```css
--tw-primary         /* main role color */
--tw-primary-dark    /* hover/focus shade */
--tw-primary-light   /* tinted background */
--tw-primary-text    /* text on light background */
```

**Neutral palette** (never override):
```css
--tw-bg-body         #eeeeee    /* page background */
--tw-bg-surface      #ffffff    /* cards, panels, modals */
--tw-bg-sidebar      #F9F9F9   /* sidebar and topbar */
--tw-text-primary    #342E37   /* headings, strong text */
--tw-text-secondary  #666666   /* labels, meta */
--tw-text-muted      #999999   /* timestamps, placeholders */
--tw-border          #e5e5e5   /* default borders */
--tw-overlay         rgba(0,0,0,0.60) /* modal backdrop */
```

**Status colors** (semantic, never role-overridden):
```css
--tw-status-inbox-bg / text        /* blue tint */
--tw-status-progress-bg / text     /* yellow tint */
--tw-status-forwarded-bg / text    /* orange tint */
--tw-status-closed-bg / text       /* green tint */
--tw-status-testing-bg / text      /* light blue */
--tw-status-development-bg / text  /* light green */
--tw-status-uat-bg / text          /* light olive */
```

**Priority colors:**
```css
--tw-priority-high-bg / text       /* red tint */
--tw-priority-medium-bg / text     /* amber tint */
--tw-priority-low-bg / text        /* green tint */
```

**Semantic / action:**
```css
--tw-danger    #DB504A    --tw-warning   #FD7238
--tw-success   #28a745    --tw-info      #3C91E6
```

### Typography Scale

```css
--tw-text-xs    11px   /* timestamps, meta */
--tw-text-sm    12px   /* badge labels */
--tw-text-base  13px   /* body, table cells, buttons */
--tw-text-md    14px   /* modal body, form labels */
--tw-text-lg    16px   /* sidebar nav, section headings */
--tw-text-xl    20px   /* section h3 */
--tw-text-2xl   24px   /* modal h2 */
--tw-text-3xl   30px   /* page h1 */
```

Fonts: `--tw-font-primary: 'Poppins'` (everything), `--tw-font-secondary: 'Lato'` (sidebar/topbar only)

### Spacing Scale (4px base grid)

```css
--tw-space-1: 4px  --tw-space-2: 8px  --tw-space-3: 12px --tw-space-4: 16px
--tw-space-5: 20px --tw-space-6: 24px --tw-space-8: 32px --tw-space-10: 40px
--tw-space-12: 48px
```

### Border Radius

```css
--tw-radius-sm:   6px    /* inputs, small buttons */
--tw-radius-md:   10px   /* dropdowns, filter cards */
--tw-radius-lg:   12px   /* table cards, timeline items */
--tw-radius-xl:   20px   /* stat tiles, modal containers */
--tw-radius-pill: 999px  /* status pills, role badges */
```

### Shadows

```css
--tw-shadow-sm:  0 1px 4px rgba(0,0,0,0.06)
--tw-shadow-md:  0 4px 12px rgba(0,0,0,0.08)
--tw-shadow-lg:  0 8px 24px rgba(0,0,0,0.12)
--tw-shadow-xl:  0 20px 60px rgba(0,0,0,0.25)  /* modals */
```

### Layout Dimensions

```css
--tw-sidebar-width:           209px
--tw-sidebar-collapsed-width: 60px
--tw-topbar-height:           56px
```

### Z-Index Scale

```
dropdown: 100 | sticky: 200 | modal: 300 | overlay: 400 | toast: 500
```

### Responsive Breakpoints

Three breakpoints only — no others:
- `1024px` — large screen: layout adjustments
- `768px` — tablet: sidebar collapses to off-canvas
- `576px` — mobile: single column

### How to Add a New Role Theme

1. Copy `theme-admin.css` → `theme-{rolename}.css`
2. Change the 4 `:root` token values to the new role's color
3. Update `--tw-shadow-primary` RGBA to match the new hue
4. If the primary color is light (like amber), change `.tw-btn-primary { color: }` to dark text
5. Load the new theme file in `base.html` position 2 (replace the current theme link)
6. Set `<body class="role-{rolename}">` in the shell template

---

## 6. PAGE-BY-PAGE BREAKDOWN

### `templates/login.html`

**Purpose:** Single entry point for all roles. Role-neutral sign-in form.

**Key sections:**
- Left panel (`.tw-auth-left`): brand logo, tagline, feature pills, copyright
- Right panel (`.tw-auth-right`): sign-in form, server error alert, forgot password link, Google OAuth (hidden, Phase 3)

**JS functions:**
- `showFieldError(input, errorEl, message)` — adds error class and message
- `clearFieldError(input, errorEl)` — removes error state
- Form submit handler — validates username (required) and password (min 6 chars), triggers loading state, redirects to `base.html` (standalone) or lets form POST (Django)
- Password toggle — swaps `type="password"` ↔ `type="text"`, updates icon
- Remember me — persists checkbox state to `localStorage`

**Django hooks:** `action="{% url 'account_login' %}"`, `{% csrf_token %}`, `{% if form.errors %}` on server alert, `{% url 'password_reset' %}` for forgot link

**Connected pages:** On success → `base.html` (standalone) or role dashboard URL (Django)

---

### `templates/otp-verify.html`

**Purpose:** 6-digit OTP verification for 2FA. UI stub — backend not wired.

**Key sections:**
- Left panel: same structure as login, different headline ("Verify your identity")
- Right panel: back link, 6-digit input group (`.tw-otp-box`), countdown timer, resend button, submit

**JS functions:**
- OTP input auto-advance — typing a digit focuses the next box; backspace on empty box goes back
- Paste handler — distributes pasted digits across all 6 boxes
- `startTimer(seconds)` / `formatTime(secs)` — 5-minute countdown timer; on expiry shows resend button
- Resend handler — resets timer, clears inputs, calls `console.log` (Django: POST to `otp_resend`)
- Form submit handler — validates all 6 boxes filled, triggers loading state

**Django hooks:** `action="{% url 'otp_verify' %}"`, `{% csrf_token %}`, `{{ masked_email }}` for email pill

**Connected pages:** Back link → `login.html`

---

### `templates/base.html`

**Purpose:** The application shell. Provides sidebar + topbar + main content area. Also hosts the JS page router for standalone preview.

**Key sections:**
- Sidebar (`.sidebar`): brand mark, main nav (Dashboard/Clients/Team/Reports), bottom nav (Settings)
- Topbar (`.topbar`): hamburger, global search form, notification bell, profile avatar
- Notification bell (`.tw-notif-bell-wrap`): dropdown panel with unread items, "mark all read" button
- `<main id="main-content">`: empty placeholder — filled by JS router or Django blocks

**JS functions (base shell):**
- Sidebar toggle — `.hide` class for desktop collapse; `.mobile-open` for mobile overlay
- `handleResize()` — removes collapse state when viewport widens past 768px
- Notification bell toggle — `aria-expanded`, click-outside to close
- "Mark all read" — removes `.unread` class from all items, removes count badge

**JS page router (standalone only — remove at Django deploy):**
- `showLoader()` — loading spinner while fetching
- `extractContent(html)` — extracts `<main>` or `<body>` content from fetched HTML string
- `injectContent(html)` — sets `innerHTML` and re-executes inline `<script>` tags (required because `innerHTML` does not run scripts)
- `loadPage(pagePath)` — async fetch + inject; supports `pagePath#tabHash` format to auto-click a tab after load
- Nav link click handler — updates active state, calls `loadPage(link.dataset.page)`
- Auto-loads `admin_portal/dashboard.html` on startup

**Django hooks:**
- `{% block title %}` on `<title>`
- `{% static '...' %}` on all CSS and JS `<link>`/`<script>` tags
- `{% block body_role %}admin{% endblock %}` on `<body class="role-…">`
- `{% block page_css %}{% endblock %}` replaces all the preloaded page CSS links
- `{% block content %}{% endblock %}` replaces `<main id="main-content">` content
- `{% block page_js %}{% endblock %}` replaces the router script block
- `{% url '...' %}` on sidebar nav links, topbar search action, notification URLs

---

### `templates/admin_portal/dashboard.html`

**Purpose:** Main Admin hub. Shows all tickets by status with tabbed view. All ticket actions happen here via modals and panels.

**Key sections:**
- Section A: Page header + global search with floating overlay (`#globalSearchWrap`)
- Section B: Stat strip (4 clickable cards: Inbox / In Progress / Forwarded / Closed)
- Section C: Table card
  - C1: Underline tab row (Inbox / In Progress / Forwarded / Closed)
  - C1b: Tab status bar (dynamic heading + meta text)
  - C2: Filter toolbar (Company dropdown, Date range picker, Priority stub, table search, sort, more)
  - C3: Four tab content panels (each with a `<table class="tw-table">`)

**Modals / panels:**
- `#ticketDetailsModal` — existing ticket details (data-status drives section visibility)
  - `#dashReassignPanel` — reassign slide-up panel (inside modal)
  - `#dashForwardPanel` — forward to client slide-up panel (inside modal)
- `#newTicketModal` — new ticket assignment (developer select with workload stats)
- `#confirmModal` — reusable confirm/cancel dialog
- `#chatPanel` — right-side sliding chat drawer
- `#timelinePanel` — right-side sliding mini timeline
- `#fullTimelineModal` — full-screen timeline modal (fetches `ticket-timeline.html`)

**JS functions (all in this file):**
| Function | Purpose |
|----------|---------|
| `updateStatCardActiveState(tabId)` | Highlights matching stat card |
| `updateTabHeading(tabId)` | Updates heading + meta text for active tab |
| `openTicketDetailsModal(id, subject, status, allottee)` | Opens existing-ticket modal, sets data-status |
| `closeTicketDetailsModal()` | Closes it |
| `openNewTicketModal(id, subject, status)` | Opens new-ticket assignment modal |
| `closeNewTicketModal()` | Closes it + resets form |
| `showDeveloperInfo()` | Reads `data-*` from select option, shows workload stats |
| `confirmAssignment()` | Triggers confirm modal for developer assignment |
| `confirmRejection()` | Triggers confirm modal with rejection reason textarea |
| `resetNewTicketForm()` | Clears select/textarea/checkbox in new ticket form |
| `openDashReassignPanel()` / `openDashForwardPanel()` | Opens action panels inside details modal |
| `closeDashActionPanel(panelId)` | Closes an action panel |
| `confirmDashReassign()` / `confirmDashForward()` | Validates and executes reassign/forward |
| `openConfirmModal(config)` | Reusable confirm modal API (type, title, message, details, onConfirm) |
| `closeConfirmModal()` / `executeConfirmAction()` | Confirm modal control |
| `openChatPanel(ticketId, subject)` / `closeChatPanel()` | Chat drawer |
| `sendMessage()` | Appends new message bubble to chat area, resets inputs |
| `removeAttachment()` | Clears file input and attachment strip |
| `openTimelinePanel(ticketId, subject)` / `closeTimelinePanel()` | Mini timeline drawer |
| `openFullTimeline(ticketId)` | Fetches `ticket-timeline.html`, injects into full-screen modal |
| `closeFullTimeline()` | Closes full timeline modal |
| `openCloseTicketConfirm()` | Uses `openConfirmModal` to confirm ticket closure |
| `showDashToast(message, type)` | Shows bottom-right toast notification |
| Global search IIFE | Filters tickets from all tab rows, shows overlay with results, highlights matching row on click |
| Escape key handler | Priority chain: global search → confirm → ticket details → new ticket → timeline → chat |

**Django template variables:**
`{{ inbox_count }}`, `{{ inprogress_count }}`, `{{ forwarded_count }}`, `{{ closed_count }}` (stat strip); `{% for ticket in inbox_tickets %}` / `inprogress_tickets` / `forwarded_tickets` / `closed_tickets` (table rows)

---

### `templates/admin_portal/clients.html`

**Purpose:** View and manage client organisations.

**Key sections:**
- Page header (h1 "Clients")
- Table card with search + "Onboard New Client" button
- Clients table: Name (with avatar), Country, Contact, Email, Status, Actions
- `#onboardModal` — stub modal placeholder (form not built yet)

**JS functions:**
- `clientSearchInput` handler — filters table rows by text content
- `openOnboardModal()` / `closeOnboardModal()` — modal open/close + scroll lock
- `manageUsers(clientId)` — placeholder (`console.log` only)
- `showDetails(clientId)` — placeholder
- `showSettings(clientId)` — placeholder

**Django hooks:** `{% for client in clients %}`, `{{ clients|length }}`, `{{ client.company_name }}`, `{{ client.status }}`, etc.

---

### `templates/admin_portal/team.html`

**Purpose:** View and manage developer and tester team members.

**Key sections:**
- Page header
- Table card with search + "Add Developer / Tester" button
- Team table: Name (with avatar), Username, Role badge, Email, Status toggle, View Details
- `#addMemberModal` — stub modal placeholder

**JS functions:**
- `memberSearchInput` handler — filters rows by first 5 columns text
- `toggleMemberStatus(checkbox, username)` — updates label text; Django: POST to enable/disable endpoint
- `openAddMemberModal()` / `closeAddMemberModal()` — modal control
- `viewDetails(username)` — placeholder

**Django hooks:** `{% for member in team_members %}`, `{{ member.username }}`, `{{ member.role }}`, `{{ member.is_active }}`, etc.

---

### `templates/admin_portal/reports.html`

**Purpose:** Filter and view ticket reports with TAT tracking. Export to PDF/Excel.

**Key sections:**
- Filter card: From Date, To Date, Status, Developer, Client, "Show Report" button
- Report summary banner (dynamically rendered by JS)
- Report table: Ticket ID, Client, Subject, Status, Issue Date, Allotment Date, Developer, Closed Date, TAT
- Download buttons: PDF and Excel
- `#reportDetailModal` — acknowledgement modal for download action

**JS functions:**
- `generateReport()` — reads filter values, renders summary banner HTML; called on load and on button click
- `showModal(message, title)` / `closeReportModal()` — download acknowledgement modal
- `downloadReport(format)` — calls `showModal` with format string; Django: fetch to download endpoint

**Django hooks:** `action="{% url 'admin_reports' %}"`, `{% for report in reports %}`, `{{ request.GET.from }}`, etc.

---

### `templates/admin_portal/chat.html`

**Purpose:** Standalone dev view of the chat panel component. In production, this panel is injected into `dashboard.html` via JS — it is not a separate page.

**Structure:** `<div class="tw-chat-panel open">` — same markup used inline in `dashboard.html`

**JS functions:**
- `chatTextarea` auto-resize — expands up to 80px
- `attachBtn` click handler — triggers hidden file input
- `handleFileSelection(files)` — shows attachment preview strip
- `removeAttachment()` — clears file + strip
- `sendMessage()` — appends sent message bubble (admin role hardcoded), supports text + file + image
- `emailCheckbox` change — console.log (Django: include in POST payload)
- Close button + Escape key handler
- `window.load` scroll-to-bottom

---

### `templates/admin_portal/notification.html`

**Purpose:** Full-page notification centre (the "View all notifications" destination from the topbar bell). Currently a placeholder — renders a stub message. Django view will render all notifications here.

---

### `templates/admin_portal/ticket-details.html`

**Purpose:** Standalone dev view of the existing ticket details modal. In production, this modal lives inside `dashboard.html`. Used for isolated development/testing only.

**Key modal sections:**
- Header: Ticket ID, Subject, status pill, allottee tag, Chat/Timeline/Reassign/Forward action buttons
- Body: 4×2 info grid, Description, Forwarding Details (hidden unless `data-status="forwarded"`), Closure Details (hidden unless `data-status="closed"`), Attachments
- Footer: Current status badge + "Close Ticket" button (hidden when `data-status="closed"`)
- `#reassignPanel` slide-up — Developer/Tester toggle, assignee select, reason textarea
- `#forwardPanel` slide-up — Client contact select, message textarea

**JS functions:**
- `openTicketModal(id, subject, status, allottee)` — sets data-status, populates fields
- `closeTicketModal()` — closes modal + scroll unlock
- `openReassignPanel()` / `openForwardPanel()` / `closeActionPanel(panelId)` — action panel control
- `confirmReassign()` / `confirmForward()` — validate and execute (Django: POST stubs)
- `showToast(message, type)` — toast notification
- `openCloseTicketConfirm()` — inline `confirm()` dialog (standalone); full `openConfirmModal` in dashboard.html
- Reassign toggle buttons — Developer / Tester selector

---

### `templates/admin_portal/ticket-details-new.html`

**Purpose:** Standalone dev view of the new ticket assignment modal (Inbox tab tickets). Same as above, used for isolated dev testing.

**Key modal sections:**
- Header: Ticket ID, Subject, "New Ticket" status pill
- Body: 6-field info grid, Description
- Assignment section: Developer select (with workload stats panel), Comments textarea, Email notification checkbox
- Action buttons: "Assign Ticket" (disabled until developer selected), "Reject / Close Ticket"

---

### `templates/admin_portal/ticket-timeline.html`

**Purpose:** Standalone dev view of the ticket timeline. In production, its content is fetched and injected into `#fullTimelineModal` in `dashboard.html`.

**Key sections:**
- Ticket header card (`.tw-ticket-header-card`): Ticket ID badge, Subject, Status badge, Close button
- Stats bar: Issue Date, Priority, Close Date, Resolution Time
- Vertical timeline (`.tl-timeline`): ordered event cards with icon, event type, description, timestamp, actor + role pill

**JS functions:**
- Close button handler — hides card; Django: dispatch `timeline:close` event

---

### `templates/components/confirm-modal.html`

**Purpose:** Reusable confirm/cancel dialog partial. Used by `dashboard.html` (referenced inline — actual markup is in `dashboard.html`, not separate include currently).

**Structure:** Overlay → confirm box with icon, title, message, details area, Cancel + Confirm buttons.

---

### `templates/components/notification-bell.html`

**Purpose:** Notification bell + dropdown panel partial. Referenced in `base.html` (markup is inline there currently).

---

## 7. COMPONENT LIBRARY

All components are in `tweedle-components.css`. Reference:

| Class | Description | Variants |
|-------|-------------|---------|
| `.tw-btn` | Base button | + `.tw-btn-primary`, `.tw-btn-outline`, `.tw-btn-danger`, `.tw-btn-success`, `.tw-btn--sm` |
| `.tw-btn-icon` | 36×36 icon-only button | Hover: primary bg + white icon |
| `.tw-btn-close` | Circle close button (modal header) | Rotates 90° on hover |
| `.tw-badge` | Base pill badge | + `.tw-status-inbox/progress/forwarded/closed` |
| `.tw-status-badge` | Sub-status pill | `--new`, `--development`, `--testing`, `--uat`, `--forwarded`, `--closed`, `--active` |
| `.tw-status-tag` | Uppercase square-corner tag (reports) | Same modifiers as status-badge |
| `.tw-priority-badge` | Priority indicator | `--high`, `--medium`, `--low` |
| `.tw-tat-badge` | TAT evaluation badge | `--met`, `--missed`, `--pending` |
| `.tw-role-pill` | Role identity chip | `--admin`, `--developer`, `--tester`, `--user`, `--subuser` |
| `.tw-role-badge` | Role label in team table | `--developer`, `--tester` |
| `.tw-count-badge` | Numeric count in role primary color | — |
| `.tw-avatar` | Circular initials avatar | `--sm`, `--lg`; color: `--blue`, `--purple`, `--violet`, `--teal`, `--rose`; role: `--admin`, `--developer`, `--tester`, `--user` |
| `.tw-table-card` | White surface card for tables | `--dashboard` (no padding, overflow visible) |
| `.tw-table` | Styled `<table>` | Sticky header + last column, hover lift |
| `.tw-row-actions` | Icon row in table last cell | `.tw-action-icon` + `--timeline`, `--chat`, `--more` |
| `.tw-star-icon` | Favourite star toggle | `.active` = filled gold |
| `.tw-row-attachment` | File chip inside table cell | PDF/DOC/IMG icon color modifiers |
| `.tw-modal-overlay` | Full-screen modal backdrop | `.active` = visible |
| `.tw-modal` | Modal container | `--sm`, `--lg` |
| `.tw-info-grid` | Metadata card grid | `--3col`, `--4col`, `--6` |
| `.tw-info-item` | Single metadata card | Hover: primary-light bg + lift |
| `.tw-description-box` | Long text block | — |
| `.tw-attachment-item` | Attachment row | `.tw-file-icon--pdf/doc/img` |
| `.tw-chat-container` | Chat window wrapper | Full-screen on mobile |
| `.tw-message` | Chat message bubble | `.sent`, `.received` |
| `.tw-chat-status-msg` | System status message (centered) | — |
| `.tw-chat-remark` | Remarks / comment label | — |
| `.tw-select` | Styled select dropdown | Custom arrow SVG |
| `.tw-status-toggle` | Checkbox-based enable/disable toggle | `.toggle-label--disabled` |
| `.tw-filter-card` | Filter form wrapper | — |
| `.tw-confirm-overlay` / `.tw-confirm-box` | Confirm dialog | `.success`, `.danger` icon modifier |
| `.tw-toast` | Bottom-right toast | `.show`, `.tw-toast--success`, `.tw-toast--error` |
| `.tw-filter-btn` / `.tw-filter-dropdown` | Dashboard filter pill + dropdown | `.active` on dropdown |
| `.tw-toolbar-btn` | Compact toolbar filter button | `aria-expanded="true"` for active |
| `.tw-notif-bell-wrap` | Bell + dropdown wrapper | — |
| `.tw-notif-item` | Single notification | `.unread` (red left border + bg) |
| `.tw-notif-type-icon` | Circular notification icon | `--success`, `--warning`, `--info`, `--error` |
| `.tw-action-panel` | Slide-up action panel (inside modal) | `.open` = visible |
| `.tw-toggle-group` / `.tw-toggle-btn` | Developer/Tester switch button pair | `.active` state |

---

## 8. TICKET FLOW (CURRENT)

### Lifecycle States (8 Statuses)

```
Submitted (client) → Inbox (admin reviews) → In Progress (dev/tester work)
                                   ↓                       ↕ (Resume / Request Info)
                                Rejected             Awaiting Client
                                                          ↓
                                                       Resolved (dev marks done)
                                                          ↓
                                                        Closed (admin confirms)

From any pre-closed state → Cancelled (client withdraws, portal not built yet)
```

**Status → Sub-status breakdown:**

| Main Status | Sub-statuses | Who Acts |
|------------|-------------|---------|
| **Submitted** | — | Client creates ticket (portal not built yet) |
| **Inbox** | New | Admin reviews and assigns developer (+ optional tester) |
| **In Progress** | Development → Testing → UAT | Developer works; Tester verifies |
| **Awaiting Client** | — | Needs client info; TAT paused; Resume button moves back to In Progress |
| **Resolved** | — | Developer marks work complete; pending admin closure |
| **Closed** | — | Admin confirms resolution |
| **Rejected** | — | Admin declines from Inbox (reason required); DOM row moves to Rejected table |
| **Cancelled** | — | Client withdraws (not yet implemented in portal) |

### Who Does What at Each Stage

| Stage | Actor | Action |
|-------|-------|--------|
| Ticket arrives in Inbox | User/Client | Submits ticket (portal not built yet) |
| Admin reviews new ticket | Admin | Opens `newTicketModal`, selects developer + optional tester, confirms |
| Admin rejects ticket | Admin | Opens `newTicketModal` → "Reject" → `confirmRejection()` moves row to Rejected table |
| Developer works | Developer | Updates sub-status: Development → Testing → UAT (portal not built) |
| Needs client input | Admin | Opens `ticketDetailsModal` → Request Info panel → selects client contact |
| Client responds | Client | Admin clicks Resume button in Awaiting Client row → `resumeTicket()` moves back to In Progress |
| Tester verifies | Tester | Updates to UAT (portal not built) |
| Close ticket | Admin | Opens `ticketDetailsModal` → "Close Ticket" button → confirm modal |
| Reassign | Admin | Opens `ticketDetailsModal` → Reassign panel → new developer/tester |

### Which Modals Handle Which Actions

| Modal / Panel | Trigger | Action |
|--------------|---------|--------|
| `#newTicketModal` | Click Inbox row (`data-ticket-type="new"`) | Assign developer + optional tester; Reject ticket |
| `#ticketDetailsModal` | Click In Progress / Awaiting Client / Closed row | View details; Request Info; Reassign; Close |
| `#dashReassignPanel` | "Reassign" button in details modal header | Change developer or tester assignment |
| `#dashForwardPanel` | "Request Info" button in details modal header | Request client information |
| Resume button (`bx-play-circle`) | Awaiting Client tab row | `resumeTicket()` moves row to In Progress, Development sub-status |
| `#confirmModal` | Assignment / Rejection / Close / Reassign / Forward | Final confirmation before action executes |
| `#chatPanel` | Chat icon in table row OR Chat button in modal | Per-ticket conversation |
| `#timelinePanel` | Timeline icon in table row OR Timeline button in modal | Mini timeline view |
| `#fullTimelineModal` | "View Full Timeline" button in mini panel | Full ticket history |
| `#bulkActionBar` | Checking row checkboxes in any tab | Bulk close/assign/forward/export |

### Data Each Modal Shows / Collects

**New Ticket Modal (Inbox):**
- Shows: Ticket ID, Subject, Issue Date, Priority, Category, Client, Department, Description
- Collects: Developer selection (shows workload: pending/completed/total), optional Tester selection (shown when "Assign tester now" toggle is checked), Comments, Email notification checkbox

**Ticket Details Modal (existing):**
- Shows: All info grid fields (Maker, Issue Date, Priority, Est. Completion, Allottee Date, Category, Client, Department), Stage (sub-status for In Progress), Description, Attachments
- Shows: Overdue warning banner when ticket has passed Est. Completion date
- Conditional: Forwarding Details section (only when `data-status="forwarded"`)
- Conditional: Closure Details section (only when `data-status="closed"`) with Closed By, Closed On, Resolution Time, TAT Status, Resolution Summary
- Collects (Reassign): Reassign type toggle, new assignee select, reason textarea, email checkbox
- Collects (Request Info): Client contact select, reason/message textarea, email checkbox

---

## 9. NAVIGATION ARCHITECTURE

### How the JS Router Works (Standalone Preview)

1. On page load, `base.html` auto-calls `loadPage('admin_portal/dashboard.html')`
2. `fetch()` retrieves the partial HTML file
3. `extractContent(html)` parses the response — if the file has a `<main>` element, returns its `innerHTML`; otherwise returns `<body>` innerHTML (for plain partials)
4. `injectContent(html)` sets `mainContent.innerHTML = html`, then for every `<script>` tag found in the injected HTML, creates a new `<script>` element and replaces the old one — this forces script execution (browser skips scripts set via `innerHTML`)
5. Nav links update active state and call `loadPage(link.dataset.page)`
6. Tab hash support: `loadPage('admin_portal/dashboard.html#inbox')` loads the page, then after 80ms clicks the `[data-tab="inbox"]` button

### How Event Delegation Works in Dashboard

Because the dashboard re-injects page content (including modal and table HTML), all event listeners are added to **static elements** using `querySelectorAll` at script execution time. This works because the partial's scripts run after its HTML is injected.

Row click delegation:
- All `<tbody tr>` in `.tab-content` get click listeners on script init
- Clicks on `.tw-star-icon` or `.tw-row-actions` are stopped from bubbling (so they don't also trigger the row modal)
- Row `data-ticket-type="new"` → opens `newTicketModal`
- Row `data-ticket-type="existing"` → opens `ticketDetailsModal`

### How Modals, Panels, Overlays Are Triggered

| Layer | Triggered by | Dismissed by |
|-------|-------------|-------------|
| Modal overlay (`.tw-modal-overlay`) | `classList.add('active')` | Close button / backdrop click / Escape |
| Action panel (`.tw-action-panel`) | `classList.add('open')` | Panel X button / opening opposing panel / modal close |
| Chat panel (`.tw-chat-panel`) | `classList.add('open')` | Chat close button / Escape |
| Timeline panel (`.tw-timeline-panel`) | `classList.add('open')` | Panel close button / Escape |
| Confirm modal (`.tw-confirm-overlay`) | `classList.add('active')` | Cancel / backdrop / Escape |
| Notification panel (`.tw-notif-panel`) | `classList.add('open')` | Bell click / click-outside |
| Toast (`.tw-toast`) | `appendChild` + `classList.add('show')` after 10ms | Auto-removed after 3s |

### Known Limitations of Standalone Preview

1. **HTTP server required** — `fetch()` fails on `file://`. Always serve via `python -m http.server`.
2. **Scripts re-executed on every page load** — the router rebuilds `<script>` tags. Variables declared with `const`/`let` at the top level of injected scripts will cause `ReferenceError` if the same page is loaded twice (TDZ / redeclaration). All top-level dashboard script variables must use `var`. (See memory: `feedback_script_reinject.md`)
3. **No state persistence** — navigating away from Dashboard loses all modal/tab state
4. **Hardcoded dummy data** — all ticket rows, counts, developer names are static HTML

---

## 10. DJANGO CONVERSION ROADMAP

### Base Template Changes (`base.html`)

```html
<!-- REMOVE: All page CSS preload links (lines 88–97) -->
<!-- CHANGE: Replace the router <script> block with: -->
<!-- {% block page_js %}{% endblock %} -->

<!-- ADD at top: -->
{% load static %}

<!-- CHANGE each static path: -->
href="../static/css/tweedle-tokens.css"
→ href="{% static 'css/tweedle-tokens.css' %}"

<!-- CHANGE body: -->
<body class="role-admin">
→ <body class="role-{% block body_role %}admin{% endblock %}">

<!-- CHANGE title: -->
<title>Tweedle</title>
→ <title>{% block title %}Tweedle{% endblock %}</title>

<!-- CHANGE main content: -->
<main id="main-content"><!-- router fills this --></main>
→ <main id="main-content">{% block content %}{% endblock %}</main>

<!-- ADD after Bootstrap JS: -->
{% block page_js %}{% endblock %}
```

### Each Admin Portal Partial → Django View

Every `admin_portal/*.html` file needs:
1. Remove the `<!-- Django: {% extends 'base.html' %} -->` comment and actually add `{% extends 'base.html' %}`
2. Wrap content in `{% block content %}…{% endblock %}`
3. Add `{% block page_css %}<link rel="stylesheet" href="{% static 'css/pages/….css' %}">{% endblock %}`
4. Wrap page JS in `{% block page_js %}…{% endblock %}`
5. Replace all `<!-- Django: {{ field }} -->` HTML comments with actual `{{ field }}` template variables
6. Replace all `<!-- Django: {% for … %} -->` comments with real for loops
7. Replace `{% url '...' %}` comment references with real URL tags

### Where `{% for %}` Loops Replace Dummy Data

| File | Replace | With |
|------|---------|------|
| `dashboard.html` | Inbox table `<tbody>` rows (×2 static rows) | `{% for ticket in inbox_tickets %}` |
| `dashboard.html` | In Progress table rows (×6 static rows) | `{% for ticket in inprogress_tickets %}` |
| `dashboard.html` | Awaiting Client table rows | `{% for ticket in awaiting_tickets %}` |
| `dashboard.html` | Closed table rows | `{% for ticket in closed_tickets %}` |
| `dashboard.html` | Rejected table rows (×2 static rows) | `{% for ticket in rejected_tickets %}` |
| `dashboard.html` | Notification items | `{% for notification in notifications %}` |
| `dashboard.html` | Company dropdown options | `{% for company in companies %}` |
| `dashboard.html` | Developer select options in newTicketModal | `{% for dev in developers %}` |
| `dashboard.html` | Tester select options in newTicketModal | `{% for tester in testers %}` |
| `dashboard.html` | Client select options | `{% for client in clients %}` |
| `clients.html` | All `<tbody>` rows | `{% for client in clients %}` |
| `team.html` | All `<tbody>` rows | `{% for member in team_members %}` |
| `reports.html` | All `<tbody>` rows | `{% for report in reports %}` |
| `reports.html` | Developer filter options | `{% for dev in developers %}` |
| `reports.html` | Client filter options | `{% for client in clients %}` |
| `settings.html` | Notification preference toggle rows | `{% for pref in notification_preferences %}` |

### Which JS Functions Become API Calls

| Current (frontend only) | Django replacement |
|------------------------|-------------------|
| `confirmAssignment()` → `console.log` | `fetch('{% url "admin:assign_ticket" %}', {method:'POST', body: formData})` |
| `confirmRejection()` → DOM move | `fetch('{% url "admin:reject_ticket" %}', ...)` then DOM move on success |
| `resumeTicket()` → DOM move | `fetch('{% url "admin:resume_ticket" id %}', {method:'POST'})` then DOM move |
| `confirmDashReassign()` → `console.log` | `fetch('{% url "admin:reassign_ticket" id %}', ...)` |
| `confirmDashForward()` → `console.log` | `fetch('{% url "admin:forward_ticket" id %}', ...)` |
| `openCloseTicketConfirm()` → `console.log` | `fetch('{% url "admin:close_ticket" id %}', ...)` |
| `bulkClose()` → DOM remove | `fetch('{% url "admin:bulk_tickets" %}', {method:'POST', body: JSON.stringify({ids:[...], action:'close'})})` |
| `bulkAssign()` → stub | `fetch('{% url "admin:bulk_tickets" %}', {method:'POST', body: JSON.stringify({ids:[...], action:'assign', developer_id:X})})` |
| `submitOnboardForm()` → DOM prepend | `fetch('{% url "admin:onboard_client" %}', {method:'POST', body: formData})` |
| `submitAddMemberForm()` → DOM prepend | `fetch('{% url "admin:add_member" %}', {method:'POST', body: formData})` |
| `saveOrgSettings()` → `console.log` | `fetch('{% url "admin:settings_org" %}', {method:'POST', body: formData})` |
| `saveNotificationSettings()` → `console.log` | `fetch('{% url "admin:settings_notifications" %}', {method:'POST', body: JSON.stringify(toggleStates)})` |
| `saveBrandingSettings()` → `console.log` | `fetch('{% url "admin:settings_branding" %}', {method:'POST', body: formData})` multipart |
| `openFullTimeline()` → fetches HTML file | `fetch('{% url "admin:ticket_timeline_api" id %}')` returning JSON or HTML fragment |
| `sendMessage()` → local DOM append | `fetch('{% url "admin:send_message" %}', {method:'POST', body: formData})` |
| `downloadReport()` → modal only | `window.location.href = "{% url 'admin:report_download' %}?format=pdf&…"` |
| `toggleMemberStatus()` → `console.log` | `fetch('{% url "admin:toggle_member" username %}', {method:'POST'})` |
| Profile dropdown Sign Out | `window.location.href = "{% url 'logout' %}"` |
| Stat counts in HTML | `{{ inbox_count }}`, `{{ inprogress_count }}`, `{{ forwarded_count }}`, `{{ closed_count }}`, `{{ rejected_count }}` from view context |
| Notification count badge | `{% if unread_count %}{{ unread_count }}{% endif %}` |

### Suggested Django App Structure

```
tweedle/
  accounts/           — CustomUser, authentication views, OTP
  admin_portal/       — Admin views (dashboard, clients, team, reports)
  developer_portal/   — Developer views (to be built)
  tester_portal/      — Tester views (to be built)
  client_portal/      — User/Client views (to be built)
  tickets/            — Ticket model, TicketEvent model, assignment logic
  notifications/      — Notification model, WebSocket (future)
  core/               — Base models, mixins, role middleware
```

### Suggested URL Structure

```python
# accounts/
path('login/',              LoginView, name='account_login'),
path('otp-verify/',         OTPVerifyView, name='otp_verify'),
path('otp-resend/',         OTPResendView, name='otp_resend'),
path('logout/',             LogoutView, name='account_logout'),

# admin_portal/
path('admin/dashboard/',    DashboardView, name='admin_dashboard'),
path('admin/clients/',      ClientsView, name='admin_clients'),
path('admin/clients/onboard/', OnboardClientView, name='admin_onboard_client'),
path('admin/team/',         TeamView, name='admin_team'),
path('admin/team/add/',     AddTeamMemberView, name='admin_add_member'),
path('admin/reports/',      ReportsView, name='admin_reports'),
path('admin/notifications/',NotificationsView, name='admin_notifications'),
path('admin/settings/',     SettingsView, name='admin_settings'),
path('admin/settings/org/', OrgSettingsView, name='admin_settings_org'),
path('admin/settings/notifications/', NotifSettingsView, name='admin_settings_notifications'),
path('admin/settings/branding/', BrandingSettingsView, name='admin_settings_branding'),

# admin_portal/ API endpoints
path('api/tickets/<id>/assign/',   AssignTicketView),
path('api/tickets/<id>/reject/',   RejectTicketView),
path('api/tickets/<id>/close/',    CloseTicketView),
path('api/tickets/<id>/reassign/', ReassignTicketView),
path('api/tickets/<id>/forward/',  ForwardTicketView),
path('api/tickets/<id>/resume/',   ResumeTicketView),     # Awaiting Client → In Progress
path('api/tickets/<id>/resolve/',  ResolveTicketView),    # In Progress → Resolved
path('api/tickets/<id>/cancel/',   CancelTicketView),     # Client cancels ticket
path('api/tickets/bulk/',          BulkTicketActionView), # bulk close/assign/forward
path('api/tickets/<id>/timeline/', TicketTimelineView),
path('api/tickets/<id>/messages/', TicketMessagesView),
path('api/reports/download/',      ReportDownloadView),
```

---

## 11. WHAT IS COMPLETE

### Authentication Pages
- [x] Login page — form validation, password toggle, loading state, remember me
- [x] OTP verify page — 6-digit auto-advance, paste handler, countdown timer, resend button
- [x] Google OAuth button (hidden, ready for Phase 3 activation)

### Admin Portal — Shell
- [x] Sidebar — brand, nav links, collapse/expand (desktop), off-canvas (mobile)
- [x] Topbar — hamburger, global ticket search form, notification bell, profile avatar
- [x] Notification bell dropdown — unread badges, "mark all read"
- [x] JS page router — fetch + inject + script re-execution, tab hash support, loader, error state

### Admin Portal — Dashboard
- [x] Stat strip — 5 clickable cards: Inbox / In Progress / Awaiting Client / Closed / Rejected
- [x] Rejected stat card with danger-red styling (`tw-stat-card--rejected`)
- [x] Tab system — 5 tabs: Inbox / In Progress / Awaiting Client / Closed / Rejected with underline active indicator
- [x] Rejected tab with 8-column table (Ticket ID, Subject, Client, Priority, Rejected By, Rejected On, Reason, Actions)
- [x] Tab status bar — dynamic heading and meta text for all 5 tabs
- [x] Filter toolbar — Company dropdown, Date range picker with quick filters, Priority dropdown, table search
- [x] Priority filter dropdown with colored dots (High / Medium / Low / All); `applyPriorityFilter()` filters all 5 tabs
- [x] Table search — live filter with SR feedback
- [x] All 5 ticket tables with dummy data
- [x] Star/favourite toggle per row
- [x] Row attachment chips (PDF, DOC)
- [x] Row action icons — Timeline, Chat, More
- [x] Row click routing — new vs existing ticket type
- [x] Sub-status Stage chip column in In Progress table (Development / Testing / UAT badges)
- [x] `data-sub-status` attribute on all In Progress rows; `openTicketDetailsModal()` accepts 5th param `subStatus`
- [x] Stage info-item shown in ticket details modal for In Progress tickets
- [x] Awaiting Client tab (renamed from "Forwarded") with updated heading and meta text
- [x] Resume button (`bx-play-circle`) in Awaiting Client rows; `resumeTicket()` moves row back to In Progress
- [x] `confirmRejection()` moves row from Inbox to Rejected table via DOM manipulation, updates stat counts
- [x] Overdue badge (`.tw-overdue-badge` red pill) on In Progress rows past `data-est-date`
- [x] `markOverdueRows()` runs on load and on In Progress tab switch
- [x] Overdue warning banner (`#modalOverdueWarning`) in ticket details modal
- [x] Bulk selection checkboxes on all 5 tab tables (header select-all with indeterminate state + per-row)
- [x] `onclick="event.stopPropagation()"` on checkbox cells prevents modal from opening
- [x] `selectedTicketIds` Set persists selection; `updateSelectAllState()` sets indeterminate correctly
- [x] Bulk action bar (`#bulkActionBar`) slides up from bottom with count, Close/Assign/Forward/Export buttons
- [x] `clearBulkSelection()` resets all checkboxes and hides bulk bar

### Modals and Panels
- [x] New Ticket Assignment modal — info grid, description, developer select with workload stats, confirm/reject
- [x] Tester assignment section in `#newTicketModal` — optional, toggle-controlled ("Assign tester now" checkbox)
- [x] `showTesterInfo()` mirrors developer workload stats for tester select
- [x] `confirmAssignment()` validates tester if "Assign tester now" is checked
- [x] Existing Ticket Details modal — full info grid (including Stage for In Progress), description, forwarding section, closure section, attachments
- [x] Overdue warning banner in ticket details modal
- [x] Reassign panel (slide-up inside modal) — developer/tester toggle, assignee select, reason
- [x] Request Info panel (slide-up inside modal, `#dashForwardPanel`) — client select, reason, notify checkbox
- [x] Confirm modal — reusable with dynamic icon/title/message/details, success/danger variants
- [x] Close ticket confirm flow
- [x] Chat panel — message history, attachment preview, send, file attach, email checkbox, auto-resize textarea
- [x] Mini timeline panel — event list, "View Full Timeline" link
- [x] Full timeline modal — fetches timeline page content, scroll-to-top button
- [x] Toast notifications — success and error variants

### Global Search
- [x] Page-header search input with floating result overlay
- [x] Searches across all tabs by ticket ID, subject, client
- [x] Clicking a result activates the correct tab and highlights the row

### Clients Page
- [x] Clients table with avatar, country tag, status badge, actions
- [x] Live search filter
- [x] Full "Onboard New Client" modal form (3 sections: Company Details, Primary Contact, Account Setup)
- [x] `submitOnboardForm()` validates required fields, prepends new row to clients table
- [x] `showClientsToast()` local toast function

### Team Page
- [x] Team members table with role badges, status toggle, view details button
- [x] Live search filter
- [x] Full "Add Developer / Tester" modal form (3 sections: Personal Details, Role & Assignment, Access)
- [x] Role toggle (Developer / Tester) using `tw-toggle-group` pattern; hidden input stores value
- [x] `submitAddMemberForm()` validates, auto-generates initials/username, prepends new row with Pending Invite badge
- [x] `showTeamToast()` local toast function

### Settings Page (new in Phase 12)
- [x] `settings.html` created at `Tweedle/templates/admin_portal/settings.html`
- [x] `settings.css` created at `Tweedle/static/css/pages/settings.css`
- [x] Section 1: Organisation form (name, industry, timezone select, default priority select)
- [x] Section 2: Email Notifications table with 8 events × 2 role columns (Notify Admin / Notify Assignee) = 16 toggles
- [x] Section 3: Portal Branding (logo upload with placeholder box, locked theme color, "Powered by Tweedle" toggle)
- [x] `saveOrgSettings()`, `saveNotificationSettings()`, `saveBrandingSettings()`, `showSettingsToast()`
- [x] Sidebar Settings nav link (`sidebar-nav--bottom`) wired with `data-page="admin_portal/settings.html"`
- [x] `sidebar-nav--bottom` flex fix: `flex: 0 0 auto` so Settings link is always visible

### Reports Page
- [x] Filter form — date range, status, developer, client
- [x] Dynamic summary banner (JS-rendered)
- [x] Report table with TAT badges (met/missed/pending)
- [x] Download PDF / Excel (stub)

### Ticket Timeline Page
- [x] Ticket header card with stats bar (Issue Date, Priority, Close Date, Resolution Time)
- [x] Full vertical timeline with typed event icons

### Global / Base Shell
- [x] Profile dropdown in topbar (`.tw-profile-panel`) with avatar initials, user info, menu items, Sign Out
- [x] `toggleProfileDropdown()` with mutual exclusion (closes notification bell when opening)
- [x] Topbar avatar replaced with `tw-avatar--admin` showing "JJ" initials
- [x] Topbar search form has `id="topbarSearchForm"`, `id="topbarSearchInput"`, submit stub
- [x] Notification bell and confirm modal markup: inline copies kept in original files; component files (`notification-bell.html`, `confirm-modal.html`) hold canonical markup for Django `{% include %}`
- [x] Dev-only banner added to `chat.html`, `ticket-details.html`, `ticket-details-new.html`, `ticket-timeline.html`
- [x] Standalone preview CSS block in `base.html` clearly marked with Django migration comment

### Design System
- [x] Complete CSS token architecture (tweedle-tokens.css)
- [x] 5 role themes (Admin, Developer, Tester, User, Sub-user)
- [x] Full component library (tweedle-components.css)
- [x] `.tw-input` class added with `width: 100%`, padding, border, focus ring (fixes all form field sizing)
- [x] `.tw-profile-wrap`, `.tw-profile-panel`, `.tw-profile-menu-item`, `.tw-profile-divider` added to components
- [x] Dark mode scaffold (body.dark class — not activated)

---

## 12. WHAT IS NOT BUILT YET

### Backend (None exists)
- [ ] Django project scaffolding (apps, models, migrations)
- [ ] All models: CustomUser (with role), Organisation, OrganisationContact, Ticket (8 statuses, 3 sub-statuses), TicketEvent, Notification, ChatMessage, Attachment, OrganisationSettings, NotificationPreference
- [ ] Authentication views (login, logout, OTP)
- [ ] Role middleware (redirects user to correct portal on login based on `request.user.role`)
- [ ] All admin_portal Django views
- [ ] All API endpoints for JS fetch() calls
- [ ] File upload handling (attachments in chat, tickets, and org logo)
- [ ] PostgreSQL setup and configuration
- [ ] Email notification system

### Missing Portal UIs (Not Started)
- [ ] Developer portal — assigned tickets list, sub-status updates (Development → Testing → UAT), chat
- [ ] Tester portal — testing queue, remarks, pass/fail flow
- [ ] User/Client portal — submit ticket form, ticket tracking, chat, UAT response (triggers Resume)
- [ ] Sub-user portal — limited client-side view

### Remaining Stub Features
- [ ] "Manage Users" action on Clients page (button exists, no modal)
- [ ] "View Details" action on Clients page (button exists, no modal)
- [ ] "View Details" action on Team page (button exists, no modal)
- [ ] More options (⋮) row button dropdown on all tables
- [ ] Full notification centre page (`notification.html` has placeholder content only)
- [ ] Pagination for all tables
- [ ] Real-time chat (WebSockets via Django Channels — Phase 2)
- [ ] Push notifications (Phase 2)
- [ ] Google OAuth login button (hidden in `login.html`, ready for Phase 3 activation)
- [ ] Dark mode (scaffold exists via `body.dark` class, not activated)
- [ ] Profile page ("View Profile" menu item logs to console only)
- [ ] Change Password page ("Change Password" menu item logs to console only)

---

## 13. KNOWN ISSUES AND DECISIONS

### Technical Debt / Workarounds

1. **Script re-injection TDZ bug** — When the JS router re-executes injected scripts, `const`/`let` declarations at the top level of a script cause `ReferenceError` if the same page is loaded twice in a session. All dashboard script variables must use `var` at the top level. This is documented in memory: `feedback_script_reinject.md`.

2. **Page CSS preloaded in base.html** — For standalone preview, all 7 page CSS files are loaded upfront in `base.html`. In Django production, these are removed from base.html and each page loads only its own CSS via `{% block page_css %}`. This is clearly marked with a comment in base.html.

3. **Duplicate component markup** — The ticket details modal, chat panel, and timeline panel markup exists in two places: (a) standalone dev view files (`ticket-details.html`, `chat.html`, `ticket-timeline.html`) and (b) inline inside `dashboard.html`. At Django time, the standalone dev files are no longer needed for the admin portal (they were only for isolated development). The canonical versions are the ones in `dashboard.html`.

4. **Confirm modal not extracted to component** — `templates/components/confirm-modal.html` exists but the confirm modal markup is currently inline in `dashboard.html`. At Django time, this should be `{% include 'components/confirm-modal.html' %}`.

5. **Notification bell inline in base.html** — Similarly, the notification bell component is inline in `base.html` rather than using `{% include 'components/notification-bell.html' %}`.

6. **Dummy developer workload data** — Developer stats (pending/completed/total) are hardcoded in `<option data-tickets="5" …>` attributes. Django will provide these from the developer's ticket queryset.

### Design Decisions Made During Build

1. **Single theme token set (4 tokens)** — Decided to make all role theming flow through just 4 CSS variables rather than theming individual components. This keeps themes extremely simple but means every component must use `var(--tw-primary*)` for role color.

2. **Status colors are NOT role-colored** — Inbox/InProgress/Forwarded/Closed use fixed semantic colors (blue/yellow/orange/green) regardless of role. This was a deliberate decision to make status immediately recognisable even in a role with a clashing primary color.

3. **Sub-user amber theme uses dark text on buttons** — Amber (#ecbe25) is too light for white text on primary buttons. Sub-user buttons use `color: var(--tw-primary-text)` (dark brown) at rest and switch to white on hover when the color darkens.

4. **Phase 10 dashboard redesign** — Previous dashboard had large stat tiles with 80×80 icon boxes and a separate filter bar. Phase 10 replaced it with a compact horizontal stat strip (4 flex cards), integrated the filter toolbar inside the table card, and replaced box-style tabs with underline tabs.

5. **JS router approach** — The single-entry-point router (base.html fetches partials) was chosen specifically to avoid having to open 9 separate HTML files during standalone development. It mirrors Django's template inheritance at the browser level.

6. **var at top level in injected scripts** — After encountering TDZ crashes when navigating back to Dashboard (Phase 8/9 debugging), the convention was established that all variables declared at the top level of scripts inside admin portal partials must use `var`, not `const`/`let`.

---

## 14. HOW TO RUN THE PROJECT

### Prerequisites

- Python 3 (for HTTP server)
- A modern browser (Chrome, Firefox, Edge)
- No npm, no build step, no node_modules needed

### Start the Server

```bash
# Navigate to the project ROOT (not the Tweedle/ subdirectory)
cd "path/to/Tweedle-Ticketing-Software"

# Start HTTP server
python -m http.server 8080
```

### Navigation Flow

1. **Open**: `http://localhost:8080/Tweedle/templates/login.html`
2. **Enter anything** in username + password (min 6 chars) → Submit
3. After 1.5s loading state → **redirects to** `http://localhost:8080/Tweedle/templates/base.html`
4. **Dashboard loads automatically** (router runs `loadPage('admin_portal/dashboard.html')`)
5. **Navigate**: Click Clients / Team / Reports in sidebar

### How to Test Each Feature

| Feature | How to Test |
|---------|------------|
| Login validation | Submit empty form; submit password < 6 chars; toggle password visibility |
| OTP verify | `http://localhost:8080/Tweedle/templates/otp-verify.html` — type digits (auto-advance), paste 6-digit number, wait for timer expiry |
| Dashboard tabs | Click stat cards or tab buttons |
| Global search | Type 2+ chars in the page-header search box (not the topbar search) |
| Table filter | Use Company dropdown, Date range picker, or the Filter Tickets input |
| New ticket modal | Click any row in the **Inbox** tab |
| Existing ticket modal | Click any row in **In Progress**, **Forwarded**, or **Closed** tabs |
| Chat panel | Click the chat icon (🗨) in any row, OR the Chat button in a modal header |
| Timeline panel | Click the clock icon (⏱) in any row, OR the Timeline button in a modal header |
| Full timeline | Click "View Full Timeline" inside the mini timeline panel |
| Reassign / Forward | Open an existing ticket modal → click Reassign or Forward in the header |
| Close ticket | Open any non-closed ticket → click "Close Ticket" in the modal footer |
| Clients page | Click Clients in sidebar |
| Onboard modal | Click "Onboard New Client" on the Clients page |
| Team page | Click Team in sidebar; test status toggles |
| Reports page | Click Reports in sidebar; click "Show Report"; click download buttons |
| Notification bell | Click the bell icon in the topbar; click "Mark all read" |
| OTP full preview | Open `http://localhost:8080/Tweedle/templates/otp-verify.html` directly |
| Chat page standalone | Open `http://localhost:8080/Tweedle/templates/admin_portal/chat.html` directly |
| Timeline standalone | Open `http://localhost:8080/Tweedle/templates/admin_portal/ticket-timeline.html` directly |

---

## 15. CONTEXT FOR AI HANDOFF

**This is a copy-paste summary for priming any AI assistant:**

---

Tweedle is a multi-role B2B ticketing SaaS — **currently a pure frontend, no backend**. The entire codebase is plain HTML/CSS/JS, Django-ready but not yet connected to Django. All templates have `<!-- Django: … -->` comments showing exactly where to add template tags.

**What's built:** The complete Admin Portal UI across 6 pages — login, OTP verify, dashboard (5 stat cards, 5 tab tables, all modals and panels), clients (full onboard form), team (full add-member form with role toggle), reports (TAT table, download stubs), notifications (placeholder), settings (org form, notification toggles, branding). Full CSS design system.

**Ticket statuses (8 total):** Submitted → Inbox → In Progress (sub-statuses: Development / Testing / UAT) → Awaiting Client ↔ In Progress (Resume button). From In Progress → Resolved → Closed. Branch paths: Inbox → Rejected (with reason, DOM move), any pre-closed → Cancelled (not yet in UI).

**Tech stack:** HTML5 + CSS3 (custom token system) + Vanilla JS + Bootstrap 5 + Boxicons + Google Fonts. Planned backend: Django + PostgreSQL + DRF. No build system, no npm.

**Architecture decisions:**
- 5-file CSS load order: tokens → theme → base → components → page CSS
- Role theming via 4 CSS custom properties (`--tw-primary*`) — swap theme file, entire UI recolors
- Admin = Blue #3C91E6 | Developer = Purple | Tester = Teal | User = Orange | Sub-user = Amber
- `base.html` is the single entry point with a JS page router that fetches admin_portal partials via `fetch()` — **requires HTTP server, not file://**
- Top-level script variables in injected partials must use `var` not `const`/`let` to avoid TDZ crashes on re-navigation
- **Critical**: Notification bell and confirm modal markup must remain **inline** in `base.html` and `dashboard.html` respectively for the standalone router. Component files (`notification-bell.html`, `confirm-modal.html`) hold canonical markup for Django `{% include %}` at deploy time only.

**Key file locations:**
- Shell: `Tweedle/templates/base.html`
- Main page: `Tweedle/templates/admin_portal/dashboard.html` (3000+ lines — all interactions here)
- Settings page: `Tweedle/templates/admin_portal/settings.html` (new in Phase 12)
- Design tokens: `Tweedle/static/css/tweedle-tokens.css`
- All components: `Tweedle/static/css/tweedle-components.css` (`.tw-input` width:100% fix included)
- Run: `python -m http.server 8080` from project root, open `Tweedle/templates/login.html`

**Django build order (recommended):**
1. `accounts` app — CustomUser model (with `role` field), login, OTP, role middleware (redirects to correct portal)
2. `organisations` app — Organisation, OrganisationContact, OrganisationSettings models
3. `tickets` app — Ticket (8 statuses, 3 sub-statuses), TicketEvent models
4. `admin_portal` app — wire all 6 existing templates to Django views, replace dummy data with context vars and `{% for %}` loops, wire all `console.log` stubs to real `fetch()` calls
5. `notifications` app — Notification model, real-time count badge
6. `client_portal` app — submit ticket, track, UAT response, chat
7. `developer_portal` app — assigned ticket queue, sub-status updates, chat
8. `tester_portal` app — testing queue, pass/fail flow
9. WebSockets via Django Channels (Phase 2 — real-time chat and notifications)
10. Google OAuth (Phase 3 — button already hidden in `login.html`)
