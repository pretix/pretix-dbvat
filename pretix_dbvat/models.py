from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from pretix.base.models import LoggedModel, OrderPosition, SubEvent


class DBVATCoupon(LoggedModel):
    event = models.ForeignKey(
        "pretixbase.Event", related_name="dbvat_coupons", on_delete=models.CASCADE
    )
    secret = models.CharField(
        verbose_name=_("eCoupon code"),
        max_length=255,
        null=False,
        blank=False,
        db_index=True,
    )
    valid_from = models.DateField(
        verbose_name=_("Valid from"),
    )
    valid_to = models.DateField(
        verbose_name=_("Valid until"),
    )
    used = models.BooleanField(default=False)
    subevent = models.ForeignKey(
        SubEvent,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        verbose_name=pgettext_lazy("subevent", "Date"),
    )
    used_by = models.ForeignKey(
        OrderPosition,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="dbvat_coupons",
    )

    def __str__(self):
        return self.secret

    @staticmethod
    def clean_subevent(data, event):
        if data.get("subevent") and not event.has_subevents:
            raise ValidationError(
                "You can not select a subevent if your event is not an event series."
            )

    @staticmethod
    def clean_secret(data, event, pk):
        if "secret" in data:
            s = data["secret"].split(";")[0]
            if len(s) != 16:
                raise ValidationError(
                    _(
                        "Coupon code '{code}' does not look like a valid DB eCoupon."
                    ).format(code=data["secret"])
                )
            data["secret"] = s

            if DBVATCoupon.objects.filter(
                Q(secret__iexact=data["secret"]) & Q(event=event) & ~Q(pk=pk)
            ).exists():
                raise ValidationError(_("An entry with this code already exists."))


class ItemDBVATConfig(models.Model):
    item = models.OneToOneField(
        "pretixbase.Item",
        related_name="dbvat_coupons_item",
        on_delete=models.CASCADE,
    )
    issue_coupons = models.BooleanField(
        verbose_name=_("Issue DB VAT eCoupons if this product is purchased"),
        default=False,
    )
