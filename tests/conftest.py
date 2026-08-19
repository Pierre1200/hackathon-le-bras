"""
conftest.py — la preparation commune a tous les tests.

Le point important : on bascule la base de donnees vers un fichier de test
AVANT d'importer les modules du projet. `back/persistance.py` et
`back/tools.py` lisent DATABASE_URL au moment de leur import ; si on changeait
la variable apres, il serait trop tard et les tests ecriraient dans la vraie
base.

pytest charge conftest.py avant tout le reste, c'est donc le seul endroit ou
on peut le faire proprement.
"""

import os
import tempfile
from pathlib import Path

# --- AVANT tout import du projet ---
_dossier_temporaire = tempfile.mkdtemp(prefix="lebras-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_dossier_temporaire}/test.db"
os.environ["OUTBOX_DIR"] = f"{_dossier_temporaire}/outbox"
os.environ["DOCS_DIR"] = f"{_dossier_temporaire}/documents"
# Cle bidon : aucun test ne doit appeler le modele. Si l'un d'eux essayait,
# il echouerait franchement au lieu de depenser de l'argent en silence.
os.environ.setdefault("LLM_API_KEY", "cle-de-test-invalide")

import pytest  # noqa: E402

from back import persistance, tools  # noqa: E402


@pytest.fixture(autouse=True)
def base_propre():
    """
    Vide les tables avant CHAQUE test.

    autouse=True : s'applique automatiquement, sans avoir a la demander dans
    chaque test. Un test qui laisserait des donnees derriere lui fausserait le
    suivant — et un test dont le resultat depend de l'ordre d'execution ne vaut
    rien.
    """
    with persistance._connexion() as db:
        db.execute("DELETE FROM actions")
        db.execute("DELETE FROM plans")
        db.execute("DELETE FROM tickets")
        db.execute("DELETE FROM employes")
    for dossier in (tools.OUTBOX_DIR, tools.DOCS_DIR):
        for fichier in Path(dossier).glob("*"):
            if fichier.is_file():
                fichier.unlink()
    yield
