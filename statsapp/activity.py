from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed

from .models import UserActivity


def _get_inactivity_limit():
    value = getattr(settings, 'INACTIVITY_TIMEOUT', None)
    if value in (None, False, 0):
        return None
    if isinstance(value, (int, float)):
        return timedelta(seconds=value)
    return value


def touch_user_activity(user, *, enforce_timeout=False):
    """
    Update the user's last_activity timestamp.
    When enforce_timeout is True, the function raises AuthenticationFailed if
    the stored timestamp is older than the inactivity limit.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return

    now = timezone.now()
    activity, _ = UserActivity.objects.get_or_create(user=user, defaults={'last_activity': now})
    limit = _get_inactivity_limit()

    if enforce_timeout and limit and activity.last_activity and now - activity.last_activity > limit:
        raise AuthenticationFailed('Sesión expirada por inactividad')

    if activity.last_activity != now:
        activity.last_activity = now
        activity.save(update_fields=['last_activity'])
