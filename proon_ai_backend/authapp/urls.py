from django.urls import path
from .views import (
    SignupView, VerifyOTPView, ResendOTPView, LoginView,
    LogoutView, ForgotPasswordView, ResetPasswordView, ProfileView,
    PersonalizationView,GoogleLogin,FacebookLogin,ResetPasswordPageView
)

urlpatterns = [
    path('signup/', SignupView.as_view(), name='signup'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('resend-otp/', ResendOTPView.as_view(), name='resend-otp'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('forgot-password/', ForgotPasswordView.as_view(), name='forgot-password'),
    path('reset-password/', ResetPasswordView.as_view(), name='reset-password'),
    path('<str:uid>/<str:token>/', ResetPasswordPageView.as_view(), name='reset-password-page'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('personalization/', PersonalizationView.as_view(), name='personalization'),
    path('google/', GoogleLogin.as_view(), name='google_login'),

    path('facebook/', FacebookLogin.as_view(), name='fb_login'),
]