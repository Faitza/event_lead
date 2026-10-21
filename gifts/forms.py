from django import forms
from django.utils.translation import gettext_lazy as _

from .models import GIFT_ICONS, Gift


class GiftForm(forms.ModelForm):
    icon_name = forms.ChoiceField(label=_("Icône"), choices=GIFT_ICONS, widget=forms.RadioSelect)

    class Meta:
        model = Gift
        fields = ["event", "name", "icon_name", "quantity"]
        labels = {"name": _("Nom du cadeau"), "quantity": _("Quantité")}
        widgets = {"name": forms.TextInput(attrs={"placeholder": _("Ex : Service à café")})}

    def clean_quantity(self):
        qty = self.cleaned_data["quantity"]
        if qty < 1:
            raise forms.ValidationError(_("La quantité doit être d'au moins 1."))
        if self.instance.pk:
            taken = self.instance.claims.count()
            if qty < taken:
                raise forms.ValidationError(
                    _("%(taken)d unité(s) déjà choisie(s) : la quantité ne peut pas être inférieure.") % {"taken": taken}
                )
        return qty

    def clean_event(self):
        event = self.cleaned_data["event"]
        if self.instance.pk and self.instance.event_id != event.pk and self.instance.claims.exists():
            raise forms.ValidationError(_("Ce cadeau a déjà été choisi : il ne peut pas changer d'événement."))
        return event
