from django.urls import path

from .views import (
    ClientDashboardView,
    client_submit_ticket,
    client_ticket_detail,
    client_ticket_transition,
)

urlpatterns = [
    path("", ClientDashboardView.as_view(), name="client_dashboard"),
    path("submit/", client_submit_ticket, name="client_submit_ticket"),
    path("ticket/<int:pk>/", client_ticket_detail, name="client_ticket_detail"),
    path("ticket/<int:pk>/action/", client_ticket_transition, name="client_ticket_transition"),
]
