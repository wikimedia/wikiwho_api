# -*- coding: utf-8 -*-
# Generated by Django 1.11.29 on 2023-04-30 03:10
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0009_auto_20230428_1812'),
    ]

    operations = [
        migrations.AlterField(
            model_name='longfailedarticle',
            name='language',
            field=models.CharField(choices=[('', '-------'), ('en', 'English'), ('de', 'German'), ('eu', 'Basque'), ('tr', 'Turkish'), ('es', 'Spanish'), ('fr', 'French'), ('it', 'Italian'), ('hu', 'Hungarian'), ('id', 'Indonesian')], default='', max_length=8),
        ),
        migrations.AlterField(
            model_name='recursionerrorarticle',
            name='language',
            field=models.CharField(choices=[('', '-------'), ('en', 'English'), ('de', 'German'), ('eu', 'Basque'), ('tr', 'Turkish'), ('es', 'Spanish'), ('fr', 'French'), ('it', 'Italian'), ('hu', 'Hungarian'), ('id', 'Indonesian')], default='', max_length=8),
        ),
    ]
