# Generated manually on 2026-01-09

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("user", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="phone_number",
            field=models.CharField(
                blank=True, max_length=20, null=True, unique=True
            ),
        ),
        migrations.AlterField(
            model_name="user",
            name="auth_provider",
            field=models.CharField(
                choices=[
                    ("google", "Google"),
                    ("phone", "Phone"),
                    ("anonymous", "Anonymous"),
                ],
                max_length=50,
            ),
        ),
        migrations.AddIndex(
            model_name="user",
            index=models.Index(fields=["phone_number"], name="users_phone_n_idx"),
        ),
    ]
