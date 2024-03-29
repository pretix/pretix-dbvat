# Generated by Django 4.2.8 on 2024-01-14 12:38

import django.db.models.deletion
import pretix.base.models.base
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        (
            "pretixbase",
            "0254_alter_logentry_organizer_link_and_more",
        ),
    ]

    operations = [
        migrations.CreateModel(
            name="ItemProduct",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("issue_coupons", models.BooleanField(default=False)),
                (
                    "item",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="dbvat_coupons_item",
                        to="pretixbase.item",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="DBVATCoupon",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("secret", models.CharField(db_index=True, max_length=255)),
                ("valid_from", models.DateField()),
                ("valid_to", models.DateField()),
                ("used", models.BooleanField(default=False)),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="dbvat_coupons",
                        to="pretixbase.event",
                    ),
                ),
                (
                    "subevent",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="pretixbase.subevent",
                    ),
                ),
                (
                    "used_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="dbvat_coupons",
                        to="pretixbase.orderposition",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
            bases=(models.Model, pretix.base.models.base.LoggingMixin),
        ),
    ]
