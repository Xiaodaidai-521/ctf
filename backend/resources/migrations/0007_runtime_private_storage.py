from django.db import migrations, models
import data_security.runtime.storage


class Migration(migrations.Migration):
    dependencies = [('resources', '0006_resourcecache_canary_payload')]
    operations = [
        migrations.AlterField(model_name='resource', name='file', field=models.FileField(
            storage=data_security.runtime.storage.protected_storage, upload_to='resources/', verbose_name='资源文件')),
        migrations.AlterField(model_name='resource', name='cover_image', field=models.ImageField(
            blank=True, null=True, storage=data_security.runtime.storage.protected_storage,
            upload_to='resource_covers/', verbose_name='封面图片')),
    ]
