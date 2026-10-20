from django import template

register = template.Library()


@register.filter
def ya_other(meet_request, user):
    """L'autre personne d'une demande ou d'une conversation."""
    return meet_request.other(user)
