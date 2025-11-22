from rest_framework_simplejwt.authentication import JWTAuthentication

from .activity import touch_user_activity


class InactivityJWTAuthentication(JWTAuthentication):
    """
    Extends the default JWT authentication to enforce inactivity timeouts.
    """

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user, token = result
        touch_user_activity(user, enforce_timeout=True)
        return (user, token)
