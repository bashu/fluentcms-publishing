# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.utils.timezone
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('fluent_pages', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='FluentPage',
            fields=[
                ('urlnode_ptr', models.OneToOneField(parent_link=True, auto_created=True, primary_key=True, serialize=False, to='fluent_pages.UrlNode')),
                ('publishing_is_draft', models.BooleanField(default=True, db_index=True, editable=False)),
                ('publishing_modified_at', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ('publishing_published_at', models.DateTimeField(null=True, editable=False)),
                ('layout', models.ForeignKey(verbose_name='Layout', to='fluent_pages.PageLayout', null=True)),
                ('publishing_linked', models.OneToOneField(related_name='publishing_draft', null=True, on_delete=django.db.models.deletion.SET_NULL, editable=False, to='fluentpage.FluentPage')),
            ],
            options={
                'abstract': False,
                'db_table': 'pagetype_fluentpage_fluentpage',
                'verbose_name': 'Page',
                'verbose_name_plural': 'Pages',
                'permissions': (('change_page_layout', 'Can change Page layout'),),
            },
            bases=('fluent_pages.htmlpage', models.Model),
        ),
    ]
