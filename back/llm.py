"""
llm.py — LE SEUL FICHIER DU PROJET QUI PARLE AU FOURNISSEUR DE MODELE.

Pourquoi ce fichier existe
--------------------------
C'est notre "adaptateur". Tout le reste du projet (les routes, le planificateur,
l'executeur) appelle la fonction `demander_au_modele()` sans jamais savoir a qui
elle parle. Consequence concrete : si on change de fournisseur, on reecrit CE
fichier et rien d'autre.

C'est aussi la reponse a la question du checkpoint "ou sont vos cles d'API ?" :
la cle est lue ici, cote serveur, depuis un fichier .env qui n'est jamais commite.
Elle ne sort jamais du back. Le navigateur ne la voit jamais.

Regle a retenir : AUCUN autre fichier du projet n'a le droit d'ecrire
`import anthropic`. Si ca arrive, l'abstraction est cassee.
"""

import os
from dataclasses import dataclass
from pathlib import Path

import anthropic
from dotenv import load_dotenv

# On charge le fichier .env situe a la racine du depot.
# Path(__file__) = le chemin de CE fichier (back/llm.py)
#   .parent        -> le dossier back/
#   .parent.parent -> la racine du depot
# On construit le chemin comme ca plutot qu'en dur ("../.env") pour que le
# programme marche quel que soit le dossier depuis lequel on le lance.
load_dotenv(Path(__file__).parent.parent / ".env")


# =============================================================================
# CONFIGURATION
# =============================================================================

# Le modele est lu dans le .env. C'est LA "ligne a changer" pour changer de
# modele : aucune modification de code n'est necessaire.
# Valeur par defaut si la variable est absente : claude-opus-5.
MODELE = os.getenv("LLM_MODEL", "claude-opus-5")

# Tarifs publics en dollars par MILLION de tokens, sous la forme (entree, sortie).
# Ils servent uniquement a afficher le cout : c'est la carte bonus "cout affiche"
# du bareme. A mettre a jour si les tarifs changent.
TARIFS = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

# Reglages supplementaires propres a chaque modele.
#
# POURQUOI CETTE TABLE EXISTE : tous les modeles n'acceptent pas les memes
# parametres. Le parametre "effort", qui regle la profondeur de reflexion,
# n'existe que sur les modeles recents ; l'envoyer a Haiku 4.5 fait echouer
# la requete entiere avec une erreur 400.
#
# C'est exactement le role de cet adaptateur : absorber ces differences ici,
# pour que le reste du projet puisse changer de modele sans rien savoir de
# leurs particularites.
#
# Un modele absent de cette table recoit un dictionnaire vide, donc aucun
# reglage supplementaire : c'est le comportement le plus sur par defaut.
OPTIONS_PAR_MODELE = {
    # "low" parce que le palier 2 ne demande qu'un aller-retour : on privilegie
    # la rapidite. On remontera l'effort au palier 3, quand le planificateur
    # devra vraiment raisonner pour construire un plan.
    "claude-opus-5": {"output_config": {"effort": "low"}},
    "claude-sonnet-5": {"output_config": {"effort": "low"}},
    # Haiku 4.5 n'accepte pas le parametre "effort" : on ne lui envoie rien.
    "claude-haiku-4-5": {},
}


# =============================================================================
# LES TYPES QU'ON EXPOSE AU RESTE DU PROJET
# =============================================================================

class ErreurLLM(Exception):
    """
    Notre erreur maison.

    Pourquoi on ne laisse pas passer les erreurs du SDK Anthropic telles quelles :
    parce que le reste du projet ne doit rien connaitre du fournisseur. Si demain
    on change de fournisseur, ses erreurs auront d'autres noms — mais le reste du
    code continuera d'attraper `ErreurLLM` sans etre modifie.
    """
    pass


@dataclass
class ReponseLLM:
    """
    Ce que notre fonction rend au reste du projet.

    `@dataclass` est un raccourci Python : il ecrit tout seul le constructeur
    a partir des champs declares ci-dessous. On s'en sert ici pour avoir un
    objet clair et type, plutot qu'un dictionnaire ou on ne sait jamais quelles
    cles existent.

    On expose volontairement les tokens et le cout : ils alimentent l'affichage
    du cout a l'ecran et, plus tard, le journal d'audit.
    """
    texte: str            # la reponse du modele, en clair
    modele: str           # quel modele a repondu (utile quand on en compare deux)
    tokens_entree: int    # ce qu'on a envoye
    tokens_sortie: int    # ce qu'il a produit
    cout_dollars: float   # le cout reel de CET appel


# =============================================================================
# LE CLIENT
# =============================================================================

# On cree le client UNE SEULE FOIS, au chargement du module, et pas a chaque
# appel : il garde une connexion ouverte vers l'API, ce qui evite de refaire
# une poignee de main reseau a chaque question.
#
# La cle n'est pas passee en argument : le SDK lit tout seul la variable
# d'environnement ANTHROPIC_API_KEY, que load_dotenv() vient de charger.
# On ne l'ecrit donc JAMAIS dans le code.
#
# timeout=60.0 : au bout de 60 secondes sans reponse, on abandonne avec une
# erreur propre. Sans ca, une requete qui traine bloque le serveur
# indefiniment et l'utilisateur voit une page qui tourne dans le vide.
_client = anthropic.Anthropic(timeout=60.0)


def _cout(modele: str, tokens_entree: int, tokens_sortie: int) -> float:
    """
    Convertit un nombre de tokens en dollars.

    Le prefixe `_` est une convention Python : elle signale que cette fonction
    est un detail interne du fichier et n'est pas destinee a etre appelee
    depuis l'exterieur.
    """
    # ATTENTION, piege rencontre en vrai :
    # le nom qu'on ENVOIE et le nom que l'API RENVOIE ne sont pas toujours
    # identiques. On demande "claude-haiku-4-5" et l'API repond
    # "claude-haiku-4-5-20251001", son identifiant date complet.
    # Une simple recherche par egalite ne trouvait donc rien, et le cout
    # s'affichait a 0.
    #
    # On cherche donc en deux temps : d'abord le nom exact, puis une cle de
    # notre table dont le nom renvoye est une extension.
    prix_entree, prix_sortie = 0.0, 0.0
    if modele in TARIFS:
        prix_entree, prix_sortie = TARIFS[modele]
    else:
        for cle, tarif in TARIFS.items():
            if modele.startswith(cle):
                prix_entree, prix_sortie = tarif
                break
    # Si aucun tarif n'est trouve, on renvoie 0 plutot que de faire planter le
    # programme : un cout faux est genant, planter pour un affichage le serait plus.
    return (
        tokens_entree * prix_entree / 1_000_000
        + tokens_sortie * prix_sortie / 1_000_000
    )


# =============================================================================
# LA FONCTION PUBLIQUE — c'est la seule chose que le reste du projet utilise
# =============================================================================

def demander_au_modele(message: str, prompt_systeme: str = "") -> ReponseLLM:
    """
    Envoie un message au modele et rend sa reponse.

    Parametres
    ----------
    message : le texte de l'utilisateur.
    prompt_systeme : les consignes permanentes donnees au modele. Optionnel
        pour l'instant (palier 2, on ne fait que verifier que le tuyau passe).
        A partir du palier 3, c'est ici qu'on posera les regles du planificateur.

    Renvoie
    -------
    Un objet ReponseLLM.

    Leve
    ----
    ErreurLLM si l'appel echoue, quelle qu'en soit la raison.
    """
    try:
        reponse = _client.messages.create(
            model=MODELE,

            # max_tokens est un PLAFOND de securite, pas une facturation :
            # on ne paie que les tokens reellement produits. On le met large
            # pour ne jamais couper une reponse au milieu d'une phrase.
            max_tokens=16000,

            # Les reglages propres au modele choisi (voir OPTIONS_PAR_MODELE).
            # La syntaxe `**dictionnaire` deplie le dictionnaire en arguments
            # nommes : si le dictionnaire est vide, aucun argument n'est ajoute.
            # C'est ce qui nous permet d'envoyer "effort" a certains modeles
            # et rien du tout aux autres, sans ecrire de `if`.
            **OPTIONS_PAR_MODELE.get(MODELE, {}),

            # Les consignes permanentes. On ne passe le parametre que s'il est
            # rempli : envoyer un system vide n'a pas de sens.
            **({"system": prompt_systeme} if prompt_systeme else {}),

            # L'historique de la conversation. Ici un seul message : l'API est
            # SANS MEMOIRE, c'est a nous de lui renvoyer tout le contexte a
            # chaque appel. Au palier 2 on n'a rien a renvoyer.
            messages=[{"role": "user", "content": message}],
        )

    # ---- On traduit les erreurs du fournisseur en NOTRE erreur ----
    # On les prend de la plus precise a la plus generale : Python s'arrete au
    # premier `except` qui correspond, donc l'ordre compte.
    except anthropic.AuthenticationError:
        raise ErreurLLM(
            "Cle d'API invalide ou absente. Verifie ANTHROPIC_API_KEY dans le .env."
        )
    except anthropic.RateLimitError:
        raise ErreurLLM(
            "Trop de requetes envoyees au fournisseur. Reessaie dans quelques secondes."
        )
    except anthropic.APIConnectionError:
        # Erreur reseau : pas de reponse du tout (coupure, timeout, DNS...).
        raise ErreurLLM(
            "Impossible de joindre le fournisseur. Verifie ta connexion internet."
        )
    except anthropic.APIStatusError as e:
        # Filet de securite : toute autre reponse HTTP en erreur.
        #
        # Cas particulier du 400 : il signifie "ta requete est malformee",
        # donc c'est NOTRE bug, pas celui de l'utilisateur. On remonte le
        # message du fournisseur, qui dit precisement quel parametre pose
        # probleme — sans lui, on cherche a l'aveugle.
        # Ce message decrit un parametre d'API, il ne contient aucune donnee
        # sensible ni aucune trace interne de notre code.
        if e.status_code == 400:
            raise ErreurLLM(
                f"Requete refusee par le fournisseur (400) : {e.message} "
                f"— verifie les reglages envoyes pour le modele {MODELE}."
            )
        raise ErreurLLM(f"Le fournisseur a renvoye une erreur {e.status_code}.")

    # ---- Le modele peut refuser de repondre ----
    # Dans ce cas la requete REUSSIT (pas d'exception), mais le contenu est vide.
    # Il faut donc verifier stop_reason AVANT de lire reponse.content, sinon on
    # planterait en essayant de lire une liste vide.
    if reponse.stop_reason == "refusal":
        raise ErreurLLM("Le modele a refuse de repondre a cette demande.")

    # ---- On extrait le texte ----
    # Une reponse est une LISTE DE BLOCS, chacun avec un type. Un bloc "text"
    # contient de la prose ; a partir du palier 3, on verra aussi des blocs
    # "tool_use" quand le modele demandera un appel d'outil.
    # On assemble ici tous les blocs de texte en une seule chaine.
    morceaux = [bloc.text for bloc in reponse.content if bloc.type == "text"]
    texte = "\n".join(morceaux).strip()

    return ReponseLLM(
        texte=texte,
        modele=reponse.model,  # le modele reellement utilise, tel que l'API le nomme
        tokens_entree=reponse.usage.input_tokens,
        tokens_sortie=reponse.usage.output_tokens,
        cout_dollars=_cout(
            reponse.model, reponse.usage.input_tokens, reponse.usage.output_tokens
        ),
    )
