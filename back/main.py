"""
main.py — Le serveur web (l'API).

Son role
--------
Faire le pont entre le navigateur et le modele :
    navigateur  --HTTP-->  cette API  --appel LLM-->  fournisseur

C'est important pour la securite, et c'est la reponse a la question du
checkpoint "ou sont vos cles d'API ?" : la cle vit uniquement ici, cote
serveur. Le navigateur ne parle qu'a NOUS. Si le front appelait le
fournisseur directement, il faudrait lui donner la cle, et n'importe qui
pourrait la lire dans le code de la page.

Ce fichier ne sait pas quel fournisseur est utilise : il appelle
`demander_au_modele()` et c'est tout. Toute la connaissance du fournisseur
est enfermee dans llm.py.

Lancement :
    .venv/bin/uvicorn back.main:app --reload
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# On importe NOTRE fonction et NOTRE erreur. Aucune trace du fournisseur ici.
from back.llm import MODELE, ErreurLLM, demander_au_modele

# `app` est l'objet serveur. C'est lui que uvicorn va chercher quand on lance
# `uvicorn back.main:app` — ce qui se lit : dans le module back.main, prends
# la variable qui s'appelle app.
app = FastAPI(
    title="LE BRAS",
    description="Un agent qui prepare des actions et n'execute que ce qui est approuve.",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
# Par securite, un navigateur interdit a une page servie depuis une origine
# (par exemple http://localhost:5500, le front de Kevin) d'appeler une API
# situee sur une autre origine (http://localhost:8000, nous). Ca s'appelle la
# "same-origin policy".
#
# Ce middleware ajoute les en-tetes qui autorisent explicitement ces appels.
# Sans lui, le front de Kevin recevrait une erreur CORS dans la console et
# on perdrait une heure a chercher pourquoi.
#
# allow_origins=["*"] veut dire "n'importe quelle origine". C'est acceptable
# en developpement local. A restreindre au vrai domaine du front le jour ou
# on deploie : c'est note dans les limites connues du README.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# LA FORME DES DONNEES ATTENDUES
# ---------------------------------------------------------------------------
class DemandeMessage(BaseModel):
    """
    Decrit ce que le front doit nous envoyer sur POST /api/message.

    Heriter de `BaseModel` (Pydantic) fait deux choses automatiquement :
      1. FastAPI valide la requete AVANT d'appeler notre fonction. Si le champ
         `message` est absent ou vide, le front recoit une erreur 422 claire
         et notre code n'est meme pas execute.
      2. La documentation interactive sur /docs est generee toute seule a
         partir de cette classe.

    C'est notre premiere ligne de defense : on ne fait jamais confiance a ce
    qui vient du navigateur.
    """
    # `...` (Ellipsis) signifie : ce champ est OBLIGATOIRE.
    # min_length=1 refuse la chaine vide, max_length=2000 evite qu'on nous
    # envoie un roman qui couterait cher en tokens.
    message: str = Field(..., min_length=1, max_length=2000)


# ---------------------------------------------------------------------------
# LES ROUTES
# ---------------------------------------------------------------------------

@app.get("/api/sante")
def sante():
    """
    Route de sante : dit simplement "je suis vivant".

    A quoi ca sert concretement :
      - Kevin peut verifier que le back tourne avant de debugger son front.
      - L'hebergeur s'en sert pour savoir si l'application repond.
      - Au checkpoint, ca prouve en une seconde que le serveur est demarre.

    Elle n'appelle pas le modele : elle doit rester instantanee et gratuite.
    """
    return {"statut": "ok", "modele": MODELE}


@app.post("/api/message")
def envoyer_message(demande: DemandeMessage):
    """
    Envoie le message de l'utilisateur au modele et renvoie sa reponse.

    FastAPI lit le corps JSON de la requete, le valide contre DemandeMessage,
    et nous le passe deja transforme en objet Python. On n'ecrit aucune ligne
    de parsing nous-memes.

    Au palier 2, cette route ne fait que prouver que le tuyau passe.
    Au palier 3, c'est ici que le planificateur prendra sa place.
    """
    try:
        reponse = demander_au_modele(demande.message)

    except ErreurLLM as e:
        # On attrape NOTRE erreur (jamais celle du fournisseur) et on la
        # traduit en reponse HTTP.
        #
        # 502 = "Bad Gateway" : le bon code quand un service dont on depend
        # a echoue. On evite le 500, qui dirait a tort que c'est NOTRE code
        # qui a plante.
        #
        # str(e) contient un message ecrit par nous, en francais, comprehensible
        # par l'utilisateur. On ne renvoie jamais la trace technique brute au
        # navigateur : ca fuiterait des details internes.
        raise HTTPException(status_code=502, detail=str(e))

    # FastAPI transforme automatiquement ce dictionnaire en JSON.
    # Ce format est le CONTRAT D'INTERFACE avec Kevin : s'il change, il faut
    # le prevenir, sinon son front casse.
    return {
        "reponse": reponse.texte,
        "modele": reponse.modele,
        "tokens_entree": reponse.tokens_entree,
        "tokens_sortie": reponse.tokens_sortie,
        # On arrondit a 6 decimales : un appel coute des fractions de centime,
        # et on veut afficher le cout a l'ecran (carte bonus "cout affiche").
        "cout_dollars": round(reponse.cout_dollars, 6),
    }
