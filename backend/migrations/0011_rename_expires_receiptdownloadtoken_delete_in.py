# Generated by Django 5.0.1 on 2024-02-01 14:44

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("backend", "0010_receiptdownloadtoken_expires"),
    ]

    operations = [
        migrations.RenameField(
            model_name="receiptdownloadtoken",
            old_name="expires",
            new_name="delete_in",
        ),
    ]