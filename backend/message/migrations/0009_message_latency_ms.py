from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('message', '0008_merge_20260114_0755'),
    ]

    operations = [
        migrations.AddField(
            model_name='message',
            name='latency_ms',
            field=models.FloatField(blank=True, help_text='Model response latency in milliseconds for Assistant messages', null=True),
        ),
    ]
