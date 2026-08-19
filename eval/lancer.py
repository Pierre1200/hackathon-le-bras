"""
Le lanceur d'evaluation : rejoue tous les cas et sort un score chiffre.

    make eval

Chaque execution appelle reellement le modele — c'est le but, on mesure le
comportement reel. Le cout total est affiche a la fin : on sait ce que coute
une campagne d'evaluation.

La base de donnees est isolee dans un dossier temporaire : lancer l'evaluation
ne touche jamais aux donnees de l'application.
"""

import os
import sys
import tempfile
import time

# --- AVANT tout import du projet : on isole la base ---
# Les modules du projet lisent ces variables au moment de leur import.
# load_dotenv() n'ecrase pas une variable deja definie, donc celles-ci gagnent.
_temp = tempfile.mkdtemp(prefix="lebras-eval-")
os.environ["DATABASE_URL"] = f"sqlite:///{_temp}/eval.db"
os.environ["OUTBOX_DIR"] = f"{_temp}/outbox"
os.environ["DOCS_DIR"] = f"{_temp}/documents"

import logging  # noqa: E402

# On fait taire les journaux techniques : cette commande est lancee devant
# quelqu'un, et une trace HTTP par appel rendrait le score illisible. Les
# erreurs restent affichees.
for nom in ("httpx", "httpcore", "openai", "le_bras.outils"):
    logging.getLogger(nom).setLevel(logging.ERROR)

from fastapi.testclient import TestClient  # noqa: E402

from back.main import app  # noqa: E402
from eval.cas import CAS, outils_executes, outils_proposes  # noqa: E402

VERT = "\033[32m"
ROUGE = "\033[31m"
GRIS = "\033[90m"
GRAS = "\033[1m"
FIN = "\033[0m"


def lancer() -> int:
    client = TestClient(app)

    if not os.getenv("LLM_API_KEY"):
        print(f"{ROUGE}LLM_API_KEY absente : renseigne-la dans le .env.{FIN}")
        return 2

    total_verifications = 0
    verifications_reussies = 0
    cas_reussis = 0
    cout_total = 0.0
    debut_campagne = time.perf_counter()

    print(f"\n{GRAS}EVALUATION — {len(CAS)} cas{FIN}\n")

    for cas in CAS:
        print(f"{GRAS}[{cas['id']}]{FIN} « {cas['intention'][:70]}… »")

        debut = time.perf_counter()
        reponse_http = client.post("/api/message", json={"message": cas["intention"]})
        duree = time.perf_counter() - debut

        if reponse_http.status_code != 200:
            print(f"  {ROUGE}ECHEC APPEL{FIN} — HTTP {reponse_http.status_code} :"
                  f" {reponse_http.json().get('detail')}")
            total_verifications += len(cas["verifications"])
            print()
            continue

        reponse = reponse_http.json()
        cout_total += reponse["cout_dollars"]

        executes = sorted(outils_executes(reponse)) or ["—"]
        proposes = sorted(outils_proposes(reponse)) or ["—"]
        print(f"  {GRIS}executes : {', '.join(executes)}{FIN}")
        print(f"  {GRIS}proposes : {', '.join(proposes)}{FIN}")

        tout_bon = True
        for libelle, verifier in cas["verifications"]:
            total_verifications += 1
            try:
                ok = bool(verifier(reponse))
            except Exception as e:
                ok = False
                libelle = f"{libelle} (verification en erreur : {e})"
            if ok:
                verifications_reussies += 1
                print(f"  {VERT}v{FIN} {libelle}")
            else:
                tout_bon = False
                print(f"  {ROUGE}x{FIN} {libelle}")

        if tout_bon:
            cas_reussis += 1

        print(f"  {GRIS}{duree:.1f} s — {reponse['cout_dollars'] * 100:.3f} centime{FIN}\n")

    duree_campagne = time.perf_counter() - debut_campagne
    score = round(100 * verifications_reussies / total_verifications) if total_verifications else 0
    couleur = VERT if score == 100 else ROUGE

    print(f"{GRAS}{'─' * 58}{FIN}")
    print(f"{GRAS}SCORE : {couleur}{score} %{FIN}"
          f"  ({verifications_reussies}/{total_verifications} verifications, "
          f"{cas_reussis}/{len(CAS)} cas complets)")
    print(f"{GRIS}campagne : {duree_campagne:.1f} s — cout total "
          f"{cout_total * 100:.2f} centime{FIN}\n")

    # Code de sortie non nul si tout n'est pas vert : utilisable en integration
    # continue, et honnete si on le lance devant quelqu'un.
    return 0 if verifications_reussies == total_verifications else 1


if __name__ == "__main__":
    sys.exit(lancer())
