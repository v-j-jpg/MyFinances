# Generated by Django 5.0.1 on 2024-02-01 14:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("backend", "0011_rename_expires_receiptdownloadtoken_delete_in"),
    ]

    operations = [
        migrations.RenameField(
            model_name="receiptdownloadtoken",
            old_name="delete_in",
            new_name="delete_at",
        ),
        migrations.AddField(
            model_name="receiptdownloadtoken",
            name="expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]