from collections import Counter, defaultdict
from django.contrib import messages
from django.db import connection
from django.db.models import Q
from django.http import HttpRequest
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from pretix.base.models import Event, Order
from pretix.base.services import tickets
from pretix.helpers import OF_SELF

from .models import DBVATCoupon


def assign_coupons(event: Event, order: Order, **kwargs):
    # ToDo: Make this modular and check for event.settings.dbvat_source, once this becomes a thing...

    positions = list(
        order.positions.filter(
            dbvat_coupons__isnull=True,
            item__dbvat_coupons_item__issue_coupons=True,
        ).select_related("item", "item__dbvat_coupons_item")
    )
    if not positions:
        return
    cntr = Counter(p.subevent_id for p in positions)
    coupons = defaultdict(list)

    for subevent_id, cnt in cntr.items():
        # We're doubling cnt, since everyone is getting two eCoupons.
        cnt = cnt * 2

        found = list(
            DBVATCoupon.objects.select_for_update(
                skip_locked=connection.features.has_select_for_update_skip_locked,
                of=OF_SELF,
            ).filter(
                Q(subevent__isnull=True) | Q(subevent_id=subevent_id),
                event=event,
                used=False,
            )[
                :cnt
            ]
        )
        if len(found) < cnt:
            order.log_action(
                "pretix_dbvat.assignment.failed",
                data={"count": cnt},
            )
            return
        else:
            coupons[subevent_id] = found

    for p in positions:
        for i in range(2):
            coupon = coupons[p.subevent_id].pop()
            coupon.used = True
            coupon.used_by = p
            coupon.save(update_fields=["used", "used_by"])

    tickets.invalidate_cache.apply(kwargs={"event": event.pk, "order": order.pk})


def dbvat_url_context(request: HttpRequest):
    dbvat_event_id = request.event.settings.dbvat_event_id
    locale = "de" if request.LANGUAGE_CODE.startswith("de") else "en"

    return {
        "dbvat_url": f"https://www.veranstaltungsticket-bahn.de/?event={dbvat_event_id}&language={locale}",
        "dbvat_event_id": dbvat_event_id,
        "dbvat_tc_url": "http://www.bahn.de/eventangebote-teilnehmende",
    }


def is_dbvar_event(event: Event):
    return DBVATCoupon.objects.filter(event=event).exists()


class VARRequiredMixin:
    def get(self, request, *args, **kwargs):
        if is_dbvar_event(request.event):
            return super().get(request, *args, **kwargs)
        else:
            messages.info(
                request,
                _(
                    "The DB Event Discount has been discontinued and replaced by the DB Event Offers."
                ),
            )
            return redirect(
                reverse(
                    "plugins:pretix_dbvat:settings",
                    kwargs={
                        "organizer": request.event.organizer.slug,
                        "event": request.event.slug,
                    },
                )
            )
