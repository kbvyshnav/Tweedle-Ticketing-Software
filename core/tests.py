from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()

# role -> (landing URL name, the path it resolves to)
ROLE_LANDINGS = {
    "admin": "admin_dashboard",
    "client": "client_dashboard",
    "developer": "dev:dashboard",
    "tester": "tester:dashboard",
    "subuser": "subuser:dashboard",
}


class AuthRoutingTestBase(TestCase):
    PASSWORD = "Sup3r$ecret!pw"

    def make_user(self, username, role):
        return User.objects.create_user(
            username=username,
            email=f"{username}@tweedle.local",
            password=self.PASSWORD,
            role=role,
        )


class PostLoginRedirectTests(AuthRoutingTestBase):
    def test_each_role_routes_to_its_portal(self):
        for role, landing in ROLE_LANDINGS.items():
            with self.subTest(role=role):
                u = self.make_user(f"{role}_user", role)
                self.client.force_login(u)
                resp = self.client.get(reverse("post_login_redirect"))
                self.assertRedirects(
                    resp, reverse(landing), fetch_redirect_response=False
                )
                self.client.logout()

    def test_full_login_flow_redirects_through_hub(self):
        self.make_user("dev_login", "developer")
        resp = self.client.post(
            reverse("account_login"),
            {"login": "dev_login", "password": self.PASSWORD},
        )
        # allauth -> LOGIN_REDIRECT_URL (post_login_redirect) -> dev:dashboard
        self.assertRedirects(
            resp, reverse("post_login_redirect"), fetch_redirect_response=False
        )


class AccessControlTests(AuthRoutingTestBase):
    def test_unauthenticated_portal_access_redirects_to_login(self):
        login_url = reverse("account_login")
        for landing in ROLE_LANDINGS.values():
            with self.subTest(landing=landing):
                url = reverse(landing)
                resp = self.client.get(url)
                self.assertRedirects(
                    resp,
                    f"{login_url}?next={url}",
                    fetch_redirect_response=False,
                )

    def test_wrong_role_is_forbidden(self):
        client_user = self.make_user("c1", "client")
        self.client.force_login(client_user)
        self.assertEqual(
            self.client.get(reverse("admin_dashboard")).status_code, 403
        )
        self.assertEqual(
            self.client.get(reverse("tester:dashboard")).status_code, 403
        )

    def test_right_role_gets_200(self):
        admin = self.make_user("a1", "admin")
        self.client.force_login(admin)
        self.assertEqual(
            self.client.get(reverse("admin_dashboard")).status_code, 200
        )


class LogoutTests(AuthRoutingTestBase):
    def test_logout_clears_session(self):
        u = self.make_user("logout_user", "client")
        self.client.force_login(u)
        # Authenticated: portal is reachable.
        self.assertEqual(
            self.client.get(reverse("client_dashboard")).status_code, 200
        )
        # allauth 65 logout is POST-only.
        self.client.post(reverse("account_logout"))
        self.assertNotIn("_auth_user_id", self.client.session)
        # Now anonymous: portal access redirects to login.
        resp = self.client.get(reverse("client_dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("account_login"), resp.url)


class SignupClosedTests(AuthRoutingTestBase):
    def test_signup_is_closed(self):
        # is_open_for_signup() returns False -> allauth renders its
        # "signup closed" page (HTTP 200, not the signup form).
        resp = self.client.get(reverse("account_signup"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'name="password1"')


class RootUrlTests(AuthRoutingTestBase):
    def test_root_anonymous_redirects_to_login(self):
        resp = self.client.get("/")
        self.assertRedirects(
            resp, reverse("account_login"), fetch_redirect_response=False
        )

    def test_root_authenticated_redirects_to_hub(self):
        u = self.make_user("root_user", "tester")
        self.client.force_login(u)
        resp = self.client.get("/")
        self.assertRedirects(
            resp, reverse("post_login_redirect"), fetch_redirect_response=False
        )
