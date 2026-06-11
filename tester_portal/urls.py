from django.urls import path

from .views import TesterDashboardView

# Namespaced as `tester` — the tester templates use `tester:dashboard` etc.
app_name = "tester"

urlpatterns = [
    path("", TesterDashboardView.as_view(), name="dashboard"),
]
