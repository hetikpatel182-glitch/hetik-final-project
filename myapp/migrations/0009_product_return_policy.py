from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('myapp', '0008_product_product_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='returnable',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='product',
            name='return_days',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='cart',
            name='delivery_date',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='cart',
            name='return_status',
            field=models.CharField(default='none', max_length=100),
        ),
    ]
