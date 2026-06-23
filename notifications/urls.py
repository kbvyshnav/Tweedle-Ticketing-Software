from django.urls import path

from . import views

urlpatterns = [
    path("", views.notifications_feed, name="notifications_feed"),
    path("<int:pk>/open/", views.notification_open, name="notification_open"),
    path("read-all/", views.mark_all_read, name="notifications_mark_all_read"),
]
