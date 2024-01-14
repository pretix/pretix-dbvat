from django import forms
from django.core.exceptions import ValidationError
from django.db.models.functions import Lower
from django.forms import DateField
from django.urls import reverse
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django_scopes.forms import SafeModelChoiceField
from pretix.base.forms import SettingsForm
from pretix.base.forms.widgets import DatePickerWidget
from pretix.control.forms.widgets import Select2
from pretix.helpers.models import modelcopy

from .models import DBVATCoupon, ItemProduct


class SettingsForm(SettingsForm):
    dbvat_source = forms.ChoiceField(
        label=_("eCoupon source"),
        choices=(
            ("list", _("List")),
            ("api", _("API")),
        ),
        initial="list",
    )

    dbvat_discount = forms.IntegerField(
        label=_("Discount amount"),
        widget=forms.NumberInput(
            attrs={'addon_after': '%'}
        ),
    )

    dbvat_issue_on = forms.ChoiceField(
        label=_("Issue eCoupons"),
        choices=(
            ("order_placed", _("when order is placed")),
            ("order_paid", _("when order is marked as paid")),
        ),
        initial="order_placed",
    )

    dbvat_issue_when = forms.ChoiceField(
        label=_("Issue eCoupons to"),
        choices=(
            ("always", _("all customers, if a matching product is purchased")),
            ("on_demand", _("customers that actively request them during checkout")),
        ),
        initial="always",
    )

    dbvat_send_email = forms.BooleanField(
        label=_("Send email with eCoupons to customer"),
        required=False,
        initial=True,
    )

    dbvat_show_infobox = forms.BooleanField(
        label=_("Show infobox with eCoupons in order overview"),
        required=False,
        initial=True,
    )

    dbvat_provide_pdfvars = forms.BooleanField(
        label=_("Provide eCoupons as PDF-ticket variables"),
        help_text=_("If using the ticket PDF to communicate the eCoupons to your customers, consider always issuing "
                    "the eCoupons to avoid empty fields. Please make sure to also provide all required information "
                    "in the PDF. Be aware though, that eCoupons will not be represented in passbook tickets."),
        required=False,
        initial=True,
        disabled=True,
    )

    dbvat_add_infopage_link = forms.BooleanField(
        label=_("Add link to information and Terms & Conditions page to the shops footer"),
        help_text=_("Even if this option is disabled, it will still be accessible, as it is linked from the "
                    "E-Mail as well as the information-box."),
        required=False,
        initial=True,
    )


class CouponForm(forms.ModelForm):
    class Meta:
        model = DBVATCoupon
        fields = ["secret", "valid_from", "valid_to", "subevent"]
        field_classes = {
            "valid_from": DateField,
            "valid_to": DateField,
            "subevent": SafeModelChoiceField,
        }
        widgets = {
            "valid_from": DatePickerWidget,
            "valid_to": DatePickerWidget,
        }

    def __init__(self, *args, **kwargs):
        instance = kwargs.get("instance")
        kwargs.pop("event")
        super().__init__(*args, **kwargs)

        if instance.event.has_subevents:
            self.fields["subevent"].queryset = instance.event.subevents.all()
            self.fields["subevent"].widget = Select2(
                attrs={
                    "data-model-select2": "event",
                    "data-select2-url": reverse(
                        "control:event.subevents.select2",
                        kwargs={
                            "event": instance.event.slug,
                            "organizer": instance.event.organizer.slug,
                        },
                    ),
                    "data-placeholder": pgettext_lazy("subevent", "Date"),
                }
            )
            self.fields["subevent"].widget.choices = self.fields["subevent"].choices
            self.fields["subevent"].required = False
        elif "subevent":
            del self.fields["subevent"]

    def clean(self):
        data = super().clean()

        if "secrets" in data:
            data["secrets"] = [
                a.strip() for a in data.get("secrets", "").strip().split("\n") if a
            ]

        DBVATCoupon.clean_subevent(data, self.instance.event)
        DBVATCoupon.clean_secret(data, self.instance.event, self.instance.pk)

        return data


class CouponBulkForm(CouponForm):
    secrets = forms.CharField(
        widget=forms.Textarea,
        label=_("Coupon codes"),
        help_text=_("Add one coupon code per line."),
        required=True,
    )

    class Meta:
        model = DBVATCoupon
        fields = ["valid_from", "valid_to", "subevent"]
        field_classes = {
            "valid_from": DateField,
            "valid_to": DateField,
            "subevent": SafeModelChoiceField,
        }
        widgets = {
            "valid_from": DatePickerWidget,
            "valid_to": DatePickerWidget,
        }

    def clean(self):
        data = super().clean()

        vouchers = self.instance.event.dbvat_coupons.annotate(
            secret_lower=Lower("secret")
        ).filter(secret_lower__in=[c.lower() for c in data["secrets"]])
        if vouchers.exists():
            raise ValidationError(
                _("Coupon code {code} already exists.").format(
                    code=vouchers.first().secret
                )
            )
        return data

    def save(self, event, *args, **kwargs):
        objs = []
        for secret in self.cleaned_data["secrets"]:
            if not secret.strip():
                continue
            obj = modelcopy(self.instance)
            obj.event = event
            obj.secret = secret
            data = dict(self.cleaned_data)
            data["secret"] = secret.strip()
            data["bulk"] = True
            del data["secrets"]
            objs.append(obj)
        DBVATCoupon.objects.bulk_create(objs)
        objs = []
        for v in event.dbvat_coupons.filter(secret__in=self.cleaned_data["secrets"]):
            # We need to query them again as bulk_create does not fill in .pk values on databases
            # other than PostgreSQL
            objs.append(v)
        return objs


class ItemProductForm(forms.ModelForm):
    issue_coupons = forms.BooleanField(
        label=pgettext_lazy(
            "dbvat", "Issue DB VAT eCoupons if this product is purchased"
        ),
        required=False,
    )

    class Meta:
        model = ItemProduct
        fields = ["issue_coupons"]
        exclude = []

    def __init__(self, *args, **kwargs):
        event = kwargs.pop("event")  # NoQA
        instance = kwargs.get("instance")  # NoQA
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        if not self.cleaned_data["issue_coupons"]:
            if self.instance.pk:
                self.instance.delete()
            else:
                return
        else:
            v = self.cleaned_data["issue_coupons"]
            self.instance.issue_coupons = v
            return super().save(commit=commit)
