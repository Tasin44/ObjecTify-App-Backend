from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authapp', '0002_user_profile_image'),
    ]

    operations = [
        migrations.CreateModel(
            name='Personalization',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('surface_area', models.CharField(max_length=100)),
                ('fruit_tress', models.IntegerField()),
                ('fruit_tree_types', models.CharField(max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=models.CASCADE, related_name='personalization', to='authapp.user')),
            ],
        ),
    ]
