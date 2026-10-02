"""Questions fréquentes de la page Aide, classées par profil.

Chaque question a un identifiant stable : les petites aides du parcours (invitation, paiement)
renvoient vers `/aide/#faq-<identifiant>`. Les réponses décrivent ce que fait le site aujourd'hui.
"""

HELP_PROFILES = [
    {
        "key": "invite",
        "title": "Invité ou visiteur",
        "icon": "bi-envelope-heart",
        "intro": "Vous avez reçu une invitation, ou vous voulez réserver un billet.",
        "questions": [
            ("invite-sans-compte", "Dois-je créer un compte pour répondre à une invitation ?",
             "Non. Le lien personnel reçu par WhatsApp ou par e-mail suffit : pas de compte, pas de mot de passe, "
             "pas d'application. Ouvrez le lien et répondez."),
            ("invite-lien-perdu", "J'ai perdu mon lien, ou il ne s'ouvre pas.",
             "Retrouvez le message d'invitation dans WhatsApp ou dans votre boîte e-mail (regardez aussi les "
             "courriers indésirables). Si vous ne le trouvez plus, demandez-le à la personne qui vous a invité(e) "
             "ou écrivez-nous avec le formulaire de cette page."),
            ("invite-modifier", "Puis-je changer ma réponse ?",
             "Oui, tant que vous n'avez pas confirmé votre présence : revenez simplement sur votre lien. Une fois "
             "la présence confirmée, la réponse est définitive."),
            ("invite-accompagnants", "Puis-je venir avec quelqu'un ?",
             "Cela dépend de l'événement. Si l'hôte accepte les accompagnants, vous indiquez leur nombre en "
             "répondant, jusqu'au maximum prévu. Sinon, la question n'apparaît pas."),
            ("invite-cadeau", "Comment choisir un cadeau ?",
             "Après avoir confirmé votre présence, si l'hôte a préparé une liste de cadeaux, vous cochez ceux que "
             "vous voulez offrir. Un cadeau choisi est aussitôt réservé pour vous : personne d'autre ne peut le "
             "prendre. Votre choix est définitif."),
            ("invite-cadeau-disparu", "Un cadeau a disparu de la liste. Pourquoi ?",
             "Un autre invité l'a choisi avant vous et il n'en reste plus. La liste se met à jour toute seule : "
             "choisissez simplement un autre cadeau."),
            ("invite-publicite", "Pourquoi une publicité s'affiche-t-elle après ma réponse ?",
             "Après votre réponse, nous présentons les publications de nos partenaires. Un bouton « Passer » "
             "apparaît après un court compte à rebours, puis vous arrivez sur l'accueil, où se trouvent les "
             "événements publics."),
            ("paiement-moncash", "Comment payer un billet avec MonCash ?",
             "Choisissez MonCash, saisissez votre numéro puis demandez le code de confirmation : il vous arrive par "
             "SMS. Saisissez-le pour valider. Le prix est en gourdes."),
            ("paiement-natcash", "Comment payer avec NatCash ?",
             "Choisissez NatCash, saisissez votre numéro puis le code PIN à 4 chiffres de votre compte NatCash."),
            ("paiement-carte", "Et avec une carte bancaire ou PayPal ?",
             "La carte (Visa, Mastercard) est débitée en dollars. Le montant en dollars est affiché avant que vous "
             "payiez, à côté du prix en gourdes."),
            ("paiement-reference", "J'ai payé : que dois-je conserver ?",
             "Conservez la référence de transaction affichée à la fin du paiement. Si le paiement a échoué ou si "
             "un doute persiste, écrivez-nous en indiquant cette référence."),
        ],
    },
    {
        "key": "vip",
        "title": "Organisateur VIP",
        "icon": "bi-gem",
        "intro": "Vous avez un compte Organisateur, ou vous voulez en ouvrir un.",
        "questions": [
            ("vip-quoi", "Qu'est-ce que l'accès Organisateur VIP ?",
             "C'est un accès payant, en paiement unique, au portail Organisateur : le détail de tous les événements "
             "publics, les événements privés auxquels vous êtes invité(e), et l'évaluation d'un événement une fois "
             "terminé. Le portail est en lecture seule : la création et la gestion des événements restent "
             "assurées par l'équipe EventLead."),
            ("vip-devenir", "Comment devenir Organisateur VIP ?",
             "Cliquez sur « Devenir VIP », créez votre compte Organisateur, puis réglez l'accès VIP avec MonCash, "
             "NatCash, carte ou PayPal. Le portail s'ouvre dès que le paiement est confirmé. Le montant est affiché "
             "sur la page de paiement, en gourdes et en dollars."),
            ("vip-evaluation", "Comment évaluer un événement ?",
             "Une fois l'événement passé et le délai prévu écoulé, un bouton « Évaluer » apparaît dans votre portail "
             "pour les événements privés où vous avez confirmé votre présence : une note de 1 à 5 étoiles et un "
             "commentaire. Chaque événement ne peut être évalué qu'une fois."),
            ("vip-evenement-absent", "Je ne vois pas un événement privé dans mon portail.",
             "Un événement privé n'apparaît que si vous y êtes invité(e). Écrivez-nous avec le nom de l'événement : "
             "nous vérifierons que l'invitation est bien liée à votre compte."),
        ],
    },
    {
        "key": "admin",
        "title": "Équipe EventLead",
        "icon": "bi-speedometer2",
        "intro": "Pour les administrateurs qui organisent les événements dans le tableau de bord.",
        "questions": [
            ("admin-creer", "Comment créer un événement ?",
             "Dans le tableau de bord, ouvrez Événements puis « Nouvel événement » : titre, type (public ou privé), "
             "catégorie, date, lieu (localisé sur la carte), nombre maximum d'invités, accompagnants autorisés et "
             "photo de couverture."),
            ("admin-inviter", "Comment envoyer les invitations ?",
             "Ajoutez vos invités dans Invités, avec une adresse e-mail ou un numéro WhatsApp. Chaque invité a un "
             "lien personnel : un bouton ouvre WhatsApp ou votre messagerie avec le message déjà écrit, et vous "
             "l'envoyez vous-même. Marquez ensuite l'invitation comme envoyée."),
            ("admin-suivi", "Comment suivre les réponses ?",
             "La page de suivi de chaque événement se met à jour avec les présences, les accompagnants et les "
             "cadeaux choisis. Les invités et les cadeaux s'exportent en CSV, les invités aussi en PDF."),
            ("admin-categories", "Comment classer les événements ?",
             "Dans Catégories, créez, renommez ou supprimez des catégories, puis choisissez-en une dans le "
             "formulaire de l'événement. Elle apparaît en badge sur la carte de l'événement et dans les filtres "
             "du site."),
            ("admin-aide", "Où voir les demandes d'aide ?",
             "Dans Demandes d'aide : chaque demande a un statut (nouvelle, en cours, résolue), et la liste "
             "s'exporte en CSV."),
        ],
    },
]
