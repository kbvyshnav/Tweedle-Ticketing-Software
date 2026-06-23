from django.urls import path

from .views import (
    DeveloperDashboardView,
    dev_post_message,
    dev_ticket_detail,
    dev_ticket_transition,
)

# Namespaced as `dev` — templates use `dev:dashboard`, `dev:ticket_detail`, etc.
app_name = "dev"

urlpatterns = [
    path("", DeveloperDashboardView.as_view(), name="dashboard"),
    path("tickets/<int:pk>/", dev_ticket_detail, name="ticket_detail"),
    path("tickets/<int:pk>/transition/", dev_ticket_transition, name="ticket_transition"),
    path("tickets/<int:pk>/message/", dev_post_message, name="post_message"),
]
