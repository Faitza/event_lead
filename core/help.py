"""Questions fréquentes de la page Aide, classées par profil.

Chaque question a un identifiant stable : les petites aides du parcours (invitation, paiement)
renvoient vers `/aide/#faq-<identifiant>`. Les réponses décrivent ce que fait le site aujourd'hui.
"""

from datetime import date

from django.utils.translation import gettext_lazy as _

# Date affichée en haut de la page Aide : à changer quand une question ou une réponse change
HELP_UPDATED = date(2026, 10, 6)

HELP_PROFILES = [
    {
        "key": "invite",
        "title": _("Invité ou visiteur"),
        "icon": "bi-envelope-heart",
        "intro": _("Vous avez reçu une invitation, ou vous voulez réserver un billet."),
        "questions": [
            ("invite-sans-compte", _("Dois-je créer un compte pour répondre à une invitation ?"),
             _("Non. Le lien personnel reçu par WhatsApp ou par e-mail suffit : pas de compte, pas de mot de passe, "
               "pas d'application. Ouvrez le lien et répondez.")),
            ("invite-lien-perdu", _("J'ai perdu mon lien, ou il ne s'ouvre pas."),
             _("Retrouvez le message d'invitation dans WhatsApp ou dans votre boîte e-mail (regardez aussi les "
               "courriers indésirables). Si vous ne le trouvez plus, demandez-le à la personne qui vous a invité(e) "
               "ou écrivez-nous avec le formulaire de cette page.")),
            ("invite-modifier", _("Puis-je changer ma réponse ?"),
             _("Oui, tant que vous n'avez pas confirmé votre présence : revenez simplement sur votre lien. Une fois "
               "la présence confirmée, la réponse est définitive.")),
            ("invite-accompagnants", _("Puis-je venir avec quelqu'un ?"),
             _("Cela dépend de l'événement. Si l'hôte accepte les accompagnants, vous indiquez leur nombre en "
               "répondant, jusqu'au maximum prévu. Sinon, la question n'apparaît pas.")),
            ("invite-cadeau", _("Comment choisir un cadeau ?"),
             _("Après avoir confirmé votre présence, si l'hôte a préparé une liste de cadeaux, vous cochez ceux que "
               "vous voulez offrir. Un cadeau choisi est aussitôt réservé pour vous : personne d'autre ne peut le "
               "prendre. Votre choix est définitif.")),
            ("invite-cadeau-disparu", _("Un cadeau a disparu de la liste. Pourquoi ?"),
             _("Un autre invité l'a choisi avant vous et il n'en reste plus. La liste se met à jour toute seule : "
               "choisissez simplement un autre cadeau.")),
            ("invite-publicite", _("Pourquoi une publicité s'affiche-t-elle après ma réponse ?"),
             _("Après votre réponse, nous présentons les publications de nos partenaires. Un bouton « Passer » "
               "apparaît après un court compte à rebours, puis vous arrivez sur l'accueil, où se trouvent les "
               "événements publics.")),
            ("paiement-moncash", _("Comment payer un billet avec MonCash ?"),
             _("Choisissez MonCash, saisissez votre numéro puis demandez le code de confirmation : il vous arrive par "
               "SMS. Saisissez-le pour valider. Le prix est en gourdes.")),
            ("paiement-natcash", _("Comment payer avec NatCash ?"),
             _("Choisissez NatCash, saisissez votre numéro puis le code PIN à 4 chiffres de votre compte NatCash.")),
            ("paiement-carte", _("Et avec une carte bancaire ou PayPal ?"),
             _("La carte (Visa, Mastercard) est débitée en dollars. Le montant en dollars est affiché avant que vous "
               "payiez, à côté du prix en gourdes.")),
            ("paiement-reference", _("J'ai payé : que dois-je conserver ?"),
             _("Conservez la référence de transaction affichée à la fin du paiement. Si le paiement a échoué ou si "
               "un doute persiste, écrivez-nous en indiquant cette référence.")),
        ],
    },
    {
        "key": "vip",
        "title": _("Organisateur VIP"),
        "icon": "bi-gem",
        "intro": _("Vous avez un compte Organisateur, ou vous voulez en ouvrir un."),
        "questions": [
            ("vip-quoi", _("Qu'est-ce que l'accès Organisateur VIP ?"),
             _("C'est un accès payant, en paiement unique, au portail Organisateur : le détail de tous les événements "
               "publics, les événements privés auxquels vous êtes invité(e), et l'évaluation d'un événement une fois "
               "terminé. Le portail est en lecture seule : la création et la gestion des événements restent "
               "assurées par l'équipe EventLead.")),
            ("vip-devenir", _("Comment devenir Organisateur VIP ?"),
             _("Cliquez sur « Devenir VIP », créez votre compte Organisateur, puis réglez l'accès VIP avec MonCash, "
               "NatCash, carte ou PayPal. Le portail s'ouvre dès que le paiement est confirmé. Le montant est affiché "
               "sur la page de paiement, en gourdes et en dollars.")),
            ("vip-evaluation", _("Comment évaluer un événement ?"),
             _("Une fois l'événement passé et le délai prévu écoulé, un bouton « Évaluer » apparaît dans votre portail "
               "pour les événements privés où vous avez confirmé votre présence : une note de 1 à 5 étoiles et un "
               "commentaire. Chaque événement ne peut être évalué qu'une fois.")),
            ("vip-evenement-absent", _("Je ne vois pas un événement privé dans mon portail."),
             _("Un événement privé n'apparaît que si vous y êtes invité(e). Écrivez-nous avec le nom de l'événement : "
               "nous vérifierons que l'invitation est bien liée à votre compte.")),
        ],
    },
    {
        "key": "admin",
        "title": _("Équipe EventLead"),
        "icon": "bi-speedometer2",
        "intro": _("Pour les administrateurs qui organisent les événements dans le tableau de bord."),
        "questions": [
            ("admin-creer", _("Comment créer un événement ?"),
             _("Dans le tableau de bord, ouvrez Événements puis « Nouvel événement » : titre, type (public ou privé), "
               "catégorie, date, lieu (localisé sur la carte), nombre maximum d'invités, accompagnants autorisés et "
               "photo de couverture.")),
            ("admin-inviter", _("Comment envoyer les invitations ?"),
             _("Ajoutez vos invités dans Invités, avec une adresse e-mail ou un numéro WhatsApp. Chaque invité a un "
               "lien personnel : un bouton ouvre WhatsApp ou votre messagerie avec le message déjà écrit, et vous "
               "l'envoyez vous-même. Marquez ensuite l'invitation comme envoyée.")),
            ("admin-suivi", _("Comment suivre les réponses ?"),
             _("La page de suivi de chaque événement se met à jour avec les présences, les accompagnants et les "
               "cadeaux choisis. Les invités et les cadeaux s'exportent en CSV, les invités aussi en PDF.")),
            ("admin-categories", _("Comment classer les événements ?"),
             _("Dans Catégories, créez, renommez ou supprimez des catégories, puis choisissez-en une dans le "
               "formulaire de l'événement. Elle apparaît en badge sur la carte de l'événement et dans les filtres "
               "du site.")),
            ("admin-aide", _("Où voir les demandes d'aide ?"),
             _("Dans Demandes d'aide : chaque demande a un statut (nouvelle, en cours, résolue), et la liste "
               "s'exporte en CSV.")),
        ],
    },
]
