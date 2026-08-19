"""
Les garanties que le projet promet. Si un seul de ces tests casse, LE BRAS ne
tient plus sa promesse — c'est pour ca qu'ils existent.

AUCUN de ces tests n'appelle le modele. On fabrique les plans directement en
base, exactement comme le planificateur le ferait, et on teste ce qui vient
apres : l'approbation, l'execution, l'idempotence et l'annulation. C'est la
partie ou une erreur a des consequences reelles.
"""

import sqlite3

from fastapi.testclient import TestClient

from back import persistance, tools
from back.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Aides
# ---------------------------------------------------------------------------

ACTION_FICHE = {
    "outil": "creer_fiche_employe",
    "arguments": {
        "nom": "Sarah Martin",
        "role": "Developpeuse back-end",
        "departement": "Ingenierie",
        "email": "sarah.martin@lebras.fr",
        "date_arrivee": "2026-08-24",
    },
}
ACTION_MESSAGE = {
    "outil": "envoyer_message",
    "arguments": {
        "destinataire": "sarah.martin@lebras.fr",
        "sujet": "Bienvenue",
        "corps": "A lundi !",
    },
}


def creer_plan(actions):
    """Fabrique un plan en base, comme le ferait le planificateur."""
    return persistance.enregistrer_plan(
        intention="Prepare l'arrivee de Sarah Martin.",
        reponse="Je propose des actions.",
        modele="test", tokens_entree=0, tokens_sortie=0, cout_dollars=0.0,
        trace=[], actions_proposees=actions,
    )


def compter_employes(nom):
    with sqlite3.connect(persistance.DB_PATH) as db:
        return db.execute(
            "SELECT COUNT(*) FROM employes WHERE nom = ?", (nom,)
        ).fetchone()[0]


def fichiers_outbox():
    return [f for f in tools.OUTBOX_DIR.glob("*") if f.is_file()]


# ---------------------------------------------------------------------------
# LA GARANTIE CENTRALE
# ---------------------------------------------------------------------------

def test_seules_les_actions_approuvees_sont_executees():
    """
    LA promesse du projet : ce qui n'est pas approuve n'arrive pas.

    On propose deux actions, on n'en approuve qu'une. L'autre ne doit pas
    seulement etre marquee refusee : son effet de bord ne doit pas exister.
    """
    plan_id = creer_plan([ACTION_FICHE, ACTION_MESSAGE])
    plan = persistance.lire_plan(plan_id)
    id_fiche, id_message = [a["id"] for a in plan["actions"]]

    reponse = client.post(
        f"/api/plans/{plan_id}/executer", json={"approuvees": [id_fiche]}
    )
    assert reponse.status_code == 200

    statuts = {a["outil"]: a["statut"] for a in reponse.json()["actions"]}
    assert statuts["creer_fiche_employe"] == persistance.EXECUTEE
    assert statuts["envoyer_message"] == persistance.REFUSEE

    # On ne se contente pas du statut : on verifie l'effet REEL.
    assert compter_employes("Sarah Martin") == 1
    assert fichiers_outbox() == [], "un message a ete envoye alors qu'il etait refuse"


def test_aucune_approbation_signifie_aucune_execution():
    """Le defaut, c'est non : une liste vide ne doit rien declencher."""
    plan_id = creer_plan([ACTION_FICHE, ACTION_MESSAGE])

    reponse = client.post(f"/api/plans/{plan_id}/executer", json={"approuvees": []})

    assert all(a["statut"] == persistance.REFUSEE for a in reponse.json()["actions"])
    assert compter_employes("Sarah Martin") == 0
    assert fichiers_outbox() == []


def test_action_d_un_autre_plan_est_rejetee():
    """
    Sans ce controle, on pourrait faire executer n'importe quelle action en
    devinant son numero. Et on refuse la requete ENTIERE : une execution
    partielle silencieuse serait pire qu'une erreur.
    """
    plan_a = creer_plan([ACTION_FICHE])
    plan_b = creer_plan([ACTION_MESSAGE])
    action_de_a = persistance.lire_plan(plan_a)["actions"][0]["id"]

    reponse = client.post(
        f"/api/plans/{plan_b}/executer", json={"approuvees": [action_de_a]}
    )

    assert reponse.status_code == 400
    assert compter_employes("Sarah Martin") == 0


# ---------------------------------------------------------------------------
# L'IDEMPOTENCE
# ---------------------------------------------------------------------------

def test_la_cle_ne_depend_pas_de_l_ordre_des_arguments():
    """
    Deux dictionnaires identiques peuvent s'ecrire dans un ordre different.
    Sans tri, la meme action produirait deux empreintes et l'idempotence ne
    servirait a rien.
    """
    a = persistance.calculer_cle_idempotence("outil", {"x": 1, "y": 2})
    b = persistance.calculer_cle_idempotence("outil", {"y": 2, "x": 1})
    assert a == b

    assert a != persistance.calculer_cle_idempotence("outil", {"x": 1, "y": 3})
    assert a != persistance.calculer_cle_idempotence("autre", {"x": 1, "y": 2})


def test_redemander_la_meme_chose_ne_cree_pas_de_doublon():
    """Le scenario reel : l'utilisateur relance la meme demande."""
    premier = creer_plan([ACTION_FICHE])
    id_1 = persistance.lire_plan(premier)["actions"][0]["id"]
    client.post(f"/api/plans/{premier}/executer", json={"approuvees": [id_1]})
    assert compter_employes("Sarah Martin") == 1

    second = creer_plan([ACTION_FICHE])       # memes arguments exactement
    id_2 = persistance.lire_plan(second)["actions"][0]["id"]
    reponse = client.post(f"/api/plans/{second}/executer", json={"approuvees": [id_2]})

    action = reponse.json()["actions"][0]
    assert action["statut"] == persistance.EXECUTEE
    assert action["resultat"]["deja_executee"] is True
    assert action["resultat"]["action_origine"] == id_1
    assert compter_employes("Sarah Martin") == 1, "l'idempotence n'a pas empeche le doublon"


def test_double_clic_sur_executer_ne_rejoue_rien():
    """Rappeler la route ne doit avoir aucun effet."""
    plan_id = creer_plan([ACTION_FICHE])
    action_id = persistance.lire_plan(plan_id)["actions"][0]["id"]

    client.post(f"/api/plans/{plan_id}/executer", json={"approuvees": [action_id]})
    client.post(f"/api/plans/{plan_id}/executer", json={"approuvees": [action_id]})

    assert compter_employes("Sarah Martin") == 1


# ---------------------------------------------------------------------------
# L'ANNULATION
# ---------------------------------------------------------------------------

def test_annuler_defait_vraiment_l_effet():
    plan_id = creer_plan([ACTION_FICHE])
    action_id = persistance.lire_plan(plan_id)["actions"][0]["id"]
    client.post(f"/api/plans/{plan_id}/executer", json={"approuvees": [action_id]})
    assert compter_employes("Sarah Martin") == 1

    reponse = client.post(f"/api/actions/{action_id}/annuler")

    assert reponse.status_code == 200
    assert reponse.json()["actions"][0]["statut"] == persistance.ANNULEE
    assert compter_employes("Sarah Martin") == 0


def test_on_ne_peut_pas_annuler_ce_qui_n_a_pas_ete_execute():
    plan_id = creer_plan([ACTION_FICHE])
    action_id = persistance.lire_plan(plan_id)["actions"][0]["id"]
    client.post(f"/api/plans/{plan_id}/executer", json={"approuvees": []})  # refusee

    reponse = client.post(f"/api/actions/{action_id}/annuler")

    assert reponse.status_code == 400
    assert "refusee" in reponse.json()["detail"]


def test_on_ne_peut_pas_annuler_un_doublon():
    """
    Cas subtil : une action dedoublonnee porte le statut "executee" mais n'a
    rien execute. L'annuler supprimerait un effet dont une AUTRE action se
    croit encore proprietaire.
    """
    premier = creer_plan([ACTION_FICHE])
    id_1 = persistance.lire_plan(premier)["actions"][0]["id"]
    client.post(f"/api/plans/{premier}/executer", json={"approuvees": [id_1]})

    second = creer_plan([ACTION_FICHE])
    id_2 = persistance.lire_plan(second)["actions"][0]["id"]
    client.post(f"/api/plans/{second}/executer", json={"approuvees": [id_2]})

    reponse = client.post(f"/api/actions/{id_2}/annuler")

    assert reponse.status_code == 400
    assert str(id_1) in reponse.json()["detail"], "le message doit dire quoi annuler"
    assert compter_employes("Sarah Martin") == 1, "l'effet d'origine a ete detruit"


# ---------------------------------------------------------------------------
# LA PERSISTANCE
# ---------------------------------------------------------------------------

def test_le_plan_survit_au_rechargement_de_la_page():
    """Le jury rechargera la page en plein milieu."""
    plan_id = creer_plan([ACTION_FICHE, ACTION_MESSAGE])
    action_id = persistance.lire_plan(plan_id)["actions"][0]["id"]
    client.post(f"/api/plans/{plan_id}/executer", json={"approuvees": [action_id]})

    # Ce que fait le front au chargement de la page.
    restaure = client.get("/api/plans/dernier").json()

    assert restaure["id"] == plan_id
    assert [a["statut"] for a in restaure["actions"]] == [
        persistance.EXECUTEE,
        persistance.REFUSEE,
    ]


def test_le_journal_garde_aussi_ce_qui_n_a_pas_ete_fait():
    """Savoir ce qui n'a PAS ete fait fait partie de l'audit."""
    plan_id = creer_plan([ACTION_FICHE, ACTION_MESSAGE])
    action_id = persistance.lire_plan(plan_id)["actions"][0]["id"]
    client.post(f"/api/plans/{plan_id}/executer", json={"approuvees": [action_id]})

    entrees = client.get("/api/journal").json()["entrees"]

    statuts = {e["outil"]: e["statut"] for e in entrees}
    assert statuts["creer_fiche_employe"] == persistance.EXECUTEE
    assert statuts["envoyer_message"] == persistance.REFUSEE
    # L'intention d'origine repond a "pourquoi l'agent a fait ca ?"
    assert all("Sarah Martin" in e["intention"] for e in entrees)
