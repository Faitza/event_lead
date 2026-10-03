from django import forms
from django.conf import settings
from django.contrib.auth import authenticate, password_validation
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from .models import CustomUser


class LoginForm(forms.Form):
    email = forms.EmailField(label=_("Adresse e-mail"), widget=forms.EmailInput(attrs={"autocomplete": "email", "placeholder": _("vous@exemple.com")}))
    password = forms.CharField(label=_("Mot de passe"), widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "placeholder": _("Votre mot de passe")}))

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        email, password = cleaned.get("email"), cleaned.get("password")
        if email and password:
            self.user = authenticate(self.request, email=email, password=password)
            if self.user is None:
                raise forms.ValidationError(_("E-mail ou mot de passe incorrect."))
        return cleaned


class RegisterForm(forms.ModelForm):
    password1 = forms.CharField(label=_("Mot de passe"), widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    password2 = forms.CharField(label=_("Confirmer le mot de passe"), widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    class Meta:
        model = CustomUser
        fields = ["first_name", "last_name", "email", "phone"]
        labels = {"first_name": _("Prénom"), "last_name": pgettext_lazy("nom de famille", "Nom"), "email": _("Adresse e-mail"), "phone": _("Téléphone (optionnel)")}
        widgets = {"phone": forms.TextInput(attrs={"placeholder": "+509 ..."})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_("Un compte existe déjà avec cette adresse e-mail."))
        return email

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", _("Les deux mots de passe ne correspondent pas."))
        if p1:
            user = CustomUser(email=cleaned.get("email"), first_name=cleaned.get("first_name", ""))
            try:
                password_validation.validate_password(p1, user)
            except forms.ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned

    def save(self, commit=True, role=CustomUser.Role.GUEST):
        user = super().save(commit=False)
        user.username = user.email
        user.role = role
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class ProfileForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ["first_name", "last_name", "phone", "language", "avatar"]
        labels = {
            "first_name": _("Prénom"), "last_name": pgettext_lazy("nom de famille", "Nom"), "phone": _("Téléphone"),
            "language": _("Langue de l'interface"), "avatar": _("Photo de profil"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["language"].choices = [("", _("Automatique (langue du navigateur)"))] + list(settings.LANGUAGES)
