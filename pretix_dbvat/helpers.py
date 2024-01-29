from collections import Counter, defaultdict
from django.db import connection
from django.db.models import Q
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
