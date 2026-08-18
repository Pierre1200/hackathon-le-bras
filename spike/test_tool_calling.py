"""
SPIKE — Test de fiabilite des appels d'outils.

=============================================================================
 CE FICHIER EST JETABLE. Ce n'est PAS le code du projet.
 Son seul but : mesurer, avant de coder LE BRAS, si le modele choisi renvoie
 des appels d'outils fiables et bien types. Le resultat va dans JOURNAL.md,
 puis on supprime (ou on garde en le declarant comme spike).
=============================================================================

Ce qu'on veut prouver en 3 points :
  1. Le modele renvoie des appels d'outils STRUCTURES (pas du texte).
  2. Les arguments respectent nos types (une date est bien une date).
  3. Sur une intention trop vague, il DEMANDE au lieu d'inventer.

Lancement :
    .venv/bin/python spike/test_tool_calling.py
"""

import os
import re
from pathlib import Path

import anthropic
from dotenv import load_dotenv

# On charge le fichier .env qui se trouve a la racine du depot.
# La cle d'API n'apparait JAMAIS dans le code : elle vit uniquement dans .env,
# et .env est ignore par git (c'est la regle qui vaut -10 points si on la rate).
load_dotenv(Path(__file__).parent.parent / ".env")


# =============================================================================
# 1. LES OUTILS
# =============================================================================
# Point cle a comprendre AVANT tout le reste :
# on n'envoie PAS de fonctions Python au modele. On lui envoie leur MODE D'EMPLOI :
# un nom, une description, et un schema JSON qui decrit les parametres attendus.
# Le modele lit ce mode d'emploi et repond "je voudrais appeler create_employee
# avec ces arguments". C'est NOTRE code qui decide ensuite quoi en faire.
#
# "strict": True garantit que les arguments renvoyes respecteront exactement
# le schema. Ca exige "additionalProperties": False et de lister tous les champs
# dans "required".

OUTILS = [
    {
        # --- OUTIL DE LECTURE : aucun effet de bord ---
        # Il est la pour une raison precise : sans outil de lecture, le modele
        # ne DECIDE rien, il deroule une recette. Avec, il doit d'abord aller
        # chercher de l'information. C'est ca, la "decision du modele" du bareme.
        "name": "list_team_members",
        "description": (
            "Liste les membres d'une equipe. A utiliser pour savoir qui travaille "
            "ou, avant de creer quoi que ce soit. Cet outil ne modifie rien."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "department": {
                    "type": "string",
                    "description": "Nom du departement, par exemple 'engineering'.",
                }
            },
            "required": ["department"],
            "additionalProperties": False,
        },
    },
    {
        # --- OUTIL D'ECRITURE : effet de bord ---
        # C'est ici qu'on teste le typage : start_date doit etre une vraie date
        # au format AAAA-MM-JJ, pas "lundi prochain".
        "name": "create_employee",
        "description": "Cree la fiche d'un nouvel employe en base.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nom complet."},
                "role": {"type": "string", "description": "Intitule du poste."},
                "start_date": {
                    "type": "string",
                    "format": "date",
                    "description": "Date d'arrivee au format AAAA-MM-JJ.",
                },
                "email": {"type": "string", "description": "Adresse email pro."},
            },
            "required": ["name", "role", "start_date", "email"],
            "additionalProperties": False,
        },
    },
    {
        # --- OUTIL D'ECRITURE : on teste ici une liste de chaines ---
        "name": "create_issue",
        "description": "Cree un ticket dans le suivi des taches.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Titre du ticket."},
                "assignee": {"type": "string", "description": "Personne assignee."},
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Etiquettes du ticket.",
                },
            },
            "required": ["title", "assignee", "labels"],
            "additionalProperties": False,
        },
    },
]

# On memorise quels outils ont un effet de bord : ca sert au test n.5.
OUTILS_ECRITURE = {"create_employee", "create_issue"}


# =============================================================================
# 2. LE PROMPT SYSTEME
# =============================================================================
# Volontairement court. On veut mesurer le modele, pas la qualite de notre prompt.
# Une seule consigne compte ici : ne pas inventer.

PROMPT_SYSTEME = """Tu es un assistant qui prepare des actions administratives.
Tu disposes d'outils. Renseigne-toi avec les outils de lecture avant de proposer
une ecriture. Si une information te manque (une date, un email, un nom),
demande-la a l'utilisateur : n'invente jamais une valeur.
Nous sommes le lundi 24 aout 2026."""


# =============================================================================
# 3. LES INTENTIONS DE TEST
# =============================================================================
# 5 cas, du plus simple au plus vicieux. Le n.5 est le plus important.

INTENTIONS = [
    (
        "1. Simple + date relative",
        "Prepare l'arrivee de Sarah Martin, developpeuse back-end. "
        "Elle commence lundi prochain. Son email est sarah.martin@exemple.fr",
    ),
    (
        "2. Liste de chaines",
        "Cree un ticket d'onboarding pour Sarah, assigne-le a pierre, "
        "avec les etiquettes onboarding et rh.",
    ),
    (
        "3. Lecture seule",
        "Qui travaille dans l'equipe engineering ?",
    ),
    (
        "4. Deux infos a extraire",
        "Ajoute Karim Benali comme designer, il arrive le 1er septembre, "
        "son email est karim.benali@exemple.fr",
    ),
    (
        # LE test decisif : l'intention ne contient AUCUNE donnee exploitable.
        # Un bon modele demande des precisions. Un mauvais invente un nom,
        # une date et un email -> et notre agent ecrirait des donnees fausses en base.
        "5. VOLONTAIREMENT AMBIGUE",
        "Occupe-toi du nouveau.",
    ),
]


# =============================================================================
# 4. LE SEUL ENDROIT DU PROJET QUI PARLE AU FOURNISSEUR
# =============================================================================
# C'est le principe qu'on veut valider : tout passe par cette fonction.
# Changer de modele = changer une chaine de caracteres. Changer de fournisseur =
# reecrire cette seule fonction, sans toucher au reste du projet.

client = anthropic.Anthropic()  # lit ANTHROPIC_API_KEY dans l'environnement


def appeler_le_modele(modele: str, intention: str):
    """Envoie une intention au modele avec la liste des outils, et rend sa reponse brute."""
    return client.messages.create(
        model=modele,
        # max_tokens est un PLAFOND, pas une facturation : on ne paie que ce qui
        # est reellement consomme. On le met large pour ne pas couper la reponse.
        max_tokens=16000,
        system=PROMPT_SYSTEME,
        tools=OUTILS,
        messages=[{"role": "user", "content": intention}],
    )


# =============================================================================
# 5. LA VERIFICATION
# =============================================================================

FORMAT_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def analyser(reponse):
    """Lit la reponse du modele et en extrait ce qu'on veut mesurer."""
    appels = []      # les appels d'outils demandes
    texte = []       # ce que le modele a dit en clair
    erreurs = []     # les problemes de typage qu'on detecte

    # Une reponse est une LISTE DE BLOCS. Chaque bloc a un type.
    # Un bloc "tool_use" = le modele demande un appel d'outil.
    # ATTENTION : on ne l'execute pas. On le lit. C'est tout le principe du BRAS.
    for bloc in reponse.content:
        if bloc.type == "text":
            texte.append(bloc.text.strip())
        elif bloc.type == "tool_use":
            appels.append((bloc.name, bloc.input))

            # Verification des types que le schema promet.
            if bloc.name == "create_employee":
                date = bloc.input.get("start_date", "")
                if not FORMAT_DATE.match(str(date)):
                    erreurs.append(f"start_date mal formatee : {date!r}")
            if bloc.name == "create_issue":
                labels = bloc.input.get("labels")
                if not isinstance(labels, list) or not all(
                    isinstance(x, str) for x in labels
                ):
                    erreurs.append(f"labels n'est pas une liste de chaines : {labels!r}")

    return appels, texte, erreurs


# Tarifs publics en dollars par MILLION de tokens (entree, sortie).
# Sert a afficher le cout reel : c'est la carte bonus "cout affiche" du bareme.
TARIFS = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),   # tarif de lancement jusqu'au 31/08/2026
    "claude-haiku-4-5": (1.00, 5.00),
}


def cout_en_dollars(modele: str, usage) -> float:
    """Convertit les tokens consommes en dollars."""
    prix_entree, prix_sortie = TARIFS.get(modele, (0.0, 0.0))
    return (
        usage.input_tokens * prix_entree / 1_000_000
        + usage.output_tokens * prix_sortie / 1_000_000
    )


# =============================================================================
# 6. LE PROGRAMME PRINCIPAL
# =============================================================================

MODELES = ["claude-opus-5", "claude-haiku-4-5"]


def main():
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERREUR : ANTHROPIC_API_KEY absente.")
        print("Cree un fichier .env a la racine avec :  ANTHROPIC_API_KEY=ta-cle")
        return

    recapitulatif = []

    for modele in MODELES:
        print("\n" + "=" * 72)
        print(f"  MODELE : {modele}")
        print("=" * 72)

        cout_total = 0.0
        appels_valides = 0
        appels_totaux = 0

        for titre, intention in INTENTIONS:
            print(f"\n--- {titre}")
            print(f'    Intention : "{intention}"')

            reponse = appeler_le_modele(modele, intention)

            # Le modele peut refuser une demande. Dans ce cas le contenu est vide :
            # on verifie TOUJOURS stop_reason avant de lire content.
            if reponse.stop_reason == "refusal":
                print("    -> Demande refusee par le modele.")
                continue

            appels, texte, erreurs = analyser(reponse)
            cout = cout_en_dollars(modele, reponse.usage)
            cout_total += cout

            if appels:
                for nom, arguments in appels:
                    appels_totaux += 1
                    print(f"    -> OUTIL  {nom}")
                    for cle, valeur in arguments.items():
                        print(f"         {cle} = {valeur!r}")
            else:
                appels_totaux += 0

            if texte:
                extrait = " ".join(texte)[:160]
                print(f'    -> TEXTE  "{extrait}..."')

            if erreurs:
                for e in erreurs:
                    print(f"    -> !! TYPE INVALIDE : {e}")
            else:
                appels_valides += len(appels)

            # Cas n.5 : le seul comportement acceptable est de NE PAS ecrire.
            if titre.startswith("5."):
                a_ecrit = any(nom in OUTILS_ECRITURE for nom, _ in appels)
                if a_ecrit:
                    print("    -> !! ECHEC : il a invente des donnees sur une demande vague.")
                else:
                    print("    -> OK : il n'a rien invente (il demande ou il se renseigne).")

            print(
                f"    [{reponse.usage.input_tokens} tokens entree / "
                f"{reponse.usage.output_tokens} sortie = {cout*100:.2f} centimes]"
            )

        recapitulatif.append((modele, appels_valides, appels_totaux, cout_total))

    # ---- Tableau final : c'est ca qu'on colle dans JOURNAL.md ----
    print("\n" + "=" * 72)
    print("  RECAPITULATIF")
    print("=" * 72)
    print(f"{'modele':<22} {'appels bien types':<20} {'cout des 5 tests'}")
    for modele, valides, totaux, cout in recapitulatif:
        score = f"{valides}/{totaux}" if totaux else "0/0"
        print(f"{modele:<22} {score:<20} {cout*100:.1f} centimes")
    print()


if __name__ == "__main__":
    main()
