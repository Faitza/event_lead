from django import forms
from django.utils.translation import gettext_lazy as _

from core.forms import honeypot_field
from core.uploads import compress_photo

from .models import ABOUT_MAX, MESSAGE_MAX, NOTE_MAX, Profile, Report


class ProfileForm(forms.ModelForm):
    """Petit profil + choix pour l'événement + 18 ans + règles, sur un seul écran."""

    website = honeypot_field()
    wants_company = forms.BooleanField(label=_("Quelqu'un pour y aller"), required=False, initial=True)
    wants_transport = forms.BooleanField(label=_("Partager le transport"), required=False)
    wants_group = forms.BooleanField(label=_("Un groupe d'amis"), required=False)
    adult = forms.BooleanField(label=_("J'ai 18 ans ou plus."), error_messages={"required": _("Cette partie est réservée aux personnes de 18 ans ou plus.")})
    rules = forms.BooleanField(label=_("J'accepte les règles et les conditions d'utilisation."), error_messages={"required": _("Acceptez les règles pour continuer.")})

    class Meta:
        model = Profile
        fields = ["first_name", "city", "about", "photo"]
        labels = {"first_name": _("Prénom affiché"), "city": _("Ville"), "about": _("Quelques mots"), "photo": _("Photo")}
        help_texts = {
            "first_name": _("Votre nom de famille n'est jamais montré."),
            "about": _("200 caractères au plus."),
            "photo": _("Facultatif. Une photo de vous, sans autre personne."),
        }
        widgets = {
            "about": forms.Textarea(attrs={"rows": 3, "maxlength": ABOUT_MAX}),
            "photo": forms.FileInput(attrs={"accept": "image/*"}),
        }

    def __init__(self, *args, listing=None, **kwargs):
        super().__init__(*args, **kwargs)
        if listing is not None:
            for name in ("wants_company", "wants_transport", "wants_group"):
                self.fields[name].initial = getattr(listing, name)
        if self.instance.pk:
            self.fields["adult"].initial = True
            self.fields["rules"].initial = True

    def clean_photo(self):
        return compress_photo(self.cleaned_data.get("photo"), max_side=600)

    def clean(self):
        data = super().clean()
        if not any(data.get(n) for n in ("wants_company", "wants_transport", "wants_group")):
            raise forms.ValidationError(_("Cochez au moins une chose que vous cherchez."))
        return data

    def listing_values(self):
        return {n: self.cleaned_data[n] for n in ("wants_company", "wants_transport", "wants_group")}


class RequestForm(forms.Form):
    website = honeypot_field()
    note = forms.CharField(label=_("Un petit mot (facultatif)"), required=False, max_length=NOTE_MAX,
                           widget=forms.Textarea(attrs={"rows": 3, "maxlength": NOTE_MAX}))


class MessageForm(forms.Form):
    body = forms.CharField(label=_("Message"), max_length=MESSAGE_MAX,
                           widget=forms.TextInput(attrs={"placeholder": _("Écrire un message..."), "maxlength": MESSAGE_MAX, "autocomplete": "off"}))


class ReportForm(forms.Form):
    reason = forms.ChoiceField(label=_("Raison"), choices=Report.Reason.choices, widget=forms.RadioSelect(attrs={"class": "form-check-input"}), initial=Report.Reason.HARASSMENT)
    details = forms.CharField(label=_("Explication"), required=False, max_length=500,
                              widget=forms.Textarea(attrs={"rows": 2, "maxlength": 500, "placeholder": _("Expliquez en quelques mots (facultatif)")}))
    also_block = forms.BooleanField(label=_("Bloquer aussi cette personne"), required=False, initial=True)


LISTING_FILTERS = {
    "transport": "wants_transport",
    "groupe": "wants_group",
}
