# SPEC — LE BRAS

**Binôme :** Pierre Rouvellat & Kevin Rigal
**Sujet choisi :** 03 — LE BRAS
**Hackathon Full Stack Agentique IA — Jour 1, matin**

---

## 1. Le problème

Quand une équipe accueille un nouvel arrivant, une dizaine de petites actions doivent être faites
dans cinq outils différents : créer un ticket d'onboarding, envoyer un message de bienvenue,
poser une réunion, créer la fiche en base, générer un document d'accueil.
Personne n'oublie la tâche importante ; tout le monde oublie les trois petites.
Un assistant qui sait *agir* pourrait tout faire — mais on ne laisse pas une IA écrire dans
nos outils sans regarder. LE BRAS résout les deux moitiés : il planifie tout, et il n'exécute
que ce qu'un humain a coché.

---

## 2. User stories

| # | User story | Critère de réussite observable |
|---|---|---|
| US1 | En tant que manager, je veux exprimer une intention en français (« prépare l'arrivée de Sarah lundi ») afin d'obtenir un plan d'actions concret sans remplir de formulaire. | Un plan d'au moins 3 actions s'affiche, chacune lisible en une phrase. |
| US2 | En tant que manager, je veux approuver ou refuser chaque action une par une, afin de garder le contrôle sur ce qui part réellement. | Je refuse une action : elle n'est pas exécutée, et rien dans le système ne la contient. |
| US3 | En tant que manager, je veux consulter le journal de ce qui a été fait et annuler la dernière action, afin de réparer une erreur sans appeler un développeur. | Le journal liste horodatage, outil, paramètres et résultat. L'annulation fait disparaître l'objet créé. |

---

## 3. Hors scope

1. **Pas de mode d'exécution automatique, même derrière un drapeau de configuration.**
   Le seul garde-fou qui protège vraiment est celui qu'on ne peut pas désactiver. Ajouter une
   option « exécuter sans valider » transformerait notre cœur technique en réglage, donc en dette :
   le jour où quelqu'un l'active, tout le reste du projet ne sert plus à rien. La validation
   humaine n'est pas une fonctionnalité de LE BRAS, c'en est la définition.
2. **Pas d'intégration avec de vraies API tierces** (Slack, GitHub, Google Calendar).
   Nos outils écrivent dans une base SQLite locale et dans un dossier `outbox/`. Les signatures
   typées sont identiques à celles d'un vrai service : remplacer l'implémentation est un changement
   d'une fonction, pas d'architecture. Une authentification OAuth coûte une demi-journée et ne
   rapporte aucun point du barème.
3. **Pas d'authentification ni de multi-utilisateurs.** Un seul utilisateur suffit à démontrer le
   pattern human-in-the-loop. Gérer des comptes déplacerait notre effort vers du CRUD.
4. **Pas de conversation multi-tours.** Une intention produit un plan. Pour changer d'avis, on
   relance une intention. Maintenir un état de dialogue est un problème à part entière.
5. **Pas de re-planification automatique après un refus.** C'est un bonus du sujet, pas le MVP.
   On le fera seulement si le palier 4 est validé en avance.
6. **Pas d'actions programmées dans le temps.** Cela demanderait un processus permanent, donc du
   déploiement, donc du temps qu'on n'a pas.
7. **Pas de responsive mobile.** La démo se fait sur un écran de portable.
8. **Pas de tests end-to-end automatisés.** On teste unitairement les deux endroits où un bug est
   éliminatoire : l'idempotence, et le refus d'exécution non approuvée. Le reste est couvert par
   la démo rejouée.
9. **Pas de gestion de fichiers binaires ni de pièces jointes.** Nos outils manipulent du texte.
10. **Pas de streaming token par token.** Le plan s'affiche quand il est complet. Un plan à moitié
    affiché ne serait pas approuvable : le streaming n'apporterait ici qu'un effet visuel.

---

## 4. Architecture

```
┌──────────────┐
│  NAVIGATEUR  │  1. l'utilisateur tape son intention
│    (front)   │  3. il coche / décoche chaque action du plan
└──────┬───────┘  5. il lit le journal, il annule
       │ HTTP (JSON)
       ▼
┌──────────────────────────────────────────────┐
│                   API  (back)                │
│  POST /plans             → crée un plan      │
│  POST /plans/:id/execute → exécute l'approuvé│
│  GET  /audit             → renvoie le journal│
│  POST /audit/:id/undo    → annule une action │
└──────┬──────────────────────────┬────────────┘
       │                          │
       ▼                          ▼
┌──────────────────┐      ┌─────────────────────┐
│   PLANIFICATEUR  │      │     EXÉCUTEUR       │
│  (appelle le LLM)│      │ (appelle les outils)│
│                  │      │                     │
│  LECTURE SEULE   │      │  EFFETS DE BORD     │
│  ne peut RIEN    │      │  vérifie la clé     │
│  écrire          │      │  d'idempotence      │
└────────┬─────────┘      └─────────┬───────────┘
         │                          │
         │  ┌───────────────────────┘
         ▼  ▼
┌──────────────────────────────────────────────┐
│                   OUTILS                     │
│  lecture : list_team_members, get_template   │
│  écriture: create_issue, send_message, ...   │
└──────┬──────────────────────┬────────────────┘
       ▼                      ▼
┌──────────────┐      ┌────────────────┐
│  SQLite      │      │  outbox/       │
│  (données +  │      │  (faux service │
│   journal)   │      │   de messages) │
└──────────────┘      └────────────────┘
```

**La règle d'or :** le PLANIFICATEUR et l'EXÉCUTEUR sont deux modules séparés. Le planificateur
n'importe aucun outil à effet de bord — physiquement, il ne *peut pas* exécuter. C'est ce qui rend
impossible le scénario éliminatoire « l'agent exécute avant validation ». Ce n'est pas de la
discipline, c'est une contrainte d'architecture.

---

## 5. Les outils de l'agent

| Outil | Signature typée | Effet de bord | Clé d'idempotence |
|---|---|---|---|
| Lister l'équipe | `list_team_members(department: str) -> list[Person]` | **NON** | — |
| Lire un modèle d'accueil | `get_onboarding_template(role: str) -> Checklist` | **NON** | — |
| Chercher en base | `find_employee(name: str) -> Employee \| None` | **NON** | — |
| Créer un ticket | `create_issue(title: str, body: str, assignee: str, labels: list[str]) -> Issue` | **OUI** | hash(titre + assignee) |
| Envoyer un message | `send_message(to: str, subject: str, body: str) -> MessageReceipt` | **OUI** | hash(to + sujet + corps) |
| Créer une fiche employé | `create_employee(name: str, role: str, start_date: date, email: str) -> Employee` | **OUI** | email (UNIQUE en base) |
| Poser un événement | `create_calendar_event(title: str, start: datetime, duration_min: int, attendees: list[str]) -> Event` | **OUI** | hash(titre + start) |
| Générer un fichier | `save_document(filename: str, content: str) -> FileRef` | **OUI** | filename |

**Trois outils de lecture, volontairement.** Sans eux, le modèle ne décide rien : il déroule une
recette. Avec eux, il doit d'abord aller chercher de l'information, puis choisir.

**L'idempotence.** Avant d'exécuter une action à effet de bord, l'exécuteur calcule une
`idempotency_key` à partir du nom de l'outil et de ses arguments normalisés. Si cette clé existe
déjà au journal avec le statut `succès`, l'action n'est pas rejouée : on renvoie le résultat
précédent. Rejouer un plan deux fois ne crée donc jamais de doublon. Pour `create_employee`, la
clé est l'email parce que la base impose déjà une contrainte UNIQUE dessus : la clé métier existe,
on la réutilise plutôt que d'en inventer une.

---

## 6. Le happy path de la démo

1. J'ouvre l'application et je tape : **« Prépare l'arrivée de Sarah Martin, développeuse back-end, lundi prochain. »**
2. L'agent lit d'abord la base (outils de lecture), puis affiche un **plan de 5 actions**, chacune sur une carte : créer la fiche employé, créer le ticket d'onboarding, envoyer le message de bienvenue, poser la réunion d'intégration, générer le document d'accueil.
3. J'**approuve 4 actions** et je **refuse** l'envoi du message de bienvenue (« je veux l'écrire moi-même »).
4. Je clique sur **Exécuter**. Les 4 actions approuvées partent une par une, chaque carte passe au vert. La carte refusée reste grise et sa fonction n'est jamais appelée.
5. J'ouvre le **journal d'audit** : 4 lignes horodatées, avec pour chacune l'outil appelé, les paramètres envoyés, le résultat reçu et la clé d'idempotence.
6. J'**annule la dernière action** (l'événement de calendrier). L'objet disparaît de la base, et le journal conserve la trace de la création *et* de l'annulation.

**Le cas d'échec géré (1 minute) :** je relance exactement le même plan une seconde fois.
L'idempotence bloque les doublons : aucune action n'est rejouée, et le journal affiche pour
chacune « déjà exécutée, résultat précédent renvoyé ». Rien n'est dupliqué en base.

---

## 7. Choix techniques — et ce qu'on a écarté

| Brique | Notre choix | Écarté, et pourquoi |
|---|---|---|
| Langage back | Python | Node/TypeScript : on veut pouvoir expliquer chaque ligne à l'oral, on prend le langage qu'on maîtrise le mieux. |
| Framework back | FastAPI | Django : trop de conventions implicites à défendre pour 3 jours. FastAPI donne des routes lisibles et des types natifs. |
| Fournisseur de modèle | Anthropic (Claude) | MiniMax : nous n'avions aucune donnée fiable sur la qualité de son tool calling, qui est la capacité dont dépend tout notre projet. On a préféré un fournisseur dont on peut vérifier la documentation. |
| SDK d'agent | **Aucun** — appel direct au SDK du fournisseur | LangChain : son `AgentExecutor` exécute automatiquement les outils, ce qui est exactement l'inverse de notre cœur technique. LangGraph a bien une primitive d'interruption adaptée, mais elle nous obligeait à défendre à l'oral un state graph et un checkpointer qu'on n'a pas écrits. Notre boucle fait une quarantaine de lignes et on peut la dérouler au tableau. |
| Base de données | SQLite | PostgreSQL : nécessite Docker, ce qui casse le « on clone et ça démarre » du barème. |
| Front | HTML / CSS / JS sans framework | React : ajoute une étape de build à expliquer, alors que le front n'est pas le cœur du sujet. |
| Hébergement | Local pour la démo | Déploiement : hors scope tant que le palier 4 n'est pas validé. |

---

## 8. Partage du travail

**Pierre : le back. Kevin : le front.**

| Bloc | Responsable |
|---|---|
| Planificateur + prompt système | Pierre |
| Exécuteur + idempotence | Pierre |
| Outils de lecture et d'écriture + faux services | Pierre |
| Base de données + journal d'audit | Pierre |
| API : les 4 routes | Pierre |
| Front : saisie de l'intention | Kevin |
| Front : cartes d'approbation (approuver / refuser) | Kevin |
| Front : journal d'audit + bouton d'annulation | Kevin |
| Contrat d'interface (format JSON échangé entre front et back) | les deux, décidé ensemble avant de coder |
| README / AGENTS.md | Pierre |
| JOURNAL.md | les deux, chacun ses entrées |
