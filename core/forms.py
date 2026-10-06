import re

from django import forms
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.core.validators import validate_email
from django.utils.translation import gettext_lazy as _

from .models import ContactMessage, HelpRequest, LogoVariant, Review
from .uploads import compress_photo


class ReviewForm(forms.ModelForm):
    stars = forms.TypedChoiceField(
        label=_("Votre note"), choices=[(i, f"{i} / 5") for i in range(5, 0, -1)], coerce=int,
        widget=forms.RadioSelect,
    )

    class Meta:
        model = Review
        fields = ["name", "stars", "text"]
        labels = {"name": _("Votre nom"), "text": _("Votre avis")}
        widgets = {"text": forms.Textarea(attrs={"rows": 3, "placeholder": _("Partagez votre expérience avec EventLead")})}


class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ["name", "email", "phone", "message"]
        labels = {"name": _("Nom complet"), "email": _("Adresse e-mail"), "phone": _("Téléphone"), "message": _("Message")}
        widgets = {"message": forms.Textarea(attrs={"rows": 4, "placeholder": _("Parlez-nous de votre événement")})}


class HelpRequestForm(forms.ModelForm):
    # Champ piège : invisible pour une personne, rempli par les robots.
    website = forms.CharField(required=False, label=_("Ne pas remplir"), widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))

    class Meta:
        model = HelpRequest
        fields = ["name", "contact", "topic", "message"]
        labels = {"name": _("Votre nom"), "contact": _("E-mail ou numéro WhatsApp"), "topic": _("Sujet"), "message": _("Votre question")}
        widgets = {
            "name": forms.TextInput(attrs={"autocomplete": "name"}),
            "contact": forms.TextInput(attrs={"placeholder": _("nom@exemple.com ou +509 ..."), "autocomplete": "email"}),
            "message": forms.Textarea(attrs={"rows": 5, "maxlength": 2000, "placeholder": _("Dites-nous ce qui se passe, avec le nom de l'événement si possible")}),
        }

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())

    def clean_contact(self):
        contact = " ".join(self.cleaned_data["contact"].split())
        if "@" in contact:
            try:
                validate_email(contact)
            except ValidationError:
                raise ValidationError(_("Cette adresse e-mail n'est pas valide."))
        elif not 8 <= len(re.sub(r"\D", "", contact)) <= 15:
            raise ValidationError(_("Indiquez une adresse e-mail ou un numéro de téléphone valide."))
        return contact


class LogoVariantForm(forms.ModelForm):
    """Version du logo pour une période : une couleur prête, ou son propre fichier PNG transparent."""

    class Meta:
        model = LogoVariant
        fields = ["name", "preset", "image", "image_dark", "start_date", "end_date", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": _("Noël 2026")}),
            "preset": forms.RadioSelect,
            "start_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"),
            "end_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"),
        }

    def _clean_logo(self, field):
        uploaded = self.cleaned_data.get(field)
        if isinstance(uploaded, UploadedFile):
            return compress_photo(uploaded, max_side=900)
        return uploaded

    def clean_image(self):
        return self._clean_logo("image")

    def clean_image_dark(self):
        return self._clean_logo("image_dark")

    def clean(self):
        data = super().clean()
        start, end = data.get("start_date"), data.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", _("La date de fin doit être après la date de début."))
        if data.get("preset") == LogoVariant.Preset.CUSTOM and not (data.get("image") or self.instance.image):
            self.add_error("image", _("Ajoutez votre fichier, ou choisissez une des couleurs prêtes."))
        return data
