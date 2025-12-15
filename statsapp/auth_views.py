from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .activity import touch_user_activity


User = get_user_model()

# Cookies cross-site: usar SameSite=None en producción para permitir envíos con credenciales.
# En entornos de desarrollo (DEBUG=True) mantenemos Lax para no requerir HTTPS.
REFRESH_COOKIE_SAMESITE = getattr(settings, 'JWT_REFRESH_COOKIE_SAMESITE', 'None' if not settings.DEBUG else 'Lax')


def _user_payload(user):
    return {
        'id': user.id,
        'username': user.get_username(),
        'is_staff': user.is_staff,
        'is_superuser': user.is_superuser,
    }


def _set_refresh_cookie(response, refresh_token):
    max_age = int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds())
    response.set_cookie(
        settings.JWT_REFRESH_COOKIE_NAME,
        refresh_token,
        max_age=max_age,
        httponly=True,
        secure=settings.JWT_COOKIE_SECURE,
        samesite=REFRESH_COOKIE_SAMESITE,
        path='/',
    )


def _clear_refresh_cookie(response):
    response.delete_cookie(
        settings.JWT_REFRESH_COOKIE_NAME,
        path='/',
        samesite=REFRESH_COOKIE_SAMESITE,
        secure=settings.JWT_COOKIE_SECURE,
    )


class StaffTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        if not self.user.is_staff:
            raise AuthenticationFailed('No autorizado', code='authorization')
        touch_user_activity(self.user)
        data['user'] = _user_payload(self.user)
        return data


class CookieTokenObtainPairView(TokenObtainPairView):
    serializer_class = StaffTokenObtainPairSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        refresh = response.data.pop('refresh', None)
        if refresh:
            _set_refresh_cookie(response, refresh)
        return response


class CookieTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        if not attrs.get('refresh'):
            request = self.context['request']
            cookie_refresh = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
            if not cookie_refresh:
                raise AuthenticationFailed('Refresh token missing', code='authorization')
            attrs['refresh'] = cookie_refresh
        data = super().validate(attrs)
        try:
            token = getattr(self, 'token', None) or RefreshToken(attrs['refresh'])
            user_id = token['user_id']
            user = User.objects.get(id=user_id)
        except User.DoesNotExist as exc:
            raise AuthenticationFailed('Usuario no encontrado') from exc
        except Exception as exc:  # Token inválido o sin user_id
            raise AuthenticationFailed('Refresh token inválido') from exc
        touch_user_activity(user, enforce_timeout=True)
        data['user'] = _user_payload(user)
        return data


class CookieTokenRefreshView(TokenRefreshView):
    serializer_class = CookieTokenRefreshSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        refresh = response.data.pop('refresh', None)
        if refresh:
            _set_refresh_cookie(response, refresh)
        return response


class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        response = Response(status=status.HTTP_204_NO_CONTENT)
        _clear_refresh_cookie(response)
        return response


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(_user_payload(request.user))
