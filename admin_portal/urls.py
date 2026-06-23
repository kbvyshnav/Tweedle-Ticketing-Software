from django.urls import path

from . import views
from .views import AdminDashboardView

# Flat (un-namespaced) names — the admin templates use `admin_dashboard` etc.,
# and the `admin:` namespace is already taken by Django's built-in admin site.
urlpatterns = [
    path("", AdminDashboardView.as_view(), name="admin_dashboard"),
    path("clients/", views.admin_clients, name="admin_clients"),
    path("clients/onboard/", views.admin_onboard_client, name="admin_onboard_client"),
    path("clients/<str:code>/detail/", views.admin_client_detail, name="admin_client_detail"),
    path("clients/<str:code>/settings/", views.admin_client_settings, name="admin_client_settings"),
    path("clients/<str:code>/users/", views.admin_client_users, name="admin_client_users"),
    path("clients/<str:code>/users/add/", views.admin_add_client_user, name="admin_add_client_user"),
    path("client-user/<int:pk>/toggle/", views.admin_toggle_client_user, name="admin_toggle_client_user"),
    path("team/", views.admin_team, name="admin_team"),
    path("team/add/", views.admin_add_team_member, name="admin_add_team_member"),
    path(
        "team/<int:pk>/toggle/",
        views.admin_toggle_team_member,
        name="admin_toggle_team_member",
    ),
    path("reports/", views.admin_reports, name="admin_reports"),
    path("settings/", views.admin_settings, name="admin_settings"),
    path("search/", views.admin_search, name="admin_search"),
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
    path(
        "ticket/<int:pk>/message/",
        views.admin_post_message,
        name="admin_post_message",
    ),
]
