# Generated by Django 5.0.1 on 2024-03-01 22:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('request_filters', '0004_filteredrequest_response_info'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='filteredrequest',
            options={'ordering': ['-created_at__date', '-created_at__time__hour', '-created_at__time__minute', '-created_at__time__second', 'filter_index'], 'verbose_name': 'Filtered Request', 'verbose_name_plural': 'Filtered Requests'},
        ),
        migrations.AddField(
            model_name='filteredrequest',
            name='filter_index',
            field=models.PositiveIntegerField(blank=True, help_text='The index of the filter that was triggered.', null=True, verbose_name='Filter Index'),
        ),
    ]
