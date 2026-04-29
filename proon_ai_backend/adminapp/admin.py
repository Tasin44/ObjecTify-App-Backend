from django.contrib import admin

from .models import UserSubscription


@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'status', 'amount', 'billing_period', 'updated_at')
    list_filter = ('plan', 'status', 'billing_period')
    search_fields = ('user__email', 'user__username')
