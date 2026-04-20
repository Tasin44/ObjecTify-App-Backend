# views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
import random
import string
from .serializers import (
    SignupSerializer, VerifyOTPSerializer, ResendOTPSerializer,
    LoginSerializer, ForgotPasswordSerializer, ResetPasswordSerializer,
    UserProfileSerializer,
    PersonalizationSerializer,
)
from .models import OTP, Personalization
from dj_rest_auth.serializers import JWTSerializer   # ← Correct import
User = get_user_model()
from rest_framework import status

class StandardResponseMixin:
    """Mixin for consistent API responses"""
    def success_response(self, data, message="Success", status_code=200):
        return Response({
            "success": True,
            "statusCode": status_code,
            "message": message,
            "data": data,
            "timestamp": timezone.now().isoformat()
        }, status=status_code)
    
    def error_response(self, message, status_code=400, data=None):
        return Response({
            "success": False,
            "statusCode": status_code,
            "message": message,
            "data": data,
            "timestamp": timezone.now().isoformat()
        }, status=status_code)

def extract_first_error(errors):
    """Extract the first error message from serializer errors dict"""
    for field, messages in errors.items():
        if isinstance(messages, list) and messages:
             return f"{field}: {messages[0]}"
        elif isinstance(messages, str):
            return messages
    return ""


class SignupView(StandardResponseMixin, APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        # print("hello!")
        serializer = SignupSerializer(data=request.data)
        print("hello!")
        if serializer.is_valid():
            user = serializer.save()
            
            return self.success_response(
                {"email": user.email},
                message="User created. OTP sent to email.",
                status_code=201
            )
        reason = extract_first_error(serializer.errors)
        return self.error_response(
            f"Signup failed: {reason}",
            status_code=400,
            data=serializer.errors
        )


class VerifyOTPView(StandardResponseMixin, APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        if serializer.is_valid():
            otp = serializer.validated_data['otp']
            user = User.objects.get(email=otp.email)
            
            user.verified = True
            user.save(update_fields=['verified', 'updated_at'])
            
            otp.is_used = True
            otp.save(update_fields=['is_used'])
            
            refresh = RefreshToken.for_user(user)
            return self.success_response(
                {
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                    "user": {
                        "id": str(user.id),
                        "email": user.email,
                        # "name": user.first_name
                    }
                },
                message="Email verified successfully.",
                status_code=200
            )
        reason = extract_first_error(serializer.errors)
        return self.error_response(
            f"Verification failed: {reason}",
            status_code=400,
            data=serializer.errors
        )


class ResendOTPView(StandardResponseMixin, APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = ResendOTPSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            
            otp_code = ''.join(random.choices(string.digits, k=6))
            expires_at = timezone.now() + timedelta(minutes=10)
            
            OTP.objects.filter(email=email, is_used=False).delete()
            OTP.objects.create(
                email=email,
                otp_code=otp_code,
                expires_at=expires_at
            )
            
            SignupSerializer.send_otp_email(email, otp_code)
            
            return self.success_response(
                {"email": email},
                message="OTP sent to email.",
                status_code=200
            )
        reason = extract_first_error(serializer.errors)
        return self.error_response(
            f"Resend OTP Failed: {reason}",
            status_code=400,
            data=serializer.errors
        )


class LoginView(StandardResponseMixin, APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            refresh = RefreshToken.for_user(user)
            
            return self.success_response(
                {
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                    "user": {
                        "id": str(user.id),
                        "email": user.email,
                        # "name": user.first_name
                    }
                },
                message="Login successful.",
                status_code=200
            )
        reason = extract_first_error(serializer.errors)
        return self.error_response(
             f"Login failed: {reason}",
            status_code=401,
            data=serializer.errors
        )

'''
class LogoutView(StandardResponseMixin, APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        return self.success_response(
            {},
            message="Logout successful.",
            status_code=200
        )
# Issue:
# This doesn’t invalidate the refresh token.
# Anyone holding the refresh token can still get a new access token.
'''
class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            print("Request data:", request.data)
            if not refresh_token:
                return Response(
                    {f"detail": "Refresh token is required.{refresh_token}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            token = RefreshToken(refresh_token)
            token.blacklist()

            return Response({"message": "Logout successful."}, status=status.HTTP_200_OK)
        except TokenError:
            return Response({"detail": "Invalid or expired token."}, status=status.HTTP_400_BAD_REQUEST)


class ForgotPasswordView(StandardResponseMixin, APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            
            otp_code = ''.join(random.choices(string.digits, k=6))
            expires_at = timezone.now() + timedelta(minutes=10)
            
            OTP.objects.filter(email=email, is_used=False).delete()
            OTP.objects.create(
                email=email,
                otp_code=otp_code,
                expires_at=expires_at
            )
            
            SignupSerializer.send_otp_email(email, otp_code)
            
            return self.success_response(
                {"email": email},
                message="OTP sent to email for password reset.",
                status_code=200
            )
        reason = extract_first_error(serializer.errors)
        return self.error_response(
           f"Forgot password failed:{reason}",
            status_code=400,
            data=serializer.errors
        )


class ResetPasswordView(StandardResponseMixin, APIView):
    permission_classes = [IsAuthenticated]  # user must be logged in via OTP verify token
    authentication_classes = [JWTAuthentication]

    '''
    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        if serializer.is_valid():
            otp = serializer.validated_data['otp']
            email = serializer.validated_data['email']
            new_password = serializer.validated_data['new_password']
            
            user = User.objects.get(email=email)
            user.set_password(new_password)
            user.save(update_fields=['password', 'updated_at'])
            
            otp.is_used = True
            otp.save(update_fields=['is_used'])
            
            return self.success_response(
                {},
                message="Password reset successful.",
                status_code=200
            )
        return self.error_response(
            "Password reset failed",
            status_code=400,
            data=serializer.errors
        )
    
    '''
    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user  # authenticated via token from VerifyOTPView
            new_password = serializer.validated_data['new_password']

            user.set_password(new_password)
            user.save(update_fields=['password', 'updated_at'])

            return self.success_response(
                {},
                message="Password reset successful.",
                status_code=200
            )
        reason = extract_first_error(serializer.errors)
        return self.error_response(
            f"Password reset failed:{reason}",
            status_code=400,
            data=serializer.errors
        )


class ProfileView(StandardResponseMixin, APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        serializer = UserProfileSerializer(request.user, context={'request': request})
        return self.success_response(serializer.data, message="Profile fetched.", status_code=200)

    def patch(self, request):
        serializer = UserProfileSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={'request': request},
        )
        if serializer.is_valid():
            serializer.save()
            return self.success_response(serializer.data, message="Profile updated.", status_code=200)

        reason = extract_first_error(serializer.errors)
        return self.error_response(
            f"Profile update failed: {reason}",
            status_code=400,
            data=serializer.errors,
        )


class PersonalizationView(StandardResponseMixin, APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        try:
            personalization = request.user.personalization
        except Personalization.DoesNotExist:
            return self.error_response("Personalization not found.", status_code=404)

        serializer = PersonalizationSerializer(personalization)
        return self.success_response(serializer.data, message="Personalization fetched.", status_code=200)

    def post(self, request):
        existing = Personalization.objects.filter(user=request.user).first()
        serializer = PersonalizationSerializer(existing, data=request.data, partial=bool(existing))
        if serializer.is_valid():
            personalization = serializer.save(user=request.user)
            response_serializer = PersonalizationSerializer(personalization)
            message = "Personalization updated." if existing else "Personalization saved."
            return self.success_response(response_serializer.data, message=message, status_code=200)

        reason = extract_first_error(serializer.errors)
        return self.error_response(
            f"Personalization save failed: {reason}",
            status_code=400,
            data=serializer.errors,
        )
    

from dj_rest_auth.registration.views import SocialLoginView
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from django.conf import settings

class GoogleLogin(SocialLoginView):
    adapter_class = GoogleOAuth2Adapter
    client_class = OAuth2Client
    callback_url = "https://6zpmb4x8-8030.inc1.devtunnels.ms/accounts/google/login/callback/"   # your tunnel URL
    

from allauth.socialaccount.providers.facebook.views import FacebookOAuth2Adapter
from dj_rest_auth.registration.views import SocialLoginView

class FacebookLogin(SocialLoginView):
    adapter_class = FacebookOAuth2Adapter
    client_class = OAuth2Client
    callback_url = "https://6zpmb4x8-8030.inc1.devtunnels.ms/accounts/facebook/login/callback/"#with devtunnel it's safer to add it explicitly (same as your Google login).
    # Add these two lines
    #serializer_class = JWTSerializer
    authentication_classes = []        # Important for social login
    '''
    Just remove serializer_class entirely — 
    SocialLoginView handles JWT response automatically when REST_AUTH = {'USE_JWT': True} is set, which you already have in settings.
    The combination of authentication_classes = [] + no serializer_class should work.

   ❌❌ Due to the serializer_class =jwtserializer, I was getting this error 
    {
    "access": [
        "This field is required."
    ],
    "refresh": [
        "This field is required."
    ]
}
    '''