from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('export_risk', '0003_riskdecision_origin')]

    operations = [
        migrations.CreateModel(
            name='ColumnRiskPermission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('permission_ref', models.CharField(max_length=160, unique=True)),
                ('request_fingerprint', models.CharField(max_length=64)),
                ('binding_hash', models.CharField(max_length=64)),
                ('grant_document', models.JSONField()),
                ('grant_event_id', models.CharField(max_length=64)),
                ('approval_document', models.JSONField(null=True)),
                ('approval_event_id', models.CharField(blank=True, max_length=64)),
                ('state', models.CharField(choices=[('pending', '待审批'), ('approved', '已审批'),
                                                     ('revoked', '已撤销')], default='pending', max_length=16)),
                ('expires_at', models.DateTimeField()),
                ('revoked_at', models.DateTimeField(null=True)),
                ('decision', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                              to='export_risk.riskdecision', to_field='decision_id')),
            ],
            options={'permissions': (('use_columnriskpermission', '使用逐列导出风险许可'),)},
        ),
    ]
