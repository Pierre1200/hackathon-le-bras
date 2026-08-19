"""
tools.py — les outils reels que l'agent peut appeler.

Deux outils branches pour le palier "outils" : un outil de LECTURE (interroge
une vraie base SQLite) et un outil d'ECRITURE (ecrit un vrai fichier sur
disque, dans outbox/). Aucun des deux n'est mocke : la base et le dossier
sont accedes pour de vrai, avec de vraies erreurs possibles — pas de valeur
codee en dur qui fait semblant de repondre.

Chaque outil expose :
  - une fonction Python avec une signature typee (executee reellement)
  - un schema JSON (SCHEMA_*) qui decrit cette meme fonction pour le modele,
    au format "tools" de l'API compatible OpenAI. C'est CE texte que le
    modele lit pour choisir quel outil appeler : une description vague donne
    un routage vague.

OUTILS est la table de dispatch utilisee par la boucle d'appel d'outils dans
llm.py : {nom_outil: fonction}. Un nom absent de ce dict (outil "debranche",
volontairement ou par erreur du modele) ne fait pas planter le serveur —
voir appeler_outil() plus bas : c'est le seul point d'entree, et il ne laisse
jamais une exception remonter.
"""

import logging
import os
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Meme fichier .env que llm.py, chargee independamment pour que ce module
# reste utilisable seul (tests, script manuel) sans dependre de l'ordre
# d'import avec llm.py.
RACINE = Path(__file__).parent.parent
load_dotenv(RACINE / ".env")

logger = logging.getLogger("le_bras.outils")

DB_PATH = RACINE / os.getenv("DATABASE_URL", "sqlite:///./lebras.db").removeprefix("sqlite:///")
OUTBOX_DIR = RACINE / os.getenv("OUTBOX_DIR", "./outbox")
# Ou atterrissent les documents generes (fiches d'accueil, recapitulatifs).
DOCS_DIR = RACINE / os.getenv("DOCS_DIR", "./documents")


def _connexion() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def _sans_accents(texte: str) -> str:
    """
    Met un texte en minuscules et lui retire ses accents, pour pouvoir
    comparer deux chaines sans se soucier de la frappe de l'utilisateur.

    Pourquoi c'est necessaire : on a decouvert en testant que "le mail de
    Chloe" ne trouvait rien, parce que la base contient "Chloe" sans accent.
    Un utilisateur ecrit "Chloe", "Ingenierie" ou "ingenierie" indifferemment.
    Sans cette normalisation, l'agent repondrait que la personne n'existe pas.

    Comment ca marche : NFD separe chaque lettre accentuee en deux caracteres
    (la lettre nue, puis l'accent). On supprime ensuite tout ce qui est un
    accent — categorie Unicode "Mn", pour "Mark, nonspacing".
    """
    decompose = unicodedata.normalize("NFD", texte)
    return "".join(c for c in decompose if unicodedata.category(c) != "Mn").lower()


def _initialiser_base() -> None:
    """Cree la table employes et la peuple si elle est vide. Idempotent :
    on peut relancer le serveur autant de fois qu'on veut sans dupliquer."""
    with _connexion() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS employes (
                id INTEGER PRIMARY KEY,
                nom TEXT NOT NULL,
                role TEXT NOT NULL,
                departement TEXT NOT NULL,
                email TEXT NOT NULL
            )
            """
        )
        # MIGRATION : les premieres versions de la table n'avaient pas de
        # colonne date_arrivee. CREATE TABLE IF NOT EXISTS ne la rajoute pas
        # sur une base deja creee — il faut donc l'ajouter a la main si elle
        # manque. Sans ca, l'app planterait chez celui qui a une vieille base.
        colonnes = {ligne[1] for ligne in db.execute("PRAGMA table_info(employes)")}
        if "date_arrivee" not in colonnes:
            db.execute("ALTER TABLE employes ADD COLUMN date_arrivee TEXT DEFAULT ''")

        # Les tickets d'onboarding, crees par creer_ticket.
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY,
                titre TEXT NOT NULL,
                description TEXT NOT NULL,
                assigne_a TEXT NOT NULL,
                cree_le TEXT NOT NULL
            )
            """
        )

        (nb,) = db.execute("SELECT COUNT(*) FROM employes").fetchone()
        if nb == 0:
            db.executemany(
                "INSERT INTO employes (nom, role, departement, email) VALUES (?, ?, ?, ?)",
                [
                    ("Alice Dupont", "Lead backend", "Ingenierie", "alice.dupont@lebras.fr"),
                    ("Bruno Martin", "Ingenieur backend", "Ingenierie", "bruno.martin@lebras.fr"),
                    ("Chloe Bernard", "Designer produit", "Design", "chloe.bernard@lebras.fr"),
                    ("David Petit", "Charge de recrutement", "RH", "david.petit@lebras.fr"),
                    ("Emma Roux", "Responsable marketing", "Marketing", "emma.roux@lebras.fr"),
                ],
            )


_initialiser_base()
OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
DOCS_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# LES OUTILS — signatures typees, executees pour de vrai
# =============================================================================

def lister_equipe(departement: str) -> list[dict]:
    """Cherche les membres d'un departement dans l'annuaire SQLite (recherche
    partielle, insensible a la casse). Renvoie une liste vide si personne ne
    correspond — ce n'est pas une erreur, juste un resultat vide."""
    # On lit toute la table puis on filtre en Python, parce que le LIKE de
    # SQLite ne sait pas ignorer les accents. L'annuaire d'une petite
    # entreprise tient en memoire sans probleme ; sur une vraie base on
    # ajouterait une colonne deja normalisee et on filtrerait en SQL.
    with _connexion() as db:
        db.row_factory = sqlite3.Row
        lignes = db.execute(
            "SELECT nom, role, departement, email FROM employes"
        ).fetchall()

    recherche = _sans_accents(departement)
    return [
        dict(ligne)
        for ligne in lignes
        if recherche in _sans_accents(ligne["departement"])
    ]


def chercher_personne(nom: str) -> list[dict]:
    """Cherche une personne par son NOM dans l'annuaire (recherche partielle,
    insensible a la casse).

    Pourquoi cet outil existe alors que lister_equipe fait deja une recherche :
    lister_equipe ne cherche que par departement. Pour retrouver quelqu'un dont
    on ne connait que le nom, le modele devait balayer les departements un par
    un — on a mesure quatre appels pour trouver une seule personne. Un outil
    qui repond en un appel coute moins cher, va plus vite, et laisse moins de
    place a l'erreur.

    On plafonne a 5 resultats : un outil bien fait renvoie peu et deja digere.
    Renvoyer tout l'annuaire remplirait le contexte du modele pour rien.
    """
    # Meme raison que dans lister_equipe : on filtre en Python pour ignorer
    # les accents et la casse.
    with _connexion() as db:
        db.row_factory = sqlite3.Row
        lignes = db.execute(
            "SELECT nom, role, departement, email FROM employes"
        ).fetchall()

    recherche = _sans_accents(nom)
    trouves = [
        dict(ligne) for ligne in lignes if recherche in _sans_accents(ligne["nom"])
    ]
    # On plafonne a 5 : un outil bien fait renvoie peu et deja digere.
    return trouves[:5]


def envoyer_message(destinataire: str, sujet: str, corps: str) -> dict:
    """Ecrit un message dans outbox/ : notre faux service de messagerie
    (voir SPEC.md — c'est un choix documente, pas un mock cache). Un vrai
    fichier est cree sur disque, avec un vrai risque d'erreur (droits,
    disque plein, etc.) que appeler_outil() saura rattraper."""
    horodatage = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    nom_fichier = f"{horodatage}_{destinataire.replace(' ', '_').replace('/', '_')}.txt"
    chemin = OUTBOX_DIR / nom_fichier
    chemin.write_text(f"A : {destinataire}\nSujet : {sujet}\n\n{corps}\n", encoding="utf-8")
    return {"fichier": str(chemin.relative_to(RACINE)), "destinataire": destinataire, "sujet": sujet}


def creer_fiche_employe(
    nom: str, role: str, departement: str, email: str, date_arrivee: str
) -> dict:
    """Cree la fiche d'un nouvel employe dans l'annuaire (table employes).

    EFFET DE BORD : ecrit une ligne en base. Une fois creee, la personne est
    immediatement trouvable par lister_equipe et chercher_personne — la boucle
    se referme sur elle-meme.

    On renvoie l'identifiant de la ligne creee : c'est ce qui permettra
    d'annuler l'action plus tard.
    """
    with _connexion() as db:
        curseur = db.execute(
            "INSERT INTO employes (nom, role, departement, email, date_arrivee)"
            " VALUES (?, ?, ?, ?, ?)",
            (nom, role, departement, email, date_arrivee),
        )
        identifiant = curseur.lastrowid
    return {"id": identifiant, "nom": nom, "email": email, "departement": departement}


def creer_ticket(titre: str, description: str, assigne_a: str) -> dict:
    """Cree un ticket dans le suivi des taches (table tickets).

    EFFET DE BORD : ecrit une ligne en base.

    On renvoie l'identifiant du ticket cree, pour pouvoir l'annuler.
    """
    with _connexion() as db:
        curseur = db.execute(
            "INSERT INTO tickets (titre, description, assigne_a, cree_le)"
            " VALUES (?, ?, ?, ?)",
            (titre, description, assigne_a, datetime.now(timezone.utc).isoformat()),
        )
        identifiant = curseur.lastrowid
    return {"id": identifiant, "titre": titre, "assigne_a": assigne_a}


def generer_document(nom_fichier: str, contenu: str) -> dict:
    """Ecrit un document texte dans documents/.

    EFFET DE BORD : cree un vrai fichier sur disque.

    SECURITE : on ne fait jamais confiance au nom de fichier propose par le
    modele. Path(...).name ne garde que le dernier element du chemin, ce qui
    neutralise une tentative comme "../../.env" — sans cette ligne, l'agent
    pourrait ecrire n'importe ou sur le disque.
    """
    nom_propre = Path(nom_fichier).name or "document.md"
    chemin = DOCS_DIR / nom_propre
    chemin.write_text(contenu, encoding="utf-8")
    return {"fichier": str(chemin.relative_to(RACINE)), "taille_octets": len(contenu)}


# =============================================================================
# LES SCHEMAS — ce que le modele lit pour CHOISIR un outil
# =============================================================================
# La description est la partie qui compte le plus : c'est elle qui determine
# si le modele choisit le bon outil sur une question qu'on n'a pas anticipee.

SCHEMA_LISTER_EQUIPE = {
    "type": "function",
    "function": {
        "name": "lister_equipe",
        "description": (
            "Liste les membres d'un departement de l'entreprise, avec leur nom, "
            "role et email. A utiliser pour toute question sur qui travaille ou, "
            "dans quel departement, ou pour trouver le contact de quelqu'un. "
            "N'invente jamais un nom d'employe : appelle cet outil."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "departement": {
                    "type": "string",
                    "description": "Nom du departement recherche, ex: 'Ingenierie', 'RH', 'Design', 'Marketing'.",
                }
            },
            "required": ["departement"],
        },
    },
}

SCHEMA_ENVOYER_MESSAGE = {
    "type": "function",
    "function": {
        "name": "envoyer_message",
        "description": (
            "Envoie un message a une personne (ex: message de bienvenue, "
            "notification). EFFET DE BORD REEL : ecrit un fichier dans outbox/. "
            "N'appelle cet outil que si l'utilisateur demande explicitement "
            "d'envoyer, notifier ou prevenir quelqu'un — jamais pour une simple "
            "question d'information."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "destinataire": {"type": "string", "description": "Nom ou email du destinataire."},
                "sujet": {"type": "string", "description": "Sujet court du message."},
                "corps": {"type": "string", "description": "Contenu du message."},
            },
            "required": ["destinataire", "sujet", "corps"],
        },
    },
}

SCHEMA_CHERCHER_PERSONNE = {
    "type": "function",
    "function": {
        "name": "chercher_personne",
        "description": (
            "Retrouve une personne a partir de son NOM ou d'une partie de son "
            "nom, et renvoie son role, son departement et son email. "
            "A utiliser des que tu connais le nom de quelqu'un et qu'il te "
            "manque une de ces informations. "
            "Ne confonds pas avec lister_equipe : ici tu pars d'un NOM, "
            "lister_equipe part d'un DEPARTEMENT. Si tu cherches une personne "
            "precise, utilise cet outil — n'essaie pas de deviner son "
            "departement pour la retrouver."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "nom": {
                    "type": "string",
                    "description": "Nom ou partie du nom recherche, ex: 'Alice', 'Dupont', 'Alice Dupont'.",
                }
            },
            "required": ["nom"],
        },
    },
}

SCHEMA_CREER_FICHE_EMPLOYE = {
    "type": "function",
    "function": {
        "name": "creer_fiche_employe",
        "description": (
            "Cree la fiche d'un NOUVEL employe dans l'annuaire de l'entreprise. "
            "A utiliser quand quelqu'un rejoint l'equipe et n'existe pas encore "
            "dans l'annuaire. Verifie d'abord avec chercher_personne qu'elle n'y "
            "est pas deja : ne cree jamais deux fiches pour la meme personne. "
            "N'invente aucune des valeurs — si le role, le departement, l'email "
            "ou la date d'arrivee ne sont pas fournis, demande-les."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "nom": {"type": "string", "description": "Nom complet, ex: 'Sarah Martin'."},
                "role": {"type": "string", "description": "Intitule du poste, ex: 'Developpeuse back-end'."},
                "departement": {
                    "type": "string",
                    "description": "Departement d'affectation, ex: 'Ingenierie', 'Design', 'RH', 'Marketing'.",
                },
                "email": {"type": "string", "description": "Adresse email professionnelle."},
                "date_arrivee": {
                    "type": "string",
                    "description": "Date d'arrivee au format AAAA-MM-JJ.",
                },
            },
            "required": ["nom", "role", "departement", "email", "date_arrivee"],
        },
    },
}

SCHEMA_CREER_TICKET = {
    "type": "function",
    "function": {
        "name": "creer_ticket",
        "description": (
            "Cree un ticket de suivi assigne a quelqu'un, pour une tache a faire "
            "(preparer un poste de travail, ouvrir des acces, commander du "
            "materiel...). A utiliser quand une tache doit etre prise en charge "
            "par une personne de l'equipe. "
            "Ne confonds pas avec envoyer_message : un ticket est une TACHE a "
            "realiser et qui reste ouverte, un message est une simple information "
            "transmise."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "titre": {"type": "string", "description": "Titre court de la tache."},
                "description": {"type": "string", "description": "Ce qu'il faut faire, en detail."},
                "assigne_a": {
                    "type": "string",
                    "description": "Nom ou email de la personne chargee de la tache.",
                },
            },
            "required": ["titre", "description", "assigne_a"],
        },
    },
}

SCHEMA_GENERER_DOCUMENT = {
    "type": "function",
    "function": {
        "name": "generer_document",
        "description": (
            "Ecrit un document texte sur disque : livret d'accueil, recapitulatif, "
            "note d'organisation. A utiliser quand l'utilisateur demande un "
            "document, un recapitulatif ou un guide a conserver. "
            "Ne confonds pas avec envoyer_message : un document est un fichier "
            "qu'on garde, un message est adresse a quelqu'un."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "nom_fichier": {
                    "type": "string",
                    "description": "Nom du fichier, sans chemin, ex: 'accueil-sarah-martin.md'.",
                },
                "contenu": {"type": "string", "description": "Le contenu complet du document."},
            },
            "required": ["nom_fichier", "contenu"],
        },
    },
}

SCHEMAS = [
    # Consultation — sans effet de bord
    SCHEMA_LISTER_EQUIPE,
    SCHEMA_CHERCHER_PERSONNE,
    # Action — avec effet de bord, donc jamais executes par la boucle
    SCHEMA_CREER_FICHE_EMPLOYE,
    SCHEMA_CREER_TICKET,
    SCHEMA_ENVOYER_MESSAGE,
    SCHEMA_GENERER_DOCUMENT,
]

OUTILS = {
    "lister_equipe": lister_equipe,
    "chercher_personne": chercher_personne,
    "creer_fiche_employe": creer_fiche_employe,
    "creer_ticket": creer_ticket,
    "envoyer_message": envoyer_message,
    "generer_document": generer_document,
}

# =============================================================================
# LE GARDE-FOU CENTRAL DU PROJET
# =============================================================================
# Un outil a un "effet de bord" quand il modifie quelque chose en dehors de
# notre programme : ecrire en base, creer un fichier, envoyer un message.
# Ces actions-la ne sont PAS reversibles d'un simple clic.
#
# LE BRAS repose entierement sur cette distinction :
#   - un outil SANS effet de bord (lecture) est execute librement par la
#     boucle : au pire on a lu une donnee pour rien ;
#   - un outil AVEC effet de bord n'est JAMAIS execute par la boucle. Il est
#     seulement enregistre comme une action PROPOSEE, que l'utilisateur devra
#     approuver.
#
# Ajouter un outil d'ecriture sans l'inscrire ici serait le seul moyen de
# casser cette garantie : c'est pour ca que la liste est courte, explicite,
# et placee juste sous la table des outils.
OUTILS_A_EFFET_DE_BORD = {
    "creer_fiche_employe",
    "creer_ticket",
    "envoyer_message",
    "generer_document",
}


def a_un_effet_de_bord(nom: str) -> bool:
    """Dit si un outil modifie quelque chose hors du programme."""
    return nom in OUTILS_A_EFFET_DE_BORD


# =============================================================================
# LES ANNULATIONS — defaire ce qu'un outil a fait
# =============================================================================
# Chaque outil a effet de bord doit avoir son inverse, sinon l'utilisateur ne
# peut pas revenir en arriere. Une annulation prend le RESULTAT de l'action
# d'origine (qui contient l'identifiant de la ligne creee ou le chemin du
# fichier ecrit) et defait l'effet.
#
# C'est pour ca que chaque outil d'action renvoie de quoi s'annuler : sans
# l'identifiant, on ne saurait pas quelle ligne supprimer.

def _annuler_creer_fiche_employe(resultat: dict) -> dict:
    with _connexion() as db:
        db.execute("DELETE FROM employes WHERE id = ?", (resultat["id"],))
    return {"annule": f"fiche employe #{resultat['id']} supprimee"}


def _annuler_creer_ticket(resultat: dict) -> dict:
    with _connexion() as db:
        db.execute("DELETE FROM tickets WHERE id = ?", (resultat["id"],))
    return {"annule": f"ticket #{resultat['id']} supprime"}


def _annuler_fichier(resultat: dict) -> dict:
    """Annulation commune a envoyer_message et generer_document : les deux
    ont ecrit un fichier, les deux s'annulent en le supprimant."""
    chemin = (RACINE / resultat["fichier"]).resolve()

    # SECURITE : on ne supprime que sous la racine du projet. Le chemin vient
    # de notre propre code, mais une verification coute une ligne et evite
    # qu'une donnee corrompue en base ne fasse supprimer un fichier ailleurs.
    if not chemin.is_relative_to(RACINE.resolve()):
        raise ValueError(f"Chemin hors du projet : {resultat['fichier']}")

    # missing_ok=True : si le fichier a deja disparu (supprime a la main),
    # l'annulation reussit quand meme. Le but est que le fichier n'existe
    # plus — il n'existe plus.
    chemin.unlink(missing_ok=True)
    return {"annule": f"fichier {resultat['fichier']} supprime"}


ANNULATIONS = {
    "creer_fiche_employe": _annuler_creer_fiche_employe,
    "creer_ticket": _annuler_creer_ticket,
    "envoyer_message": _annuler_fichier,
    "generer_document": _annuler_fichier,
}


def peut_etre_annule(nom: str) -> bool:
    """Dit si un outil sait defaire ce qu'il a fait."""
    return nom in ANNULATIONS


def annuler_outil(nom: str, resultat: dict) -> dict:
    """
    Defait une action executee. Meme contrat que appeler_outil : ne leve
    jamais d'exception, renvoie soit un resultat, soit {"erreur": ...}.
    """
    inverse = ANNULATIONS.get(nom)
    if inverse is None:
        return {"erreur": f"L'outil '{nom}' ne sait pas s'annuler."}

    try:
        resultat_annulation = inverse(resultat)
    except Exception as e:
        logger.warning("annulation de %s a echoue: %s", nom, e)
        return {"erreur": f"L'annulation de '{nom}' a echoue : {e}"}

    logger.info("annulation de %s -> %s", nom, resultat_annulation)
    return resultat_annulation


def appeler_outil(nom: str, arguments: dict) -> dict:
    """
    Execute un outil par son nom et rend un resultat toujours serialisable.

    Point d'entree UNIQUE de la boucle d'appel d'outils (llm.py ne connait
    pas OUTILS directement). Ne laisse JAMAIS une exception remonter : un
    outil qui plante, un outil debranche (nom absent de OUTILS, par exemple
    si on le retire pour tester la resilience), ou de mauvais arguments
    produisent tous un resultat {"erreur": "..."} que le modele peut lire et
    rapporter a l'utilisateur — plutot qu'un crash du serveur ou une reponse
    inventee.
    """
    fonction = OUTILS.get(nom)
    if fonction is None:
        logger.warning("outil demande introuvable ou debranche: %s", nom)
        return {"erreur": f"L'outil '{nom}' n'existe pas ou est desactive."}

    try:
        resultat = fonction(**arguments)
    except Exception as e:
        logger.warning("outil %s(%s) a echoue: %s", nom, arguments, e)
        return {"erreur": f"L'outil '{nom}' a echoue : {e}"}

    logger.info("outil %s(%s) -> %s", nom, arguments, resultat)
    return resultat
