import logging
from django.contrib import messages
from django.db import transaction
from django.http import Http404, HttpResponseRedirect
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView
from pretix.base.models import LogEntry
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.control.views import CreateView, PaginationMixin, UpdateView
from pretix.control.views.event import EventSettingsFormView, EventSettingsViewMixin
from pretix.helpers.compat import CompatDeleteView
from pretix.helpers.models import modelcopy

from .forms import CouponBulkForm, CouponForm, SettingsForm
from .models import DBVATCoupon

logger = logging.getLogger(__name__)


class CouponListView(
    EventSettingsViewMixin,
    EventSettingsFormView,
    PaginationMixin,
    EventPermissionRequiredMixin,
    ListView,
):
    model = DBVATCoupon
    context_object_name = "coupons"
    form_class = SettingsForm
    template_name = "pretix_dbvat/index.html"
    permission = "can_view_orders"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["count"] = self.request.event.dbvat_coupons.filter(used=False).count()
        ctx["event"] = self.request.event
        ctx["any_product_issuing"] = self.request.event.items.filter(
            dbvat_coupons_item__issue_coupons=True
        ).exists()
        return ctx

    def get_queryset(self):
        qs = (
            self.request.event.dbvat_coupons.filter()
            .select_related("subevent", "used_by", "used_by__order")
            .order_by("used", "secret")
        )

        return qs

    def get_success_url(self) -> str:
        return reverse(
            "plugins:pretix_dbvat:list",
            kwargs={
                "organizer": self.request.event.organizer.slug,
                "event": self.request.event.slug,
            },
        )


class CouponDelete(EventPermissionRequiredMixin, CompatDeleteView):
    model = DBVATCoupon
    template_name = "pretix_dbvat/delete.html"
    permission = "can_change_orders"
    context_object_name = "secret"

    def get_object(self, queryset=None):
        try:
            return self.request.event.dbvat_coupons.get(id=self.kwargs["secret"])
        except DBVATCoupon.DoesNotExist:
            raise Http404(_("The requested ticket code does not exist."))

    def get(self, request, *args, **kwargs):
        if self.get_object().used:
            messages.error(
                request,
                _("A coupon code can not be deleted if it already has been used."),
            )
            return HttpResponseRedirect(self.get_success_url())
        return super().get(request, *args, **kwargs)

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        success_url = self.get_success_url()

        if self.get_object().used:
            messages.error(
                request,
                _("A coupon code can not be deleted if it already has been used."),
            )
        else:
            self.object.log_action(
                "pretix_dbvat.coupon.deleted", user=self.request.user
            )
            self.object.delete()
            messages.success(request, _("The selected ticket code has been deleted."))
        return HttpResponseRedirect(success_url)

    def get_success_url(self) -> str:
        return reverse(
            "plugins:pretix_dbvat:list",
            kwargs={
                "organizer": self.request.event.organizer.slug,
                "event": self.request.event.slug,
            },
        )


class CouponUpdate(EventPermissionRequiredMixin, UpdateView):
    model = DBVATCoupon
    template_name = "pretix_dbvat/detail.html"
    permission = "can_change_orders"
    context_object_name = "secret"
    form_class = CouponForm

    def get_object(self, queryset=None):
        try:
            return self.request.event.dbvat_coupons.get(id=self.kwargs["secret"])
        except CouponUpdate.DoesNotExist:
            raise Http404(_("The requested ticket code does not exist."))

    @transaction.atomic
    def form_valid(self, form):
        messages.success(self.request, _("Your changes have been saved."))
        if form.has_changed():
            self.object.log_action(
                "pretix_dbvat.coupon.changed",
                user=self.request.user,
                data={k: form.cleaned_data.get(k) for k in form.changed_data},
            )
        return super().form_valid(form)

    def get_success_url(self) -> str:
        return reverse(
            "plugins:pretix_dbvat:list",
            kwargs={
                "organizer": self.request.event.organizer.slug,
                "event": self.request.event.slug,
            },
        )


class CouponBulkCreate(EventPermissionRequiredMixin, CreateView):
    model = DBVATCoupon
    template_name = "pretix_dbvat/bulk.html"
    permission = "can_change_orders"
    form_class = CouponBulkForm

    def get_success_url(self) -> str:
        return reverse(
            "plugins:pretix_dbvat:list",
            kwargs={
                "organizer": self.request.event.organizer.slug,
                "event": self.request.event.slug,
            },
        )

    @cached_property
    def copy_from(self):
        if self.request.GET.get("copy_from") and not getattr(self, "object", None):
            try:
                return self.request.event.dbvat_coupons.get(
                    pk=self.request.GET.get("copy_from")
                )
            except DBVATCoupon.DoesNotExist:
                pass

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        if self.copy_from:
            i = modelcopy(self.copy_from)
            i.pk = None
            i.redeemed = 0
            kwargs["instance"] = i
        else:
            kwargs["instance"] = DBVATCoupon(event=self.request.event)
        return kwargs

    @transaction.atomic
    def form_valid(self, form):
        log_entries = []
        objs = form.save(self.request.event)
        voucherids = []
        for v in objs:
            log_entries.append(
                v.log_action(
                    "pretix_dbvat.coupon.added",
                    data=form.cleaned_data,
                    user=self.request.user,
                    save=False,
                )
            )
            voucherids.append(v.pk)
        LogEntry.objects.bulk_create(log_entries)
        messages.success(self.request, _("The new coupon have been created."))
        return HttpResponseRedirect(self.get_success_url())
