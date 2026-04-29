from datetime import timedelta

from django.db.models import Count
from django.db.models.functions import ExtractHour, TruncDate
from django.utils import timezone
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
    AdminTodayScanBucketsSerializer,
    AdminUserSerializer,
    AdminUserUpdateSerializer,
    AdminLast7DaysSerializer,
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


@api_view(['GET'])
@permission_classes([IsAdminUser])
def weekend_scans_by_week(request):
    today = timezone.localdate()
    start_date = today - timedelta(days=6)

    date_counts = (
        ScanHistory.objects.filter(created_at__date__range=(start_date, today))
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(total=Count('id'))
    )
    counts_by_date = {item['day']: item['total'] for item in date_counts}

    days = []
    for day_offset in range(7):
        day = start_date + timedelta(days=day_offset)
        days.append({'date': day, 'count': counts_by_date.get(day, 0)})

    payload = {
        'start_date': start_date,
        'end_date': today,
        'days': days,
    }

    serializer = AdminLast7DaysSerializer(payload)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def today_scans_by_three_hours(request):
    now = timezone.localtime()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    hourly_counts = (
        ScanHistory.objects.filter(created_at__gte=start_of_day, created_at__lt=end_of_day)
        .annotate(hour=ExtractHour('created_at'))
        .values('hour')
        .annotate(total=Count('id'))
    )

    buckets = [0] * 8
    for item in hourly_counts:
        hour = item['hour']
        if hour is None:
            continue
        bucket_index = int(hour) // 3
        if 0 <= bucket_index < 8:
            buckets[bucket_index] += item['total']

    payload = {
        'date': now.date(),
        'buckets': [],
    }
    for bucket_index in range(8):
        start_hour = bucket_index * 3
        end_hour = start_hour + 3
        payload['buckets'].append(
            {
                'start_hour': start_hour,
                'end_hour': end_hour,
                'label': f"{start_hour:02d}:00-{end_hour:02d}:00",
                'count': buckets[bucket_index],
            }
        )

    serializer = AdminTodayScanBucketsSerializer(payload)
    return Response(serializer.data, status=status.HTTP_200_OK)
