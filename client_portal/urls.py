from django.urls import path

from .views import ClientDashboardView

# Flat names — the client templates use `client_dashboard` etc.
urlpatterns = [
    path("", ClientDashboardView.as_view(), name="client_dashboard"),
]
