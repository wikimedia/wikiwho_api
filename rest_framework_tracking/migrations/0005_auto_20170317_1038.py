# -*- coding: utf-8 -*-
# Generated by Django 1.10.6 on 2017-03-17 09:38
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rest_framework_tracking', '0004_auto_20170317_0949'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='apirequestlog',
            name='path',
        ),
        migrations.AlterField(
            model_name='apirequestlog',
            name='query_params',
            field=models.CharField(blank=True, default='', max_length=256),
        ),
    ]