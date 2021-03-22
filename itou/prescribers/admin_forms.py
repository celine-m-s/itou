from django import forms
from django.utils.translation import gettext_lazy

from itou.prescribers.models import PrescriberOrganization


class PrescriberOrganizationAdminForm(forms.ModelForm):

    # Add a custom form field that is not part of the model in the admin.
    extra_field_refresh_geocoding = forms.BooleanField(
        label=gettext_lazy("Recalculer le geocoding"),
        help_text=gettext_lazy(
            "Si cette case est cochée, les coordonnées géographiques seront mises à "
            "jour si l'adresse est correctement renseignée."
        ),
        required=False,
    )

    class Meta:
        model = PrescriberOrganization
        fields = "__all__"
