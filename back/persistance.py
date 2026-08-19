"""
persistance.py — tout ce qui survit au rechargement de la page.

Pourquoi ce fichier existe
--------------------------
Jusqu'ici, un plan vivait le temps d'une requete HTTP puis disparaissait.
Le palier 4 demande qu'on puisse recharger la page en plein milieu sans rien
perdre : le plan et ses actions doivent donc vivre en base, pas dans le
navigateur ni dans la memoire du serveur.

Deux tables :

  plans    une intention de l'utilisateur, la reponse de l'agent, ce que
           l'appel a coute, et la trace des outils appeles.

  actions  les actions a effet de bord proposees pour un plan, avec leur
           statut, leur cle d'idempotence, et le resultat de leur execution.

`actions` sert DEUX besoins a la fois : c'est la liste des cartes a approuver,
ET le journal d'audit. Une action executee y garde son horodatage, ses
arguments et son resultat. On evite ainsi une deuxieme table qui dirait la
meme chose et pourrait diverger.

Ce module ne connait ni le modele ni les outils : il ne fait que ranger et
relire. C'est ce qui permet de le tester sans depenser un centime d'API.
"""

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Meme fichier de base que tools.py. On relit la variable d'environnement
# plutot que d'importer tools.py, pour que ce module reste independant :
# on peut le tester seul, sans charger les outils.
RACINE = Path(__file__).parent.parent
load_dotenv(RACINE / ".env")
DB_PATH = RACINE / os.getenv("DATABASE_URL", "sqlite:///./lebras.db").removeprefix("sqlite:///")


# =============================================================================
# LES STATUTS D'UNE ACTION
# =============================================================================
# Le cycle de vie complet :
#
#   proposee ──approuvee par l'utilisateur──> approuvee ──executee──> executee
#      │                                                                  │
#      └──refusee par l'utilisateur──> refusee                            │
#                                                                         │
#                                          echouee <──l'outil a plante────┤
#                                                                         │
#                                          annulee <──annulation demandee─┘
#
# On garde les actions refusees : le journal doit dire ce qui N'A PAS ete fait
# autant que ce qui a ete fait.
PROPOSEE = "proposee"
APPROUVEE = "approuvee"
REFUSEE = "refusee"
EXECUTEE = "executee"
ECHOUEE = "echouee"
ANNULEE = "annulee"


def _maintenant() -> str:
    """Horodatage ISO en UTC. En UTC pour que deux machines soient comparables."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connexion() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    # row_factory permet de lire les colonnes par leur nom (ligne["statut"])
    # au lieu de leur position (ligne[3]) : plus lisible, et ca ne casse pas
    # si on ajoute une colonne au milieu.
    db.row_factory = sqlite3.Row
    return db


def initialiser() -> None:
    """Cree les tables si elles n'existent pas. Rejouable sans risque."""
    with _connexion() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY,
                intention TEXT NOT NULL,
                reponse TEXT NOT NULL,
                modele TEXT NOT NULL,
                tokens_entree INTEGER NOT NULL,
                tokens_sortie INTEGER NOT NULL,
                cout_dollars REAL NOT NULL,
                trace_json TEXT NOT NULL,
                cree_le TEXT NOT NULL
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS actions (
                id INTEGER PRIMARY KEY,
                plan_id INTEGER NOT NULL,
                outil TEXT NOT NULL,
                arguments_json TEXT NOT NULL,
                cle_idempotence TEXT NOT NULL,
                statut TEXT NOT NULL,
                resultat_json TEXT,
                cree_le TEXT NOT NULL,
                execute_le TEXT,
                FOREIGN KEY (plan_id) REFERENCES plans (id)
            )
            """
        )
        # MIGRATION : duree_ms est arrivee apres la creation de la table.
        # CREATE TABLE IF NOT EXISTS ne l'ajoute pas sur une base existante,
        # il faut donc la rajouter a la main si elle manque.
        colonnes = {ligne[1] for ligne in db.execute("PRAGMA table_info(actions)")}
        if "duree_ms" not in colonnes:
            db.execute("ALTER TABLE actions ADD COLUMN duree_ms REAL")

        # Un index sur la cle d'idempotence : on interroge cette colonne avant
        # CHAQUE execution pour savoir si l'action a deja ete faite. Sans
        # index, SQLite parcourrait toute la table a chaque fois.
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_actions_cle ON actions (cle_idempotence)"
        )


initialiser()


# =============================================================================
# L'IDEMPOTENCE
# =============================================================================

def calculer_cle_idempotence(outil: str, arguments: dict) -> str:
    """
    Fabrique l'empreinte d'une action.

    A quoi ca sert : rejouer un plan, cliquer deux fois sur "Executer", ou
    perdre le reseau au mauvais moment ne doit pas creer deux fois le meme
    employe ni envoyer deux fois le meme message. Avant d'executer, on
    regarde si cette empreinte existe deja en succes ; si oui, on ne rejoue
    pas et on renvoie le resultat precedent.

    Pourquoi `sort_keys=True` : deux dictionnaires identiques peuvent
    s'ecrire dans un ordre different ({"a":1,"b":2} et {"b":2,"a":1}). Sans
    tri, ils donneraient deux empreintes differentes pour la MEME action, et
    l'idempotence ne servirait plus a rien.

    Pourquoi sha256 et pas hash() : hash() de Python change a chaque
    demarrage du programme, donc l'empreinte ne survivrait pas a un
    redemarrage du serveur — alors qu'elle est stockee en base.
    """
    empreinte = json.dumps(
        {"outil": outil, "arguments": arguments},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(empreinte.encode("utf-8")).hexdigest()


def chercher_execution_reussie(cle: str) -> dict | None:
    """Renvoie l'action deja executee avec succes pour cette cle, s'il y en a une."""
    with _connexion() as db:
        ligne = db.execute(
            "SELECT * FROM actions WHERE cle_idempotence = ? AND statut = ?"
            " ORDER BY id LIMIT 1",
            (cle, EXECUTEE),
        ).fetchone()
    return _action_en_dict(ligne) if ligne else None


# =============================================================================
# LECTURE / ECRITURE
# =============================================================================

def _action_en_dict(ligne: sqlite3.Row) -> dict:
    """Transforme une ligne SQL en dictionnaire pret a partir en JSON."""
    return {
        "id": ligne["id"],
        "plan_id": ligne["plan_id"],
        "outil": ligne["outil"],
        # Les arguments sont stockes en texte JSON (SQLite n'a pas de type
        # dictionnaire) : on les redeserialise a la lecture.
        "arguments": json.loads(ligne["arguments_json"]),
        "cle_idempotence": ligne["cle_idempotence"],
        "statut": ligne["statut"],
        "resultat": json.loads(ligne["resultat_json"]) if ligne["resultat_json"] else None,
        "cree_le": ligne["cree_le"],
        "execute_le": ligne["execute_le"],
        # Combien de temps l'execution a pris. None tant que l'action n'a pas
        # ete executee.
        "duree_ms": ligne["duree_ms"],
    }


def enregistrer_plan(
    intention: str,
    reponse: str,
    modele: str,
    tokens_entree: int,
    tokens_sortie: int,
    cout_dollars: float,
    trace: list[dict],
    actions_proposees: list[dict],
) -> int:
    """Range un plan et ses actions proposees. Renvoie l'identifiant du plan."""
    maintenant = _maintenant()
    with _connexion() as db:
        curseur = db.execute(
            "INSERT INTO plans (intention, reponse, modele, tokens_entree,"
            " tokens_sortie, cout_dollars, trace_json, cree_le)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                intention, reponse, modele, tokens_entree, tokens_sortie,
                cout_dollars, json.dumps(trace, ensure_ascii=False), maintenant,
            ),
        )
        plan_id = curseur.lastrowid

        for action in actions_proposees:
            db.execute(
                "INSERT INTO actions (plan_id, outil, arguments_json,"
                " cle_idempotence, statut, cree_le)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    plan_id,
                    action["outil"],
                    json.dumps(action["arguments"], ensure_ascii=False),
                    calculer_cle_idempotence(action["outil"], action["arguments"]),
                    PROPOSEE,
                    maintenant,
                ),
            )
    return plan_id


def lire_plan(plan_id: int) -> dict | None:
    """Relit un plan complet avec ses actions. C'est ce qui permet de
    recharger la page sans rien perdre."""
    with _connexion() as db:
        plan = db.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
        if plan is None:
            return None
        actions = db.execute(
            "SELECT * FROM actions WHERE plan_id = ? ORDER BY id", (plan_id,)
        ).fetchall()

    return {
        "id": plan["id"],
        "intention": plan["intention"],
        "reponse": plan["reponse"],
        "modele": plan["modele"],
        "tokens_entree": plan["tokens_entree"],
        "tokens_sortie": plan["tokens_sortie"],
        "cout_dollars": plan["cout_dollars"],
        "outils_appeles": json.loads(plan["trace_json"]),
        "cree_le": plan["cree_le"],
        "actions": [_action_en_dict(a) for a in actions],
    }


def dernier_plan() -> dict | None:
    """Le plan le plus recent. Sert au rechargement de la page : le front
    demande simplement "ou en etais-je ?"."""
    with _connexion() as db:
        ligne = db.execute("SELECT id FROM plans ORDER BY id DESC LIMIT 1").fetchone()
    return lire_plan(ligne["id"]) if ligne else None


def lire_action(action_id: int) -> dict | None:
    with _connexion() as db:
        ligne = db.execute("SELECT * FROM actions WHERE id = ?", (action_id,)).fetchone()
    return _action_en_dict(ligne) if ligne else None


def changer_statut(action_id: int, statut: str) -> None:
    """Passe une action d'un statut a un autre (approuvee, refusee, annulee...)."""
    with _connexion() as db:
        db.execute("UPDATE actions SET statut = ? WHERE id = ?", (statut, action_id))


def enregistrer_resultat(
    action_id: int, statut: str, resultat: dict, duree_ms: float | None = None
) -> None:
    """Note ce qu'a donne l'execution d'une action, quand, et en combien de temps."""
    with _connexion() as db:
        db.execute(
            "UPDATE actions SET statut = ?, resultat_json = ?, execute_le = ?,"
            " duree_ms = ? WHERE id = ?",
            (
                statut,
                json.dumps(resultat, ensure_ascii=False),
                _maintenant(),
                duree_ms,
                action_id,
            ),
        )


def lire_journal(limite: int = 50) -> list[dict]:
    """
    Le journal d'audit : tout ce qui a ete decide et fait, du plus recent au
    plus ancien.

    On y garde AUSSI les actions refusees et annulees. Un journal qui ne
    montrerait que les succes ne serait pas un journal d'audit : savoir ce
    qui n'a pas ete fait compte autant que le reste.
    """
    with _connexion() as db:
        lignes = db.execute(
            "SELECT a.*, p.intention FROM actions a"
            " JOIN plans p ON p.id = a.plan_id"
            " ORDER BY a.id DESC LIMIT ?",
            (limite,),
        ).fetchall()

    journal = []
    for ligne in lignes:
        entree = _action_en_dict(ligne)
        # L'intention d'origine donne le contexte : "pourquoi cette action ?"
        entree["intention"] = ligne["intention"]
        journal.append(entree)
    return journal
