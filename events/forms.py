from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from django.utils.translation import gettext_lazy as _

from core.uploads import check_video, compress_photo

from .album import AlbumError, tile_photo
from .models import Event, EventCategory, EventEvaluation, Guest

CATEGORY_ICONS = [
    ("bi-heart", _("Mariage")), ("bi-stars", _("Gala")), ("bi-balloon", _("Fête")), ("bi-balloon-heart", _("Baby shower")),
    ("bi-droplet", _("Baptême")),
    ("bi-mic", _("Conférence")), ("bi-music-note-beamed", _("Musique")), ("bi-cup-straw", _("Soirée")),
    ("bi-trophy", _("Sport")), ("bi-mortarboard", _("Diplômes")), ("bi-briefcase", _("Affaires")),
    ("bi-palette", _("Art")), ("bi-film", _("Cinéma")), ("bi-flower1", _("Cérémonie")), ("bi-gift", _("Cadeaux")),
    ("bi-people", _("Rencontre")), ("bi-calendar2-event", _("Autre")),
]


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = [
            "title", "event_type", "status", "date", "time", "venue", "latitude", "longitude",
            "max_guests", "allow_companions", "max_companions", "evaluation_delay_days",
            "accept_contributions", "price_htg", "description", "cover_image", "cover_video", "category",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "description": forms.Textarea(attrs={"rows": 4}),
            "latitude": forms.NumberInput(attrs={"step": "any", "readonly": "readonly"}),
            "longitude": forms.NumberInput(attrs={"step": "any", "readonly": "readonly"}),
            "venue": forms.TextInput(attrs={"placeholder": _("Ex : Hôtel Montana, Pétion-Ville")}),
            "cover_image": forms.ClearableFileInput(attrs={"accept": "image/*"}),
            "cover_video": forms.ClearableFileInput(attrs={"accept": "video/*"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].empty_label = _("Aucune catégorie")
        self.fields["category"].label_from_instance = lambda c: c.label
        self.fields["cover_image"].help_text = _("JPEG, PNG ou WebP, 12 Mo au plus. La photo est réduite et allégée automatiquement.")
        self.fields["cover_video"].help_text = _("MP4, WebM ou MOV, 40 Mo au plus.")

    def clean_cover_image(self):
        return compress_photo(self.cleaned_data.get("cover_image"))

    def clean_cover_video(self):
        return check_video(self.cleaned_data.get("cover_video"))

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("allow_companions"):
            cleaned["max_companions"] = 0
        elif not cleaned.get("max_companions"):
            self.add_error("max_companions", _("Indiquez le nombre maximum d'accompagnants."))
        lat, lng = cleaned.get("latitude"), cleaned.get("longitude")
        if lat is not None and not -90 <= lat <= 90:
            self.add_error("latitude", _("Latitude invalide."))
        if lng is not None and not -180 <= lng <= 180:
            self.add_error("longitude", _("Longitude invalide."))
        return cleaned


class EventCategoryForm(forms.ModelForm):
    icon_name = forms.ChoiceField(label=_("Icône"), choices=CATEGORY_ICONS, widget=forms.RadioSelect)
    image = forms.ImageField(
        label=_("Photo de la tuile"), required=False,
        widget=forms.FileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
        help_text=_("Affichée sur l'accueil, recadrée en 4/3 (au moins 480 x 360 pixels). Sans photo, un décor violet avec l'icône s'affiche."),
    )
    remove_image = forms.BooleanField(label=_("Retirer la photo actuelle"), required=False)

    class Meta:
        model = EventCategory
        fields = ["name", "icon_name", "order", "image"]
        widgets = {"name": forms.TextInput(attrs={"placeholder": _("Ex : Mariage")})}
        help_texts = {"order": _("Les petits numéros s'affichent en premier.")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._old_image = self.instance.image.name if self.instance.pk and self.instance.image else ""

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        clash = EventCategory.objects.filter(name__iexact=name).exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError(_("Une catégorie porte déjà ce nom."))
        return name

    def clean_image(self):
        uploaded = self.cleaned_data.get("image")
        if isinstance(uploaded, UploadedFile):
            try:
                return tile_photo(uploaded)
            except AlbumError as error:
                raise forms.ValidationError(str(error))
        return uploaded

    def save(self, commit=True):
        category = super().save(commit=False)
        if self.cleaned_data.get("remove_image") and not isinstance(self.cleaned_data.get("image"), ContentFile):
            category.image = ""
        if commit:
            category.save()
            if self._old_image and self._old_image != (category.image.name if category.image else ""):
                category.image.storage.delete(self._old_image)  # l'ancienne photo ne reste pas sur le disque
        return category


class GuestForm(forms.ModelForm):
    class Meta:
        model = Guest
        fields = ["event", "name", "email", "phone", "language", "sent_via"]
        widgets = {
            "phone": forms.TextInput(attrs={"placeholder": "+509 ..."}),
            "sent_via": forms.RadioSelect,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["language"].required = False

    def clean_language(self):
        return self.cleaned_data.get("language") or settings.LANGUAGE_CODE

    def clean(self):
        cleaned = super().clean()
        email, phone, via = cleaned.get("email"), cleaned.get("phone"), cleaned.get("sent_via")
        if not email and not phone:
            raise forms.ValidationError(_("Renseignez au moins un e-mail ou un numéro de téléphone."))
        if via == Guest.Channel.EMAIL and not email:
            self.add_error("email", _("Un e-mail est nécessaire pour un envoi par e-mail."))
        if via == Guest.Channel.WHATSAPP and not phone:
            self.add_error("phone", _("Un numéro est nécessaire pour un envoi par WhatsApp."))
        event = cleaned.get("event")
        if event and not self.instance.pk and event.guests.count() >= event.max_guests:
            raise forms.ValidationError(
                _("Cet événement a atteint son nombre maximum d'invités (%(max)d).") % {"max": event.max_guests}
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
            (Guest.Status.CONFIRMED, _("Oui")),
            (Guest.Status.DECLINED, _("Non")),
            (Guest.Status.MAYBE, _("Peut-être")),
        ],
        widget=forms.RadioSelect,
        error_messages={"required": _("Indiquez si vous serez présent.")},
    )
    companions = forms.IntegerField(min_value=0, required=False, initial=0, label=_("Nombre d'accompagnants"))

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
            raise forms.ValidationError(_("Maximum %(max)d accompagnant(s).") % {"max": self.event.max_companions})
        return value

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("status") != Guest.Status.CONFIRMED:
            cleaned["companions"] = 0
        return cleaned


class GiftWishForm(forms.Form):
    """Étape 2 : souhaitez-vous envoyer un cadeau ?"""

    wants_gift = forms.TypedChoiceField(
        choices=[("yes", _("Oui, je veux")), ("no", _("Non merci"))],
        coerce=lambda v: v == "yes",
        widget=forms.RadioSelect,
    )


class GiftSelectionForm(forms.Form):
    """Étape 3 : les cadeaux sont rendus manuellement ; on valide seulement les identifiants."""

    gifts = forms.TypedMultipleChoiceField(coerce=int, required=True, error_messages={
        "required": _("Sélectionnez au moins un cadeau, ou revenez en arrière pour choisir « Non merci »."),
    })

    def __init__(self, *args, available_ids=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["gifts"].choices = [(i, i) for i in available_ids]


class EvaluationForm(forms.ModelForm):
    stars = forms.TypedChoiceField(
        label=_("Votre note"), choices=[(i, f"{i} / 5") for i in range(5, 0, -1)], coerce=int, widget=forms.RadioSelect
    )

    class Meta:
        model = EventEvaluation
        fields = ["stars", "comment"]
        labels = {"comment": _("Commentaire")}
        widgets = {"comment": forms.Textarea(attrs={"rows": 4, "placeholder": _("Qu'avez-vous pensé de l'événement ?")})}
