# -*- coding: utf-8 -*-
# Generated by Django 1.10.7 on 2017-06-02 18:51
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('perma', '0023_apikey'),
    ]

    operations = [
        migrations.AddField(
            model_name='historicalregistrar',
            name='address',
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
        migrations.AddField(
            model_name='registrar',
            name='address',
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
    ]
