# Tweedle — Multi-Role Ticketing Software

A professional B2B ticketing and support management platform 
built for teams that need structured ticket flow, role-based 
access, and real-time collaboration.

---

## Overview

Tweedle is a full-stack ticketing SaaS designed for organisations 
managing support operations across multiple clients, developers, 
and testers. Each role has a distinct interface and color identity 
so users instantly recognise their workspace.

---

## Role System

| Role | Access |
|------|--------|
| **Admin** | Full control — tickets, team, clients, reports |
| **Developer** | Assigned tickets, chat, status updates |
| **Tester** |  Testing tickets, remarks, verification |
| **User / Client** | Submit and track own tickets |
| **Sub-user** | Limited access under a client account |

---

## Features

### Ticket Management
- Ticket flow: New → In Progress → Awaiting Client → UAT → Resolved → Closed (or Rejected / Cancelled)
- Sub-status tracking: New → Development → Testing → UAT
- Priority levels: High / Medium / Low
- TAT (Turn Around Time) tracking per ticket
- Ticket assignment with developer workload stats
- Reject / close with confirmation modal

### Communication
- Per-ticket real-time chat panel
- Role-identified message bubbles
- File attachments in chat (PDF, DOC, images)
- Email notification toggle per message
- Remarks / comment labels
- Status messages in chat timeline

### Ticket Timeline
- Full lifecycle view per ticket
- Vertical timeline with event types and actor roles
- Priority, date, resolution stats bar

### Admin Portal
- Dashboard with stat tiles (Inbox / In Progress / Awaiting Client / UAT / Resolved / Closed / Rejected / Cancelled)
- Client management — onboard, manage users, status
- Team management — add developers and testers, enable/disable
- Reports — filter by date, status, developer, client
- PDF and Excel export
- TAT met / missed / pending reporting

### Notifications
- Real-time notification bell with unread badge
- Typed notifications: new message, ticket assigned, ticket closed
- Mark all read, view all, per-item read state

### Authentication
- Single login page — role-neutral, clean enterprise design
- Auto-redirect to role dashboard after login
- OTP verification page (Phase 2 — stub ready)
- Google OAuth button (Phase 3 — stub ready)
- Client-side form validation, password toggle, loading state

---

## Tech Stack

### Frontend (Current)
- HTML5 — semantic, Django-template-ready
- CSS3 — custom design system with CSS variables
- Vanilla JavaScript — no frameworks, well-commented
- Bootstrap 5 — grid and responsive utilities
- Boxicons — icon library
- Google Fonts — Poppins (primary) + Lato (secondary)

### Backend (Built — through Phase 4.18)
- Python Django 5.2 LTS — web framework (server-rendered; DRF not used)
- PostgreSQL — primary database (SQLite fallback for local dev)
- django-allauth — authentication (signup closed; admin-provisioned)
- Guarded transition engine — every ticket state change flows through one audited `transition()` service
- All five portals wired end-to-end; admin ticket lifecycle complete (286 tests green)
- Django REST Framework — not built (deferred; server-rendered form-POST is the target)
- django-otp — two-factor authentication (Phase 3b — deferred)

---

*Built with care. Designed to feel human.*
