import copy
from django.db import transaction
from django.dispatch import receiver
from django.http import HttpRequest
from django.template.loader import get_template
from django.urls import resolve, reverse
from django.utils.translation import gettext_lazy as _
from pretix.base.models import Event, Order
from pretix.base.settings import settings_hierarkey
from pretix.base.signals import (
    event_copy_data,
    item_copy_data,
    layout_text_variables,
    logentry_display,
    order_paid,
    order_placed,
)
from pretix.control.signals import item_forms, nav_event
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.signals import (
    checkout_flow_steps,
    footer_link,
    html_head,
    order_info,
    order_meta_from_request,
    position_info,
)
from pretix.presale.views.cart import cart_session

from .checkoutflow import DBVATCheckoutStep
from .forms import ItemProductForm
from .helpers import assign_coupons
from .models import DBVATCoupon, ItemProduct


@receiver(nav_event, dispatch_uid="dbvat_nav")
def navbar_info(sender, request, **kwargs):
    url = resolve(request.path_info)
    if not request.user.has_event_permission(
        request.organizer, request.event, "can_view_orders", request=request
    ):
        return []
    return [
        {
            "label": _("DB VAT"),
            "icon": "train",
            "url": reverse(
                "plugins:pretix_dbvat:list",
                kwargs={
                    "event": request.event.slug,
                    "organizer": request.organizer.slug,
                },
            ),
            "active": url.namespace == "plugins:pretix_dbvat"
            and url.url_name != "revocations",
        }
    ]


@receiver(item_forms, dispatch_uid="dbvat_item_forms")
def control_item_forms(sender, request, item, **kwargs):
    try:
        inst = ItemProduct.objects.get(item=item)
    except ItemProduct.DoesNotExist:
        inst = ItemProduct(item=item)
    return ItemProductForm(
        instance=inst,
        event=sender,
        data=(request.POST if request.method == "POST" else None),
        prefix="dbvatcouponsitem",
    )


@receiver(item_copy_data, dispatch_uid="dbvat_item_copy")
def copy_item(sender, source, target, **kwargs):
    try:
        inst = ItemProduct.objects.get(item=source)
        inst = copy.copy(inst)
        inst.pk = None
        inst.item = target
        inst.save()
    except ItemProduct.DoesNotExist:
        pass


@receiver(signal=event_copy_data, dispatch_uid="dbvat_copy_data")
def event_copy_data_receiver(sender, other, question_map, item_map, **kwargs):
    for ip in ItemProduct.objects.filter(item__event=other):
        ip = copy.copy(ip)
        ip.pk = None
        ip.event = sender
        ip.item = item_map[ip.item_id]
        ip.save()


@receiver(signal=logentry_display, dispatch_uid="dbvat_logentry_display")
def badges_logentry_display(sender, logentry, **kwargs):
    if not logentry.action_type.startswith("pretix_dbvat"):
        return

    plains = {
        "pretix_dbvat.coupon.deleted": _("DB VAT eCoupon deleted."),
        "pretix_dbvat.coupon.added": _("DB VAT eCoupon created."),
        "pretix_dbvat.coupon.changed": _("DB VAT eCoupon changed."),
        "pretix_dbvat.assignment.failed": _("Failed to assign an DB VAT eCoupon."),
    }

    if logentry.action_type in plains:
        return plains[logentry.action_type]


@receiver(signal=order_placed, dispatch_uid="dbvat_order_placed")
@transaction.atomic()
def order_placed_receiver(sender, order, **kwargs):
    if sender.settings.dbvat_issue_when == "order_placed":
        if (
            sender.settings.dbvat_issue_when == "on_demand"
            and order.meta_info_data.get("dbvat_requested", False)
        ) or sender.settings.dbvat_issue_when == "always":
            assign_coupons(sender, order, **kwargs)


@receiver(signal=order_paid, dispatch_uid="dbvat_order_paid")
@transaction.atomic()
def order_paid_receiver(sender, order, **kwargs):
    print(order.meta_info_data)
    if (
        sender.settings.dbvat_issue_when == "on_demand"
        and order.meta_info_data.get("dbvat_requested", False)
    ) or sender.settings.dbvat_issue_when == "always":
        assign_coupons(sender, order, **kwargs)


@receiver(layout_text_variables, dispatch_uid="dbvat_layout_text_variables")
def recv_layout_text_variables(sender, request=None, **kwargs):
    def _get_coupon(number, op, order, event):
        d = list(op.dbvat_coupons.all())
        if d:
            return d[number - 1].secret
        elif op.addon_to_id:
            return _get_coupon(number, op.addon_to, order, event)
        else:
            return ""

    def _get_coupon_1(op, order, event):
        return _get_coupon(1, op, order, event)

    def _get_coupon_2(op, order, event):
        return _get_coupon(2, op, order, event)

    def _get_coupon_bulk(number, ops):
        # TODO: Pick first or second code
        d = {
            c.used_by_id: c
            for c in DBVATCoupon.objects.filter(
                used_by__in=[op.pk for op in ops]
                + [op.addon_to_id for op in ops if op.addon_to_id]
            )
        }
        return [
            d[op.pk].secret
            if op.pk in d
            else (d[op.addon_to_id].secret if op.addon_to_id in d else "")
            for op in ops
        ]

    def _get_coupon_1_bulk(ops):
        return _get_coupon_bulk(1, ops)

    def _get_coupon_2_bulk(ops):
        return _get_coupon_bulk(2, ops)

    return {
        "dbvat_coupon_1": {
            "label": _("DB VAT eCoupon #1"),
            "editor_sample": "ABCDE12345",
            "evaluate": _get_coupon_1,
            # "evaluate_bulk": _get_coupon_1_bulk,
        },
        "dbvat_coupon_2": {
            "label": _("DB VAT eCoupon #2"),
            "editor_sample": "ABCDE12345",
            "evaluate": _get_coupon_2,
            # "evaluate_bulk": _get_coupon_2_bulk,
        },
    }


@receiver(order_info, dispatch_uid="dbvat_order_info")
def order_info(sender: Event, order: Order, request, **kwargs):
    if not sender.settings.dbvat_show_infobox:
        return ""

    if not DBVATCoupon.objects.filter(used_by__in=order.positions.all()).exists():
        return ""

    template = get_template("pretix_dbvat/order_position_info.html")
    ctx = {
        "order": order,
        "positions": order.positions.all(),
        "event": sender,
    }
    return template.render(ctx, request)


@receiver(position_info, dispatch_uid="dbvat_position_info")
def position_info(sender: Event, order: Order, position, request, **kwargs):
    if not sender.settings.dbvat_show_infobox:
        return ""

    if not position.dbvat_coupons.exists():
        return ""

    template = get_template("pretix_dbvat/order_position_info.html")
    ctx = {
        "order": order,
        "positions": [position],
        "event": sender,
    }
    return template.render(ctx, request)


@receiver(html_head, dispatch_uid="dbvat_html_head")
def html_head_presale(sender, request=None, **kwargs):
    template = get_template("pretix_dbvat/presale_head.html")
    return template.render({})


@receiver(footer_link, dispatch_uid="dbvat_link_privacy")
def footer_link(sender, request=None, **kwargs):
    v = []
    if sender.settings.dbvat_add_infopage_link:
        v.append(
            {
                "label": _("DB Event Discount"),
                "url": eventreverse(sender, "plugins:pretix_dbvat:terms"),
            }
        )
    return v


@receiver(checkout_flow_steps, dispatch_uid="dbvat_checkout_step")
def checkout_flow_steps(sender, **kwargs):
    return DBVATCheckoutStep


@receiver(order_meta_from_request, dispatch_uid="dbvat_order_meta_from_request")
def order_meta_from_request(sender: Event, request: HttpRequest, **kwargs):
    if sender.settings.dbvat_issue_when == "on_demand":
        cs = cart_session(request)
        return {
            "dbvat_requested": cs.get("dbvat_requested", False),
        }
    return {}


settings_hierarkey.add_default("dbvat_source", "list", str)
settings_hierarkey.add_default("dbvat_discount", 0, int)
settings_hierarkey.add_default("dbvat_issue_on", "order_placed", str)
settings_hierarkey.add_default("dbvat_issue_when", "always", str)
settings_hierarkey.add_default("dbvat_send_email", True, bool)
settings_hierarkey.add_default("dbvat_show_infobox", True, bool)
settings_hierarkey.add_default("dbvat_provide_pdfvars", True, bool)
settings_hierarkey.add_default("dbvat_add_infopage_link", True, bool)
