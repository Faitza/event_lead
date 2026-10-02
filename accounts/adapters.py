from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class AccountAdapter(DefaultAccountAdapter):
    def get_login_redirect_url(self, request):
        from .views import post_login_url_for

        return post_login_url_for(request.user)

    def populate_username(self, request, user):
        if not user.username:
            user.username = (user.email or "").lower()[:150] or None
        if not user.username:
            super().populate_username(request, user)


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """Un nouvel utilisateur Google recoit le role invite par defaut."""

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        user.role = "guest"
        if user.email and not user.username:
            user.username = user.email.lower()[:150]
        return user
