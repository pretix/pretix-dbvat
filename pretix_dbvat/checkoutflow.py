from distutils.util import strtobool
from django.shortcuts import redirect
from django.utils.translation import pgettext_lazy
from pretix.presale.checkoutflow import TemplateFlowStep
from pretix.presale.views import CartMixin


class DBVATCheckoutStep(CartMixin, TemplateFlowStep):
    priority = 900  # Just before the final step
    identifier = "dbvat"
    template_name = "pretix_dbvat/checkout_step.html"
    icon = "train"
    label = pgettext_lazy("checkoutflow", "DB Event Discount")

    def is_applicable(self, request):
        settings = request.event.settings

        if settings.dbvat_issue_when == "on_demand":
            return True

        return False

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["cart"] = self.get_cart()
        ctx["cart_session"] = self.cart_session
        return ctx

    def is_completed(self, request, warn=False):
        self.request = request
        cs = self.cart_session

        return cs.get("dbvat_passed", False)

    def post(self, request):
        self.request = request

        requested = request.POST.get("dbvat_requested", None)
        self.cart_session["dbvat_requested"] = strtobool(requested)
        self.cart_session["dbvat_passed"] = True

        return redirect(self.get_next_url(request))
