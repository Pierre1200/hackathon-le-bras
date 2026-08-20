"""
La robustesse des outils, et les invariants qui empechent une erreur
d'inattention de casser le garde-fou.

Les deux tests d'invariant (a la fin) sont les plus utiles du fichier : ils
attrapent l'oubli qu'on fera forcement un jour — ajouter un outil d'ecriture
sans le declarer comme tel.
"""

from pathlib import Path

import pytest

from back import tools


# ---------------------------------------------------------------------------
# appeler_outil ne doit JAMAIS lever d'exception
# ---------------------------------------------------------------------------
# C'est ce qui permet a l'agent de dire "je n'ai pas pu" au lieu de faire
# tomber le serveur ou d'inventer une reponse.

def test_outil_inexistant_renvoie_une_erreur_lisible():
    """Le cas du checkpoint : le jury debranche un outil."""
    resultat = tools.appeler_outil("outil_qui_n_existe_pas", {})
    assert "erreur" in resultat
    assert "outil_qui_n_existe_pas" in resultat["erreur"]


def test_mauvais_arguments_renvoient_une_erreur_au_lieu_de_planter():
    """Le modele peut proposer des arguments qui ne correspondent pas."""
    resultat = tools.appeler_outil("lister_equipe", {"parametre_inconnu": "x"})
    assert "erreur" in resultat


def test_un_outil_qui_plante_est_rattrape(monkeypatch):
    """Meme une panne interne ne doit pas remonter jusqu'a l'utilisateur."""
    def outil_casse(**kwargs):
        raise RuntimeError("disque plein")

    monkeypatch.setitem(tools.OUTILS, "outil_casse", outil_casse)
    resultat = tools.appeler_outil("outil_casse", {})

    assert "erreur" in resultat
    assert "disque plein" in resultat["erreur"]


def test_annuler_un_outil_qui_ne_sait_pas_s_annuler():
    resultat = tools.annuler_outil("lister_equipe", {})
    assert "erreur" in resultat


# ---------------------------------------------------------------------------
# Validation des arguments proposes par le modele
# ---------------------------------------------------------------------------
# Cas rencontre en vrai avec un modele local plus faible : il inventait des
# noms de parametres. Sans validation, Python levait un TypeError affiche tel
# quel a l'utilisateur.

def test_argument_obligatoire_manquant_est_refuse_avant_execution():
    resultat = tools.appeler_outil(
        "creer_ticket", {"titre": "T", "description": "D"}  # assigne_a manque
    )
    assert "erreur" in resultat
    assert "assigne_a" in resultat["erreur"]

    # Et surtout : rien n'a ete ecrit en base.
    import sqlite3
    with sqlite3.connect(tools.DB_PATH) as db:
        assert db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 0


def test_nom_de_parametre_invente_est_refuse():
    """Le cas exact observe : le modele propose ses propres noms d'arguments."""
    resultat = tools.appeler_outil(
        "envoyer_message",
        {"prenom": "Lucas", "nom": "Digne", "contenu_de_la_messsage": "Bienvenue"},
    )
    assert "erreur" in resultat
    # Le message doit dire ce qui manque ET ce qui est en trop.
    assert "destinataire" in resultat["erreur"]
    assert "contenu_de_la_messsage" in resultat["erreur"]
    assert not [f for f in tools.OUTBOX_DIR.glob("*") if f.is_file()]


def test_arguments_valides_passent():
    """La validation ne doit pas bloquer un appel correct."""
    resultat = tools.appeler_outil(
        "creer_ticket", {"titre": "T", "description": "D", "assigne_a": "david"}
    )
    assert "erreur" not in resultat
    assert "id" in resultat


# ---------------------------------------------------------------------------
# Securite
# ---------------------------------------------------------------------------

def test_generer_document_neutralise_les_chemins(tmp_path):
    """
    Sans Path(...).name, un modele proposant '../../.env' ecraserait la
    configuration du projet. Le fichier doit rester dans documents/.
    """
    resultat = tools.generer_document("../../.env", "contenu malveillant")

    brut = Path(resultat["fichier"])
    chemin = (brut if brut.is_absolute() else tools.RACINE / brut).resolve()
    assert chemin.parent == tools.DOCS_DIR.resolve(), "le fichier est sorti de documents/"
    assert chemin.name == ".env"


# ---------------------------------------------------------------------------
# Comportement des outils de consultation
# ---------------------------------------------------------------------------

def test_la_recherche_ignore_accents_et_casse():
    """Un utilisateur ecrit 'Chloé', la base contient 'Chloe'."""
    tools.creer_fiche_employe(
        nom="Chloe Bernard", role="Designer", departement="Design",
        email="chloe@lebras.fr", date_arrivee="2026-01-01",
    )
    for saisie in ("Chloé", "chloe", "CHLOE", "Bernard"):
        trouves = tools.chercher_personne(saisie)
        assert [p["nom"] for p in trouves] == ["Chloe Bernard"], f"echec sur {saisie!r}"


def test_un_resultat_vide_n_est_pas_une_erreur():
    """L'agent doit pouvoir dire 'personne', pas inventer quelqu'un."""
    assert tools.lister_equipe("Service Juridique") == []
    assert "erreur" not in tools.appeler_outil("lister_equipe", {"departement": "Neant"})


def test_la_recherche_est_plafonnee():
    """Un outil bien fait renvoie peu : on ne remplit pas le contexte du modele."""
    for i in range(10):
        tools.creer_fiche_employe(
            nom=f"Testeur Numero{i}", role="Test", departement="Test",
            email=f"t{i}@lebras.fr", date_arrivee="2026-01-01",
        )
    assert len(tools.chercher_personne("Testeur")) <= 5


# ---------------------------------------------------------------------------
# LES INVARIANTS — ceux qui attrapent l'oubli de demain
# ---------------------------------------------------------------------------

def test_chaque_outil_a_un_schema_et_reciproquement():
    """
    Un outil sans schema est invisible pour le modele. Un schema sans fonction
    fait echouer l'appel. Les deux sont des oublis silencieux.
    """
    noms_schemas = {s["function"]["name"] for s in tools.SCHEMAS}
    assert set(tools.OUTILS) == noms_schemas


def test_chaque_outil_a_effet_de_bord_sait_s_annuler():
    """
    Sans annulation, l'etape 6 du parcours est impossible pour cet outil.
    Ce test le rappellera au moment ou on ajoutera le prochain.
    """
    sans_annulation = tools.OUTILS_A_EFFET_DE_BORD - set(tools.ANNULATIONS)
    assert sans_annulation == set()


def test_la_liste_des_effets_de_bord_ne_contient_que_de_vrais_outils():
    """
    Une faute de frappe dans OUTILS_A_EFFET_DE_BORD passerait inapercue et
    l'outil reellement dangereux serait execute sans validation.
    """
    assert tools.OUTILS_A_EFFET_DE_BORD <= set(tools.OUTILS)


@pytest.mark.parametrize("nom", sorted(tools.OUTILS_A_EFFET_DE_BORD))
def test_les_outils_d_ecriture_renvoient_de_quoi_s_annuler(nom):
    """
    Une annulation a besoin de l'identifiant de la ligne creee ou du chemin du
    fichier ecrit. Un outil qui ne renvoie rien d'utile serait inannulable.
    """
    exemples = {
        "creer_fiche_employe": {
            "nom": "Jean Test", "role": "Test", "departement": "Test",
            "email": "jean@lebras.fr", "date_arrivee": "2026-01-01",
        },
        "creer_ticket": {"titre": "T", "description": "D", "assigne_a": "A"},
        "envoyer_message": {"destinataire": "a@b.fr", "sujet": "S", "corps": "C"},
        "generer_document": {"nom_fichier": "test.md", "contenu": "C"},
    }
    resultat = tools.appeler_outil(nom, exemples[nom])
    assert "erreur" not in resultat
    assert "id" in resultat or "fichier" in resultat
