from django.urls import path

from .views import DeveloperDashboardView

# Namespaced as `dev` — the developer templates use `dev:dashboard` etc.
app_name = "dev"

urlpatterns = [
    path("", DeveloperDashboardView.as_view(), name="dashboard"),
]
