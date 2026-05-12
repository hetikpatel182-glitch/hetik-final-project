from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('myapp', '0007_contact'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='product_status',
            field=models.BooleanField(default=True),
        ),
    ]
