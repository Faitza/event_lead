from django import forms
from django.utils.translation import gettext_lazy as _

from core.uploads import check_video, compress_photo

from .models import Ad, is_facebook_video, youtube_id

AD_ICONS = [
    ("bi-megaphone", _("Annonce")), ("bi-shop", _("Boutique")), ("bi-cup-straw", _("Boissons")), ("bi-camera", _("Photo")),
    ("bi-music-note-beamed", _("Musique")), ("bi-flower1", _("Fleuriste")), ("bi-car-front", _("Transport")),
    ("bi-building", _("Hôtel")), ("bi-bank", _("Banque")), ("bi-phone", _("Téléphonie")), ("bi-gem", _("Bijouterie")),
    ("bi-airplane", _("Voyage")), ("bi-cake2", _("Pâtisserie")), ("bi-stars", _("Beauté")),
]


class AdForm(forms.ModelForm):
    icon_name = forms.ChoiceField(label=_("Icône"), choices=AD_ICONS, widget=forms.RadioSelect)

    class Meta:
        model = Ad
        fields = ["advertiser", "advertiser_phone", "is_paid", "amount_htg", "start_date", "end_date", "title", "icon_name", "message", "image", "video", "video_url", "sponsor_link", "skip_after_seconds",
                  "is_active", "show_after_reply", "order"]
        widgets = {
            "message": forms.Textarea(attrs={"rows": 3}),
            "start_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "end_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "image": forms.ClearableFileInput(attrs={"accept": "image/*"}),
            "video": forms.ClearableFileInput(attrs={"accept": "video/*"}),
            "video_url": forms.URLInput(attrs={"placeholder": "https://www.youtube.com/watch?v=..."}),
            "sponsor_link": forms.URLInput(attrs={"placeholder": "https://"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["advertiser"].required = True
        self.fields["image"].help_text = _("JPEG, PNG ou WebP, 12 Mo au plus. L'image est réduite et allégée automatiquement.")
        self.fields["video"].help_text = _("MP4, WebM ou MOV, 40 Mo au plus. Jouée sans le son et en boucle ; l'image sert d'affiche avant qu'elle démarre.")
        self.fields["video_url"].help_text = _("Ou collez le lien d'une vidéo YouTube ou Facebook (utilisé s'il n'y a pas de fichier vidéo).")

    def clean_image(self):
        return compress_photo(self.cleaned_data.get("image"), max_side=1600)

    def clean_video(self):
        return check_video(self.cleaned_data.get("video"))

    def clean_video_url(self):
        url = (self.cleaned_data.get("video_url") or "").strip()
        if url and not (youtube_id(url) or is_facebook_video(url)):
            raise forms.ValidationError(_("Collez le lien d'une vidéo YouTube ou Facebook."))
        return url

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_date"), cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", _("La fin de diffusion doit venir après le début."))
        return cleaned

    def clean_skip_after_seconds(self):
        value = self.cleaned_data["skip_after_seconds"]
        if value > 30:
            raise forms.ValidationError(_("30 secondes maximum."))
        return value
