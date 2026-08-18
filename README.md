# LE BRAS

> Un agent qui ne se contente pas de parler : il agit. Mais rien ne part sans vous.

Hackathon Full Stack Agentique IA — Holberton School. Sujet 03.
**Binôme :** Pierre Rouvellat (back) & Kevin Rigal (front)

---

## Quickstart

**Prérequis :** Python 3.11+ et une clé d'API Anthropic.

```bash
git clone https://github.com/Pierre1200/hackathon-le-bras.git
cd hackathon-le-bras

python3 -m venv .venv
source .venv/bin/activate          # sous Windows : .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # puis ouvrez .env et collez votre clé
```

Dans `.env`, remplacez la valeur de `ANTHROPIC_API_KEY` par votre clé. Puis :

```bash
uvicorn back.main:app --reload
```

L'API tourne sur **http://127.0.0.1:8000**.

**Vérifier que ça marche en 10 secondes**, dans un autre terminal :

```bash
curl http://127.0.0.1:8000/api/sante
```

Réponse attendue : `{"statut":"ok","modele":"claude-opus-5"}`

Et pour un vrai appel au modèle :

```bash
curl -X POST http://127.0.0.1:8000/api/message \
  -H "Content-Type: application/json" \
  -d '{"message":"Bonjour, réponds en une phrase."}'
```

Une documentation interactive est aussi générée automatiquement sur
**http://127.0.0.1:8000/docs** : on peut y essayer les routes depuis le navigateur,
sans écrire une ligne de `curl`.

---

## Ce que fait le projet

L'utilisateur exprime une intention en français (« prépare l'arrivée de Sarah lundi »).
L'agent construit un plan d'actions concrètes, l'affiche, et **n'exécute que ce que
l'utilisateur a approuvé, action par action**. Chaque exécution est tracée dans un
journal d'audit consultable et annulable.

Le détail du cadrage (scope, hors-scope, outils, démo) est dans [SPEC.md](SPEC.md).

---

## Architecture

```
navigateur  ──HTTP──▶  API (FastAPI)  ──▶  llm.py  ──▶  fournisseur de modèle
                            │
                            ├── planificateur  (lecture seule)
                            └── exécuteur      (effets de bord)
```

Deux principes qui structurent tout le code :

**1. La clé d'API ne quitte jamais le serveur.** Le navigateur ne parle qu'à notre API ;
c'est notre API qui parle au fournisseur. Si le front appelait le fournisseur directement,
il faudrait lui confier la clé, et n'importe qui pourrait la lire dans le code de la page.

**2. Le planificateur et l'exécuteur sont deux modules séparés.** Le planificateur
n'importe aucun outil à effet de bord : il ne *peut pas* exécuter. Ce n'est pas de la
discipline, c'est une contrainte d'architecture — c'est ce qui rend impossible le
scénario « l'agent exécute avant validation ».

### Les fichiers

| Fichier | Rôle |
|---|---|
| `back/main.py` | Le serveur et ses routes. Ne connaît aucun fournisseur. |
| `back/llm.py` | **Le seul fichier qui parle au fournisseur.** Changer de fournisseur = réécrire ce fichier, et rien d'autre. |
| `front/` | Le front (Kevin). |
| `SPEC.md` | Le cadrage : scope, hors-scope, outils typés, happy path. |
| `AGENTS.md` | Prompts système, outils et signatures, schéma de la boucle. |
| `JOURNAL.md` | Notre travail avec l'IA. |

### Les routes

| Méthode | Route | Rôle |
|---|---|---|
| `GET` | `/api/sante` | Dit si le serveur tourne et quel modèle est configuré. N'appelle pas le modèle. |
| `POST` | `/api/message` | Envoie un message au modèle et renvoie sa réponse, avec les tokens et le coût. |

---

## Choix techniques

| Brique | Notre choix | Écarté, et pourquoi |
|---|---|---|
| Back | Python + FastAPI | Django : trop de conventions implicites à défendre en 3 jours. FastAPI valide les entrées et génère sa doc tout seul. |
| SDK d'agent | **Aucun** — appel direct au SDK du fournisseur | LangChain : son `AgentExecutor` exécute automatiquement les outils, ce qui est l'inverse de notre cœur technique. LangGraph a bien une primitive d'interruption adaptée, mais nous aurions dû défendre à l'oral un state graph et un checkpointer que nous n'avons pas écrits. Notre boucle tient en une quarantaine de lignes. |
| Fournisseur | Anthropic (Claude) | MiniMax : aucune donnée fiable sur la qualité de son *tool calling*, la capacité dont dépend tout le projet. |
| Base de données | SQLite | PostgreSQL : impose Docker, ce qui casse le « on clone et ça démarre ». |
| Front | HTML / CSS / JS sans framework | React : ajoute une étape de build, alors que le front n'est pas le cœur du sujet. |

---

## Coût

Chaque réponse de l'API renvoie les tokens consommés et le coût réel de l'appel :

```json
{ "tokens_entree": 34, "tokens_sortie": 62, "cout_dollars": 0.00172 }
```

Un aller-retour coûte de l'ordre de **0,2 centime**.

---

## Limites connues

- **Il faut votre propre clé d'API.** Sans clé valide dans `.env`, `/api/sante` répond
  toujours, mais `/api/message` renvoie une erreur 502 explicite. Nous ne commitons
  évidemment aucune clé.
- **Les services externes seront simulés** (palier 3 et suivants) : la messagerie
  écrira des fichiers dans `outbox/`, le reste vivra dans une base SQLite locale.
  C'est un choix documenté, pas un oubli — les signatures typées sont identiques à
  celles d'un vrai service.
- **CORS ouvert à toutes les origines** (`allow_origins=["*"]`), acceptable en
  développement local, à restreindre au domaine du front lors du déploiement.
- **Pas d'authentification** : un seul utilisateur. Hors scope assumé.
- **L'API est sans mémoire** : chaque appel est indépendant, il n'y a pas encore
  d'historique de conversation.
