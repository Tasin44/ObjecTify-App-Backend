from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def create_default_subscriptions(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))
    UserSubscription = apps.get_model('adminapp', 'UserSubscription')

    subscriptions = []
    for user in User.objects.all().iterator():
        subscriptions.append(UserSubscription(user_id=user.id))

    UserSubscription.objects.bulk_create(subscriptions, ignore_conflicts=True)


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('authapp', '0003_personalization'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserSubscription',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('plan', models.CharField(choices=[('monthly', 'Monthly'), ('yearly', 'Yearly')], default='monthly', max_length=20)),
                ('status', models.CharField(choices=[('active', 'Active')], default='active', max_length=20)),
                ('amount', models.DecimalField(decimal_places=2, default=100, max_digits=10)),
                ('billing_period', models.CharField(choices=[('monthly', 'Monthly')], default='monthly', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='admin_subscription', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.RunPython(create_default_subscriptions, migrations.RunPython.noop),
    ]
