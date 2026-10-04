from django import forms
from django.utils.translation import gettext_lazy as _

from core.uploads import compress_photo

from .models import Ad

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
        fields = ["title", "icon_name", "message", "image", "sponsor_link", "skip_after_seconds",
                  "is_active", "show_after_reply", "order"]
        widgets = {
            "message": forms.Textarea(attrs={"rows": 3}),
            "image": forms.ClearableFileInput(attrs={"accept": "image/*"}),
            "sponsor_link": forms.URLInput(attrs={"placeholder": "https://"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["image"].help_text = _("JPEG, PNG ou WebP, 12 Mo au plus. L'image est réduite et allégée automatiquement.")

    def clean_image(self):
        return compress_photo(self.cleaned_data.get("image"), max_side=1600)

    def clean_skip_after_seconds(self):
        value = self.cleaned_data["skip_after_seconds"]
        if value > 30:
            raise forms.ValidationError(_("30 secondes maximum."))
        return value
