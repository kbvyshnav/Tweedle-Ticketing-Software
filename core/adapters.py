from allauth.account.adapter import DefaultAccountAdapter


class NoSignupAccountAdapter(DefaultAccountAdapter):
    """Closes public self-registration.

    Tweedle is admin-provisioned: admins onboard clients/sub-users and create
    internal staff. There is no open signup, so allauth's /accounts/signup/ is
    disabled.
    """

    def is_open_for_signup(self, request):
        return False
