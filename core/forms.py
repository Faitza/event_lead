from django import forms

from .models import ContactMessage, Review


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
