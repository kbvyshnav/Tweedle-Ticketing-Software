from django.urls import path

from .views import (
    SubuserDashboardView,
    subuser_post_message,
    subuser_submit_ticket,
    subuser_ticket_detail,
    subuser_ticket_transition,
)

app_name = "subuser"

urlpatterns = [
    path("",                              SubuserDashboardView.as_view(), name="dashboard"),
    path("submit/",                       subuser_submit_ticket,           name="submit_ticket"),
    path("tickets/<int:pk>/",            subuser_ticket_detail,           name="ticket_detail"),
    path("tickets/<int:pk>/transition/", subuser_ticket_transition,        name="ticket_transition"),
    path("tickets/<int:pk>/message/",    subuser_post_message,            name="post_message"),
]
