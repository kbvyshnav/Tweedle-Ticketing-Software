from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class ProfileViewTests(TestCase):
    def setUp(self):
        self.url = reverse("profile")
        self.user = User.objects.create_user(
            "dev_p", email="dev_p@tweedle.local", password="OldPass!2026", role="developer",
            first_name="Dev", last_name="One",
        )

    def test_requires_login(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp.url)

    def test_get_renders_with_role_base(self):
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "accounts/profile.html")
        self.assertEqual(resp.context["base_template"], "developer_base.html")

    def test_admin_gets_admin_base(self):
        admin = User.objects.create_user(
            "admin_p", email="admin_p@tweedle.local", password="pw", role="admin"
        )
        self.client.force_login(admin)
        resp = self.client.get(self.url)
        self.assertEqual(resp.context["base_template"], "base.html")

    # ── Profile section ──────────────────────────────────────
    def test_update_profile(self):
        self.client.force_login(self.user)
        resp = self.client.post(self.url, {
            "section": "profile", "first_name": "Devon", "last_name": "Two",
            "email": "devon@tweedle.local",
        })
        self.assertRedirects(resp, self.url)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Devon")
        self.assertEqual(self.user.email, "devon@tweedle.local")

    def test_duplicate_email_rejected(self):
        User.objects.create_user(
            "other", email="taken@tweedle.local", password="pw", role="tester"
        )
        self.client.force_login(self.user)
        resp = self.client.post(self.url, {
            "section": "profile", "first_name": "Dev", "last_name": "One",
            "email": "taken@tweedle.local",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "already in use")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "dev_p@tweedle.local")  # unchanged

    def test_email_required(self):
        self.client.force_login(self.user)
        resp = self.client.post(self.url, {
            "section": "profile", "first_name": "Dev", "last_name": "One", "email": "",
        })
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "dev_p@tweedle.local")

    # ── Password section ─────────────────────────────────────
    def test_change_password_success_keeps_session(self):
        self.client.force_login(self.user)
        resp = self.client.post(self.url, {
            "section": "password", "old_password": "OldPass!2026",
            "new_password1": "BrandNew!2026", "new_password2": "BrandNew!2026",
        })
        self.assertRedirects(resp, self.url)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("BrandNew!2026"))
        # Session preserved (update_session_auth_hash) — still authenticated.
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_change_password_wrong_old(self):
        self.client.force_login(self.user)
        resp = self.client.post(self.url, {
            "section": "password", "old_password": "WrongOld!2026",
            "new_password1": "BrandNew!2026", "new_password2": "BrandNew!2026",
        })
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("OldPass!2026"))  # unchanged

    def test_change_password_mismatch(self):
        self.client.force_login(self.user)
        resp = self.client.post(self.url, {
            "section": "password", "old_password": "OldPass!2026",
            "new_password1": "BrandNew!2026", "new_password2": "Different!2026",
        })
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("OldPass!2026"))  # unchanged
