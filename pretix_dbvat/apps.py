from django.utils.translation import gettext_lazy

from . import __version__

try:
    from pretix.base.plugins import PluginConfig
except ImportError:
    raise RuntimeError("Please use pretix 2.7 or above to run this plugin!")


class PluginApp(PluginConfig):
    default = True
    name = "pretix_dbvat"
    verbose_name = "DB Event Discount"

    class PretixPluginMeta:
        name = gettext_lazy("DB Event Discount")
        author = "pretix team"
        description = gettext_lazy(
            "Distribute Deutsche Bahn Veranstaltungsrabatt (DB VAT) eCoupons to your attendees"
        )
        visible = True
        picture = "pretix_dbvat/db-logo.svg"
        version = __version__
        category = "INTEGRATION"
        compatibility = "pretix>=2023.10.0"

    def ready(self):
        from . import signals  # NOQA
