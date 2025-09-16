from django.urls import path

from .views import (
    CouponBulkCreate,
    CouponDelete,
    CouponListView,
    CouponUpdate,
    VATSettingsView,
)

urlpatterns = [
    # DB VAR
    path(
        "control/event/<str:organizer>/<str:event>/dbvat/",
        CouponListView.as_view(),
        name="list",
    ),
    path(
        "control/event/<str:organizer>/<str:event>/dbvat/<int:secret>/",
        CouponUpdate.as_view(),
        name="coupon",
    ),
    path(
        "control/event/<str:organizer>/<str:event>/dbvat/<int:secret>/delete",
        CouponDelete.as_view(),
        name="delete",
    ),
    path(
        "control/event/<str:organizer>/<str:event>/dbvat/bulk_add",
        CouponBulkCreate.as_view(),
        name="bulk",
    ),
    # Totally not DB VAT, but actually is
    path(
        "control/event/<str:organizer>/<str:event>/dbvat/settings",
        VATSettingsView.as_view(),
        name="settings",
    ),
]
