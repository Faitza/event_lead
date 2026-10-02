from django import forms
from django.contrib.auth import get_user_model

from .models import Event, EventCategory, EventEvaluation, Guest

CATEGORY_ICONS = [
    ("bi-heart", "Mariage"), ("bi-stars", "Gala"), ("bi-balloon", "Fête"), ("bi-droplet", "Baptême"),
    ("bi-mic", "Conférence"), ("bi-music-note-beamed", "Musique"), ("bi-cup-straw", "Soirée"),
    ("bi-trophy", "Sport"), ("bi-mortarboard", "Diplômes"), ("bi-briefcase", "Affaires"),
    ("bi-palette", "Art"), ("bi-film", "Cinéma"), ("bi-flower1", "Cérémonie"), ("bi-gift", "Cadeaux"),
    ("bi-people", "Rencontre"), ("bi-calendar2-event", "Autre"),
]


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = [
            "title", "event_type", "status", "date", "time", "venue", "latitude", "longitude",
            "max_guests", "allow_companions", "max_companions", "evaluation_delay_days",
            "price_htg", "description", "cover_image", "cover_video", "category",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "description": forms.Textarea(attrs={"rows": 4}),
            "latitude": forms.NumberInput(attrs={"step": "any", "readonly": "readonly"}),
            "longitude": forms.NumberInput(attrs={"step": "any", "readonly": "readonly"}),
            "venue": forms.TextInput(attrs={"placeholder": "Ex : Hôtel Montana, Pétion-Ville"}),
            "cover_image": forms.ClearableFileInput(attrs={"accept": "image/*"}),
            "cover_video": forms.ClearableFileInput(attrs={"accept": "video/*"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].empty_label = "Aucune catégorie"

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("allow_companions"):
            cleaned["max_companions"] = 0
        elif not cleaned.get("max_companions"):
            self.add_error("max_companions", "Indiquez le nombre maximum d'accompagnants.")
        lat, lng = cleaned.get("latitude"), cleaned.get("longitude")
        if lat is not None and not -90 <= lat <= 90:
            self.add_error("latitude", "Latitude invalide.")
        if lng is not None and not -180 <= lng <= 180:
            self.add_error("longitude", "Longitude invalide.")
        return cleaned


class EventCategoryForm(forms.ModelForm):
    icon_name = forms.ChoiceField(label="Icône", choices=CATEGORY_ICONS, widget=forms.RadioSelect)

    class Meta:
        model = EventCategory
        fields = ["name", "icon_name", "order"]
        widgets = {"name": forms.TextInput(attrs={"placeholder": "Ex : Mariage"})}
        help_texts = {"order": "Les petits numéros s'affichent en premier."}

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        clash = EventCategory.objects.filter(name__iexact=name).exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError("Une catégorie porte déjà ce nom.")
        return name


class GuestForm(forms.ModelForm):
    class Meta:
        model = Guest
        fields = ["event", "name", "email", "phone", "sent_via"]
        widgets = {
            "phone": forms.TextInput(attrs={"placeholder": "+509 ..."}),
            "sent_via": forms.RadioSelect,
        }

    def clean(self):
        cleaned = super().clean()
        email, phone, via = cleaned.get("email"), cleaned.get("phone"), cleaned.get("sent_via")
        if not email and not phone:
            raise forms.ValidationError("Renseignez au moins un e-mail ou un numéro de téléphone.")
        if via == Guest.Channel.EMAIL and not email:
            self.add_error("email", "Un e-mail est nécessaire pour un envoi par e-mail.")
        if via == Guest.Channel.WHATSAPP and not phone:
            self.add_error("phone", "Un numéro est nécessaire pour un envoi par WhatsApp.")
        event = cleaned.get("event")
        if event and not self.instance.pk and event.guests.count() >= event.max_guests:
            raise forms.ValidationError(
                f"Cet événement a atteint son nombre maximum d'invités ({event.max_guests})."
            )
        return cleaned

    def save(self, commit=True):
        guest = super().save(commit=False)
        if guest.email and not guest.user_id:
            guest.user = get_user_model().objects.filter(email__iexact=guest.email).first()
        if commit:
            guest.save()
        return guest


class PresenceForm(forms.Form):
    """Étape 1 du flux invité."""

    status = forms.ChoiceField(
        choices=[
            (Guest.Status.CONFIRMED, "Oui"),
            (Guest.Status.DECLINED, "Non"),
            (Guest.Status.MAYBE, "Peut-être"),
        ],
        widget=forms.RadioSelect,
        error_messages={"required": "Indiquez si vous serez présent."},
    )
    companions = forms.IntegerField(min_value=0, required=False, initial=0, label="Nombre d'accompagnants")

    def __init__(self, *args, event=None, **kwargs):
        self.event = event
        super().__init__(*args, **kwargs)
        max_c = event.max_companions if event and event.allow_companions else 0
        self.fields["companions"].max_value = max_c
        self.fields["companions"].widget.attrs.update({"min": 0, "max": max_c})

    def clean_companions(self):
        value = self.cleaned_data.get("companions") or 0
        if not (self.event and self.event.allow_companions):
            return 0
        if value > self.event.max_companions:
            raise forms.ValidationError(f"Maximum {self.event.max_companions} accompagnant(s).")
        return value

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("status") != Guest.Status.CONFIRMED:
            cleaned["companions"] = 0
        return cleaned


class GiftWishForm(forms.Form):
    """Étape 2 : souhaitez-vous envoyer un cadeau ?"""

    wants_gift = forms.TypedChoiceField(
        choices=[("yes", "Oui, je veux"), ("no", "Non merci")],
        coerce=lambda v: v == "yes",
        widget=forms.RadioSelect,
    )


class GiftSelectionForm(forms.Form):
    """Étape 3 : les cadeaux sont rendus manuellement ; on valide seulement les identifiants."""

    gifts = forms.TypedMultipleChoiceField(coerce=int, required=True, error_messages={
        "required": "Sélectionnez au moins un cadeau, ou revenez en arrière pour choisir « Non merci ».",
    })

    def __init__(self, *args, available_ids=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["gifts"].choices = [(i, i) for i in available_ids]


class EvaluationForm(forms.ModelForm):
    stars = forms.TypedChoiceField(
        label="Votre note", choices=[(i, f"{i} / 5") for i in range(5, 0, -1)], coerce=int, widget=forms.RadioSelect
    )

    class Meta:
        model = EventEvaluation
        fields = ["stars", "comment"]
        labels = {"comment": "Commentaire"}
        widgets = {"comment": forms.Textarea(attrs={"rows": 4, "placeholder": "Qu'avez-vous pensé de l'événement ?"})}
