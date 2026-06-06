from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='taxes_usuario_id',
            field=models.IntegerField(
                blank=True,
                help_text='Primary key (id_usuario) in Postgres taxes.usuarios — not a FK (separate DB).',
                null=True,
                verbose_name='Taxes usuario ID',
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='negocio_id',
            field=models.IntegerField(
                blank=True,
                help_text='Tenant (negocio) in Postgres taxes — copied from linked usuarios row.',
                null=True,
                verbose_name='Negocio ID',
            ),
        ),
    ]
