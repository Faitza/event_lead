import re

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from .models import ContactMessage, HelpRequest, Review


class ReviewForm(forms.ModelForm):
    stars = forms.TypedChoiceField(
        label="Votre note", choices=[(i, f"{i} / 5") for i in range(5, 0, -1)], coerce=int,
        widget=forms.RadioSelect,
    )

    class Meta:
        model = Review
        fields = ["name", "stars", "text"]
        labels = {"name": "Votre nom", "text": "Votre avis"}
        widgets = {"text": forms.Textarea(attrs={"rows": 3, "placeholder": "Partagez votre expérience avec EventLead"})}


class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ["name", "email", "phone", "message"]
        labels = {"name": "Nom complet", "email": "Adresse e-mail", "phone": "Téléphone", "message": "Message"}
        widgets = {"message": forms.Textarea(attrs={"rows": 4, "placeholder": "Parlez-nous de votre événement"})}


class HelpRequestForm(forms.ModelForm):
    # Champ piège : invisible pour une personne, rempli par les robots.
    website = forms.CharField(required=False, label="Ne pas remplir", widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))

    class Meta:
        model = HelpRequest
        fields = ["name", "contact", "topic", "message"]
        labels = {"name": "Votre nom", "contact": "E-mail ou numéro WhatsApp", "topic": "Sujet", "message": "Votre question"}
        widgets = {
            "name": forms.TextInput(attrs={"autocomplete": "name"}),
            "contact": forms.TextInput(attrs={"placeholder": "nom@exemple.com ou +509 ...", "autocomplete": "email"}),
            "message": forms.Textarea(attrs={"rows": 5, "maxlength": 2000, "placeholder": "Dites-nous ce qui se passe, avec le nom de l'événement si possible"}),
        }

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())

    def clean_contact(self):
        contact = " ".join(self.cleaned_data["contact"].split())
        if "@" in contact:
            try:
                validate_email(contact)
            except ValidationError:
                raise ValidationError("Cette adresse e-mail n'est pas valide.")
        elif not 8 <= len(re.sub(r"\D", "", contact)) <= 15:
            raise ValidationError("Indiquez une adresse e-mail ou un numéro de téléphone valide.")
        return contact
