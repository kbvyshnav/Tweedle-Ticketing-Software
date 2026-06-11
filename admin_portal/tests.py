from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class AdminDashboardTemplateTests(TestCase):
    def setUp(self):
        self.url = reverse("admin_dashboard")
        self.admin = User.objects.create_user(
            "admin_t", email="admin_t@tweedle.local", password="pw", role="admin"
        )
        self.client_user = User.objects.create_user(
            "client_t", email="client_t@tweedle.local", password="pw", role="client"
        )

    def test_admin_gets_200_and_uses_templates(self):
        self.client.force_login(self.admin)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "admin_portal/dashboard.html")
        self.assertTemplateUsed(resp, "base.html")

    def test_non_admin_forbidden(self):
        self.client.force_login(self.client_user)
        self.assertEqual(self.client.get(self.url).status_code, 403)
