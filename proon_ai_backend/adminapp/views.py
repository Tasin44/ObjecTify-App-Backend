from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from api.models import ScanHistory
from authapp.models import User

from .models import UserSubscription
from .serializers import (
    AdminDashboardSerializer,
    AdminScanSerializer,
    AdminSubscriptionSerializer,
    AdminUserSerializer,
    AdminUserUpdateSerializer,
)


def _ensure_subscriptions_for_all_users():
    existing_user_ids = set(UserSubscription.objects.values_list('user_id', flat=True))
    missing_users = User.objects.exclude(id__in=existing_user_ids)
    UserSubscription.objects.bulk_create(
        [UserSubscription(user=user) for user in missing_users],
        ignore_conflicts=True,
    )


@api_view(['GET'])
@permission_classes([IsAdminUser])
def dashboard_summary(request):
    _ensure_subscriptions_for_all_users()

    payload = {
        'total_users': User.objects.count(),
        'total_active_users': User.objects.filter(is_active=True).count(),
        'total_subscribers': UserSubscription.objects.filter(status=UserSubscription.STATUS_ACTIVE).count(),
        'total_scans': ScanHistory.objects.count(),
    }
    serializer = AdminDashboardSerializer(payload)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def users_list(request):
    _ensure_subscriptions_for_all_users()

    users = User.objects.select_related('admin_subscription').annotate(total_scan=Count('scans')).order_by('-date_joined')
    serializer = AdminUserSerializer(users, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['PATCH'])
@permission_classes([IsAdminUser])
def user_edit(request, user_id):
    user = get_object_or_404(User.objects.select_related('admin_subscription'), id=user_id)
    subscription, _ = UserSubscription.objects.get_or_create(user=user)

    serializer = AdminUserUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    username = serializer.validated_data.get('username')
    subscription_plan = serializer.validated_data.get('subscription_plan')

    if username is not None:
        user.username = username
        user.save(update_fields=['username'])

    if subscription_plan is not None:
        subscription.plan = subscription_plan
        subscription.save(update_fields=['plan'])

    refreshed = User.objects.select_related('admin_subscription').annotate(total_scan=Count('scans')).get(id=user.id)
    return Response(AdminUserSerializer(refreshed).data, status=status.HTTP_200_OK)


@api_view(['DELETE'])
@permission_classes([IsAdminUser])
def user_remove(request, user_id):
    user = get_object_or_404(User, id=user_id)
    user.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def scans_list(request):
    scans = ScanHistory.objects.select_related('user').all().order_by('-created_at')
    serializer = AdminScanSerializer(scans, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def subscriptions_list(request):
    _ensure_subscriptions_for_all_users()

    subscriptions = UserSubscription.objects.select_related('user').all().order_by('-created_at')
    serializer = AdminSubscriptionSerializer(subscriptions, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)
