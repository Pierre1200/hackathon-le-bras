"""
llm.py — LE SEUL FICHIER DU PROJET QUI PARLE A UN FOURNISSEUR D'IA.

Pourquoi ce fichier existe
--------------------------
C'est notre "adaptateur". Tout le reste du projet appelle la fonction
`demander_au_modele()` sans jamais savoir a qui elle parle ni comment.

Consequence concrete : n'importe qui peut cloner ce depot et brancher SON
fournisseur en modifiant uniquement le fichier .env. Aucune ligne de code a
toucher.

Comment c'est possible
----------------------
La grande majorite des fournisseurs (OpenAI, Mistral, Groq, MiniMax, Together,
Ollama en local, et Anthropic via son point d'entree compatible) exposent la
MEME forme d'API, appelee "compatible OpenAI". On utilise donc un seul client,
et on lui indique par une variable d'environnement a quelle adresse taper.

Changer de fournisseur = changer trois lignes du .env :
    LLM_BASE_URL   ou taper
    LLM_API_KEY    avec quelle cle
    LLM_MODEL      quel modele

La cle est lue ici, cote serveur, depuis un .env jamais commite. Elle ne sort
jamais du back : le navigateur ne la voit jamais.

Regle a retenir : AUCUN autre fichier du projet n'a le droit d'ecrire
`import openai`. Si ca arrive, l'abstraction est cassee.
"""

import os
from dataclasses import dataclass
from pathlib import Path

import openai
from dotenv import load_dotenv

# On charge le .env situe a la racine du depot.
# Path(__file__) = le chemin de CE fichier (back/llm.py)
#   .parent        -> le dossier back/
#   .parent.parent -> la racine du depot
# On construit le chemin ainsi, et pas en dur ("../.env"), pour que le
# programme marche quel que soit le dossier depuis lequel on le lance.
load_dotenv(Path(__file__).parent.parent / ".env")


# =============================================================================
# CONFIGURATION — les trois seules lignes a changer pour changer de fournisseur
# =============================================================================

# L'adresse du fournisseur. Par defaut Anthropic, mais n'importe quelle API
# compatible OpenAI fonctionne (voir les exemples dans .env.example).
BASE_URL = os.getenv("LLM_BASE_URL", "https://api.anthropic.com/v1/")

# La cle d'API. Si elle est absente, on met une valeur bidon plutot que de
# planter au demarrage : le serveur doit pouvoir demarrer sans cle, pour que
# celui qui clone voie un message d'erreur clair a l'ecran plutot qu'un
# serveur qui refuse de se lancer.
CLE_API = os.getenv("LLM_API_KEY") or "cle-non-configuree"

# Le nom du modele, tel que le fournisseur l'appelle.
MODELE = os.getenv("LLM_MODEL", "claude-haiku-4-5")

# Plafond de tokens produits par reponse. C'est un garde-fou, pas une
# facturation : on ne paie que ce qui est reellement produit. Il protege
# surtout contre une reponse a rallonge si l'app est exposee publiquement.
MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1000"))

# Tarifs publics en dollars par MILLION de tokens : (entree, sortie).
# Sert uniquement a AFFICHER le cout (carte bonus "cout affiche" du bareme).
# Un modele absent de cette table affiche un cout de 0 : c'est une estimation
# d'affichage, pas une facturation, donc on prefere zero a un plantage.
TARIFS = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


# =============================================================================
# LES TYPES QU'ON EXPOSE AU RESTE DU PROJET
# =============================================================================

class ErreurLLM(Exception):
    """
    Notre erreur maison.

    Pourquoi on ne laisse pas passer les erreurs du SDK telles quelles :
    parce que le reste du projet ne doit rien connaitre du fournisseur.
    Si on en change, ses erreurs auront d'autres noms — mais le reste du code
    continuera d'attraper `ErreurLLM` sans etre modifie.
    """
    pass


@dataclass
class ReponseLLM:
    """
    Ce que notre fonction rend au reste du projet.

    `@dataclass` est un raccourci Python : il ecrit tout seul le constructeur
    a partir des champs declares ci-dessous. On s'en sert pour avoir un objet
    clair et type, plutot qu'un dictionnaire dont on ne sait jamais quelles
    cles existent.

    On expose les tokens et le cout : ils alimentent l'affichage a l'ecran et,
    plus tard, le journal d'audit.
    """
    texte: str            # la reponse du modele, en clair
    modele: str           # quel modele a repondu
    tokens_entree: int    # ce qu'on a envoye
    tokens_sortie: int    # ce qu'il a produit
    cout_dollars: float   # le cout estime de CET appel


# Le client est cree une seule fois, au chargement du fichier : il maintient
# une connexion ouverte, la recreer a chaque question referait une poignee de
# main reseau inutile.
_client = openai.OpenAI(base_url=BASE_URL, api_key=CLE_API, timeout=60.0)


def _cout(modele: str, tokens_entree: int, tokens_sortie: int) -> float:
    """
    Convertit un nombre de tokens en dollars.

    Le prefixe `_` est une convention Python : elle signale que la fonction est
    un detail interne du fichier, pas destinee a etre appelee de l'exterieur.
    """
    # ATTENTION, piege rencontre en vrai : le nom qu'on ENVOIE et le nom que
    # l'API RENVOIE ne sont pas toujours identiques. On demande
    # "claude-haiku-4-5" et l'API repond "claude-haiku-4-5-20251001".
    # Une recherche par simple egalite ne trouvait rien et le cout s'affichait
    # a 0. On cherche donc le nom exact, puis une cle dont le nom renvoye est
    # une extension.
    prix_entree, prix_sortie = 0.0, 0.0
    if modele in TARIFS:
        prix_entree, prix_sortie = TARIFS[modele]
    else:
        for cle, tarif in TARIFS.items():
            if modele.startswith(cle):
                prix_entree, prix_sortie = tarif
                break

    return (
        tokens_entree * prix_entree / 1_000_000
        + tokens_sortie * prix_sortie / 1_000_000
    )


# =============================================================================
# LA FONCTION PUBLIQUE — la seule chose que le reste du projet utilise
# =============================================================================

def demander_au_modele(message: str, prompt_systeme: str = "") -> ReponseLLM:
    """
    Envoie un message au modele et rend sa reponse.

    Parametres
    ----------
    message : le texte de l'utilisateur.
    prompt_systeme : les consignes permanentes donnees au modele. Optionnel au
        palier 2, ou l'on verifie seulement que le tuyau passe. A partir du
        palier 3, c'est ici qu'on posera les regles du planificateur.

    Renvoie
    -------
    Un objet ReponseLLM.

    Leve
    ----
    ErreurLLM si l'appel echoue, quelle qu'en soit la raison.
    """
    # On construit la conversation. Un message "system" porte les consignes
    # permanentes, un message "user" porte la demande. On n'ajoute le system
    # que s'il est rempli : en envoyer un vide n'a pas de sens.
    #
    # A retenir : l'API est SANS MEMOIRE. Elle ne se souvient d'aucun echange
    # precedent — c'est a nous de lui renvoyer tout le contexte a chaque appel.
    conversation = []
    if prompt_systeme:
        conversation.append({"role": "system", "content": prompt_systeme})
    conversation.append({"role": "user", "content": message})

    try:
        reponse = _client.chat.completions.create(
            model=MODELE,
            messages=conversation,
            max_tokens=MAX_TOKENS,
        )

    # ---- On traduit les erreurs du fournisseur en NOTRE erreur ----
    # De la plus precise a la plus generale : Python s'arrete au premier
    # `except` qui correspond, donc l'ordre compte.
    except openai.AuthenticationError:
        raise ErreurLLM(
            "Cle d'API refusee. Verifie LLM_API_KEY dans le .env, et qu'elle "
            f"correspond bien au fournisseur configure ({BASE_URL})."
        )
    except openai.NotFoundError:
        # Tres frequent quand on change de fournisseur : soit l'adresse est
        # fausse, soit ce fournisseur ne connait pas ce nom de modele.
        raise ErreurLLM(
            f"Modele '{MODELE}' introuvable chez {BASE_URL}. Verifie "
            "LLM_MODEL et LLM_BASE_URL dans le .env."
        )
    except openai.RateLimitError:
        raise ErreurLLM(
            "Trop de requetes envoyees au fournisseur. Reessaie dans quelques secondes."
        )
    except openai.APIConnectionError:
        # Erreur reseau : aucune reponse (coupure, DNS, adresse invalide...).
        raise ErreurLLM(
            f"Impossible de joindre {BASE_URL}. Verifie ta connexion et LLM_BASE_URL."
        )
    except openai.APIStatusError as e:
        # Filet de securite pour toute autre reponse HTTP en erreur.
        # On remonte le message du fournisseur : sans lui on cherche a
        # l'aveugle. Il decrit un probleme de requete, pas une donnee sensible.
        raise ErreurLLM(f"Erreur {e.status_code} du fournisseur : {e.message}")

    # ---- On extrait le texte ----
    # `choices` est une liste : l'API peut renvoyer plusieurs propositions.
    # On n'en demande qu'une, donc on prend la premiere.
    # `content` peut valoir None si le modele n'a rien produit : `or ""` evite
    # de planter en appelant .strip() sur None.
    texte = (reponse.choices[0].message.content or "").strip()

    # ---- On compte les tokens ----
    # Tous les fournisseurs compatibles ne renvoient pas le bloc `usage`.
    # On verifie donc son existence plutot que de supposer qu'il est la : sinon
    # l'app planterait chez celui qui branche un fournisseur plus minimaliste.
    usage = reponse.usage
    tokens_entree = usage.prompt_tokens if usage else 0
    tokens_sortie = usage.completion_tokens if usage else 0

    # `reponse.model` est le nom du modele tel que le fournisseur le nomme
    # reellement ; il peut differer de ce qu'on a demande. On garde le notre
    # en secours si le champ est absent.
    modele_reel = reponse.model or MODELE

    return ReponseLLM(
        texte=texte,
        modele=modele_reel,
        tokens_entree=tokens_entree,
        tokens_sortie=tokens_sortie,
        cout_dollars=_cout(modele_reel, tokens_entree, tokens_sortie),
    )
