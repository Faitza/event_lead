from django import forms

from .models import Ad

AD_ICONS = [
    ("bi-megaphone", "Annonce"), ("bi-shop", "Boutique"), ("bi-cup-straw", "Boissons"), ("bi-camera", "Photo"),
    ("bi-music-note-beamed", "Musique"), ("bi-flower1", "Fleuriste"), ("bi-car-front", "Transport"),
    ("bi-building", "Hôtel"), ("bi-bank", "Banque"), ("bi-phone", "Téléphonie"), ("bi-gem", "Bijouterie"),
    ("bi-airplane", "Voyage"), ("bi-cake2", "Pâtisserie"), ("bi-stars", "Beauté"),
]


class AdForm(forms.ModelForm):
    icon_name = forms.ChoiceField(label="Icône", choices=AD_ICONS, widget=forms.RadioSelect)

    class Meta:
        model = Ad
        fields = ["title", "icon_name", "message", "image", "sponsor_link", "skip_after_seconds",
                  "is_active", "show_after_reply", "order"]
        widgets = {
            "message": forms.Textarea(attrs={"rows": 3}),
            "image": forms.ClearableFileInput(attrs={"accept": "image/*"}),
            "sponsor_link": forms.URLInput(attrs={"placeholder": "https://"}),
        }

    def clean_skip_after_seconds(self):
        value = self.cleaned_data["skip_after_seconds"]
        if value > 30:
            raise forms.ValidationError("30 secondes maximum.")
        return value
