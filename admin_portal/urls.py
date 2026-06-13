from django.urls import path

from . import views
from .views import AdminDashboardView

# Flat (un-namespaced) names — the admin templates use `admin_dashboard` etc.,
# and the `admin:` namespace is already taken by Django's built-in admin site.
urlpatterns = [
    path("", AdminDashboardView.as_view(), name="admin_dashboard"),
    path(
        "ticket/<int:pk>/transition/",
        views.ticket_transition,
        name="ticket_transition",
    ),
    path(
        "ticket/<int:pk>/detail/",
        views.admin_ticket_detail,
        name="admin_ticket_detail",
    ),
    path(
        "ticket/<int:pk>/timeline/",
        views.admin_ticket_timeline,
        name="admin_ticket_timeline",
    ),
    path(
        "ticket/<int:pk>/chat/",
        views.admin_ticket_chat,
        name="admin_ticket_chat",
    ),
]
