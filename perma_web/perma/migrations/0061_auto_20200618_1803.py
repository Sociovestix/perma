# Generated by Django 2.2.13 on 2020-06-18 18:03

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('perma', '0060_auto_20200618_1706'),
    ]

    operations = [
        migrations.AddField(
            model_name='historicallink',
            name='bonus_link',
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='historicallinkuser',
            name='bonus_links',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='historicalregistrar',
            name='bonus_links',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='link',
            name='bonus_link',
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='linkuser',
            name='bonus_links',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='registrar',
            name='bonus_links',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
