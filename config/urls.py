"""URL configuration for config project."""

from django.contrib import admin
from django.urls import include, path

from core import views as core_views

urlpatterns = [
    path('admin/', admin.site.urls),

    # Bare root: anonymous -> login; authenticated -> role redirect hub.
    path('', core_views.root, name='root'),

    # Authentication (django-allauth) + the post-login role redirect hub.
    path('accounts/', include('allauth.urls')),
    path('portal/', core_views.post_login_redirect, name='post_login_redirect'),

    # Per-portal landing pages (Phase 3a placeholders).
    path('admin-portal/', include('admin_portal.urls')),
    path('client/', include('client_portal.urls')),
    path('developer/', include('developer_portal.urls')),
    path('tester/', include('tester_portal.urls')),
    path('subuser/', include('subuser_portal.urls')),
    path('notifications/', include('notifications.urls')),
]
