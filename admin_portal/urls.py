from django.urls import path

from .views import AdminDashboardView

# Flat (un-namespaced) names — the admin templates use `admin_dashboard` etc.,
# and the `admin:` namespace is already taken by Django's built-in admin site.
urlpatterns = [
    path("", AdminDashboardView.as_view(), name="admin_dashboard"),
]
