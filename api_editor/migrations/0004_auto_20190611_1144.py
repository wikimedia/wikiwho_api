# -*- coding: utf-8 -*-
# Generated by Django 1.11.20 on 2019-06-11 09:44
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api_editor', '0003_auto_20190509_1345'),
    ]

    operations = [
        migrations.AddField(
            model_name='editordatade',
            name='revisions',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='editordatadenotindexed',
            name='revisions',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='editordataen',
            name='revisions',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='editordataennotindexed',
            name='revisions',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='editordataes',
            name='revisions',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='editordataesnotindexed',
            name='revisions',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='editordataeu',
            name='revisions',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='editordataeunotindexed',
            name='revisions',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='editordatatr',
            name='revisions',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='editordatatrnotindexed',
            name='revisions',
            field=models.IntegerField(default=0),
        ),
    ]
