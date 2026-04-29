from rest_framework import serializers

from api.models import ScanHistory
from authapp.models import User

from .models import UserSubscription


class AdminDashboardSerializer(serializers.Serializer):
    total_users = serializers.IntegerField()
    total_active_users = serializers.IntegerField()
    total_subscribers = serializers.IntegerField()
    total_scans = serializers.IntegerField()


class AdminUserSerializer(serializers.ModelSerializer):
    username = serializers.SerializerMethodField()
    subscription_plan = serializers.CharField(source='admin_subscription.plan', read_only=True)
    status = serializers.SerializerMethodField()
    total_scan = serializers.IntegerField(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'subscription_plan', 'status', 'total_scan']

    def get_username(self, obj):
        if obj.username and '@' not in obj.username:
            return obj.username

        full_name = f"{obj.first_name} {obj.last_name}".strip()
        if full_name:
            return full_name

        if obj.username and '@' in obj.username:
            return obj.username.split('@', 1)[0]

        return obj.username

    def get_status(self, obj):
        return 'active' if obj.is_active else 'inactive'


class AdminUserUpdateSerializer(serializers.Serializer):
    username = serializers.CharField(required=False, max_length=150)
    subscription_plan = serializers.ChoiceField(required=False, choices=UserSubscription.PLAN_CHOICES)


class AdminScanSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.username', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = ScanHistory
        fields = [
            'id',
            'user',
            'user_name',
            'user_email',
            'mode',
            'detected_label',
            'confidence',
            'created_at',
        ]


class AdminSubscriptionSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.username', read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)
    purchased_subscription_plan = serializers.CharField(source='plan', read_only=True)

    class Meta:
        model = UserSubscription
        fields = [
            'user',
            'user_name',
            'email',
            'purchased_subscription_plan',
            'status',
            'amount',
            'billing_period',
        ]
