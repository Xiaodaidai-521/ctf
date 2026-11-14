from django.db import migrations, models
import data_security.runtime.storage
import feedback_center.models


class Migration(migrations.Migration):
    dependencies = [('feedback_center', '0003_feedbackattachment_private_file')]
    operations = [migrations.AlterField(model_name='feedbackattachment', name='file', field=models.FileField(
        storage=data_security.runtime.storage.protected_storage,
        upload_to=feedback_center.models.feedback_attachment_path, verbose_name='受控文件'))]
