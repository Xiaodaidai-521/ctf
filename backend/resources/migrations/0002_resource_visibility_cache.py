# Generated manually for tutoring resource cache and visibility controls.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('resources', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='resource',
            name='is_tutoring_reserved',
            field=models.BooleanField(db_index=True, default=False, verbose_name='Tutoring reserved only'),
        ),
        migrations.CreateModel(
            name='ResourceCache',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('studentId', models.PositiveIntegerField(db_index=True)),
                ('knowledgePoint', models.CharField(db_index=True, max_length=160)),
                ('resourceList', models.JSONField(blank=True, default=list)),
                ('studentLevel', models.CharField(blank=True, max_length=40)),
                ('cacheHitCount', models.PositiveIntegerField(default=0)),
                ('createdTime', models.DateTimeField(auto_now_add=True)),
                ('updatedTime', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-updatedTime'],
                'indexes': [
                    models.Index(fields=['studentId', 'knowledgePoint'], name='resources_r_student_607628_idx'),
                    models.Index(fields=['studentLevel'], name='resources_r_student_4cc080_idx'),
                ],
                'constraints': [
                    models.UniqueConstraint(fields=('studentId', 'knowledgePoint'), name='unique_resource_cache_student_knowledge'),
                ],
            },
        ),
    ]
