# -*- coding: utf-8 -*-
# Generated by Django 1.11.29 on 2023-04-24 21:28
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rest_framework_tracking', '0014_auto_20200616_1904'),
    ]

    operations = [
        migrations.AlterField(
            model_name='apirequestlog',
            name='language',
            field=models.CharField(choices=[('', '-------'), ('en', 'English'), ('de', 'German'), ('eu', 'Basque'), ('tr', 'Turkish'), ('es', 'Spanish'), ('fr', 'French')], default='', max_length=8),
        ),
    ]
