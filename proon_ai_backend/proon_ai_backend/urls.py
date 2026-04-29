from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import render

from authapp.views import FacebookLogin, GoogleLogin

def social_login_success(request):
    return render(request, 'authapp/social_login_success.html')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/', include('authapp.urls')),
    path('api/', include('api.urls')),
    path('adminapi/', include('adminapp.urls')),
    path('accounts/profile/', social_login_success),
    # path('accounts/google/login/', GoogleLogin.as_view(), name='google_login_api'),
    # path('accounts/facebook/login/', FacebookLogin.as_view(), name='facebook_login_api'),
    path('accounts/', include('allauth.urls')),           # ← This creates the callback URL
    path('dj-rest-auth/', include('dj_rest_auth.urls')),
    path('dj-rest-auth/registration/', include('dj_rest_auth.registration.urls')),
    path('dj-rest-auth/facebook/', FacebookLogin.as_view(), name='fb_login'),
]

# In development: Django serves both static and media files directly.
# In production: configure nginx (or your platform) to serve MEDIA_ROOT at /media/.
# Whitenoise only handles STATIC files, not MEDIA — this is a common gotcha.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
