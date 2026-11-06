"""Textes de Django réutilisés par le site (dates, validation des formulaires, mots de passe).

Ce fichier n'est jamais importé : il sert à `tools/i18n.py`, qui y relève les textes à traduire.
Django les utilise sous ces formes anglaises ; les traductions créoles sont dans locale/ht
(le français et l'anglais viennent déjà de Django).
"""
from django.utils.translation import gettext_noop, ngettext_lazy

# Mois et jours (filtre `date` des gabarits)
MONTHS = [
    gettext_noop("January"),
    gettext_noop("February"),
    gettext_noop("March"),
    gettext_noop("April"),
    gettext_noop("May"),
    gettext_noop("June"),
    gettext_noop("July"),
    gettext_noop("August"),
    gettext_noop("September"),
    gettext_noop("October"),
    gettext_noop("November"),
    gettext_noop("December"),
]
MONTHS_3 = [
    gettext_noop("jan"),
    gettext_noop("feb"),
    gettext_noop("mar"),
    gettext_noop("apr"),
    gettext_noop("may"),
    gettext_noop("jun"),
    gettext_noop("jul"),
    gettext_noop("aug"),
    gettext_noop("sep"),
    gettext_noop("oct"),
    gettext_noop("nov"),
    gettext_noop("dec"),
]
WEEKDAYS = [
    gettext_noop("Monday"),
    gettext_noop("Tuesday"),
    gettext_noop("Wednesday"),
    gettext_noop("Thursday"),
    gettext_noop("Friday"),
    gettext_noop("Saturday"),
    gettext_noop("Sunday"),
]
WEEKDAYS_ABBR = [
    gettext_noop("Mon"),
    gettext_noop("Tue"),
    gettext_noop("Wed"),
    gettext_noop("Thu"),
    gettext_noop("Fri"),
    gettext_noop("Sat"),
    gettext_noop("Sun"),
]

# Validation des formulaires
FORM_MESSAGES = [
    gettext_noop("This field is required."),
    gettext_noop("Enter a valid value."),
    gettext_noop("Enter a valid email address."),
    gettext_noop("Enter a valid URL."),
    gettext_noop("Enter a whole number."),
    gettext_noop("Enter a number."),
    gettext_noop("Enter a valid date."),
    gettext_noop("Enter a valid time."),
    gettext_noop("Enter a valid date/time."),
    gettext_noop("Select a valid choice. %(value)s is not one of the available choices."),
    gettext_noop("Select a valid choice. That choice is not one of the available choices."),
    gettext_noop("Ensure this value is greater than or equal to %(limit_value)s."),
    gettext_noop("Ensure this value is less than or equal to %(limit_value)s."),
    gettext_noop("The submitted file is empty."),
    gettext_noop("No file was submitted. Check the encoding type on the form."),
    gettext_noop("Upload a valid image. The file you uploaded was either not an image or a corrupted image."),
    gettext_noop("Please either submit a file or check the clear checkbox, not both."),
    gettext_noop("Clear"),
    gettext_noop("Currently"),
    gettext_noop("Change"),
    gettext_noop("This password is too common."),
    gettext_noop("This password is entirely numeric."),
    gettext_noop("The password is too similar to the %(verbose_name)s."),
]
FORM_PLURALS = [
    ngettext_lazy("Ensure this value has at least %(limit_value)d character (it has %(show_value)d).", "Ensure this value has at least %(limit_value)d characters (it has %(show_value)d).", "n"),
    ngettext_lazy("Ensure this value has at most %(limit_value)d character (it has %(show_value)d).", "Ensure this value has at most %(limit_value)d characters (it has %(show_value)d).", "n"),
    ngettext_lazy("This password is too short. It must contain at least %(min_length)d character.", "This password is too short. It must contain at least %(min_length)d characters.", "n"),
]
