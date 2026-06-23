from django.urls import path

from .views import (
    TesterDashboardView,
    tester_post_message,
    tester_ticket_detail,
    tester_ticket_transition,
)

app_name = "tester"

urlpatterns = [
    path("",                              TesterDashboardView.as_view(),  name="dashboard"),
    path("tickets/<int:pk>/",            tester_ticket_detail,           name="ticket_detail"),
    path("tickets/<int:pk>/transition/", tester_ticket_transition,        name="ticket_transition"),
    path("tickets/<int:pk>/message/",    tester_post_message,            name="post_message"),
]
