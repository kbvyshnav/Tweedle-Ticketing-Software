from django.urls import path

from .views import SubuserDashboardView

# Namespaced as `subuser` — the sub-user templates use `subuser:dashboard` etc.
app_name = "subuser"

urlpatterns = [
    path("", SubuserDashboardView.as_view(), name="dashboard"),
]
