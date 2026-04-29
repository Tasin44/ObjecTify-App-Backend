from django.conf import settings
from django.db import models


class UserSubscription(models.Model):
    PLAN_MONTHLY = 'monthly'
    PLAN_YEARLY = 'yearly'
    PLAN_CHOICES = [
        (PLAN_MONTHLY, 'Monthly'),
        (PLAN_YEARLY, 'Yearly'),
    ]

    STATUS_ACTIVE = 'active'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
    ]

    BILLING_MONTHLY = 'monthly'
    BILLING_CHOICES = [
        (BILLING_MONTHLY, 'Monthly'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='admin_subscription',
    )
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default=PLAN_MONTHLY)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=100)
    billing_period = models.CharField(max_length=20, choices=BILLING_CHOICES, default=BILLING_MONTHLY)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.email} - {self.plan}'
