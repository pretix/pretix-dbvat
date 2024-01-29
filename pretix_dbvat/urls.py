from django.urls import path

from .views import CouponBulkCreate, CouponDelete, CouponListView, CouponUpdate

urlpatterns = [
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
]
