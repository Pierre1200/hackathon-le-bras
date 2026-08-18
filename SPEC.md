# SPEC — LE BRAS

> **⚠️ NOTES DE PRÉPARATION — À SUPPRIMER AVANT LE CHECKPOINT**
> Toutes les lignes qui commencent par `> 💬` sont des notes pour vous, pas pour le jury.
> Pour les retrouver toutes avant de rendre : `grep -n "💬" SPEC.md`

**Binôme :** Kevin Rigal & Pierre Rouvellat
**Sujet choisi :** 03 — LE BRAS
**Date :** [[jour 1, matin]]

---

## 1. Le problème (5 lignes)

> 💬 Le jury lit ça en 20 secondes. Pas de jargon, pas de "solution innovante". Décris une douleur réelle.

Quand une équipe accueille un nouvel arrivant, une dizaine de petites actions doivent être faites
dans cinq outils différents : créer un ticket d'onboarding, envoyer un message de bienvenue,
poser une réunion, créer la fiche en base, générer un document d'accueil.
Personne n'oublie la tâche importante ; tout le monde oublie les trois petites.
Un assistant qui sait *agir* pourrait tout faire — mais on ne laisse pas une IA écrire dans
nos outils sans regarder. LE BRAS résout les deux moitiés du problème : il planifie tout,
et il n'exécute que ce qu'un humain a coché.

---

## 2. User stories (3 maximum)

> 💬 Format : En tant que X, je veux Y, afin de Z. Une story = une chose vérifiable à la démo.

| # | User story | Critère de réussite (observable) |
|---|---|---|
| US1 | En tant que manager, je veux exprimer une intention en français (« prépare l'arrivée de Sarah lundi ») afin d'obtenir un plan d'actions concret sans remplir de formulaire. | Un plan d'au moins 3 actions s'affiche, chacune lisible en une phrase. |
| US2 | En tant que manager, je veux approuver ou refuser chaque action une par une, afin de garder le contrôle sur ce qui part réellement. | Je refuse une action : elle n'est pas exécutée, et rien dans le système ne la contient. |
| US3 | En tant que manager, je veux consulter le journal de ce qui a été fait et pouvoir annuler la dernière action, afin de réparer une erreur sans appeler un développeur. | Le journal liste l'horodatage, l'outil, les paramètres et le résultat. L'annulation fait disparaître l'objet créé. |

---

## 3. Hors scope

> 💬 **Le jury lit cette section AVANT le scope.** Elle doit être plus longue et mieux argumentée.
> 💬 Chaque ligne = ce qu'on ne fait PAS + pourquoi. Un "non" sans raison ne vaut rien.

1. **Pas de mode d'exécution automatique, même derrière un drapeau de configuration.** ⭐
   Le seul garde-fou qui protège vraiment est celui qu'on ne peut pas désactiver. Ajouter une option
   « exécuter sans valider » transformerait notre cœur technique en réglage, donc en dette : le jour où
   quelqu'un l'active, tout le reste du projet ne sert plus à rien. La validation humaine n'est pas
   une fonctionnalité de LE BRAS, c'en est la définition.
2. **Pas d'intégration avec de vraies API tierces** (Slack, GitHub, Google Calendar).
   Nos outils écrivent dans une base SQLite locale et dans un dossier `outbox/`. Les signatures typées
   sont identiques à celles d'un vrai service : remplacer l'implémentation est un changement d'une
   fonction, pas d'architecture. Une authentification OAuth coûte une demi-journée et ne rapporte
   aucun point du barème.
3. **Pas d'authentification ni de multi-utilisateurs.** Un seul utilisateur suffit à démontrer le
   pattern human-in-the-loop. Gérer des comptes déplacerait notre effort du cœur agentique vers du CRUD.
4. **Pas de conversation multi-tours.** Une intention produit un plan. Pour changer d'avis,
   on relance une intention. Maintenir un état de dialogue est un problème à part entière.
5. **Pas de re-planification automatique après un refus.** C'est un bonus du sujet, pas le MVP.
   On le fera seulement si le palier 4 est validé en avance.
6. **Pas d'actions programmées dans le temps** (scheduler, cron). Cela demanderait un processus
   qui tourne en permanence, donc du déploiement, donc du temps qu'on n'a pas.
7. **Pas de responsive mobile.** La démo se fait sur un écran de portable. Le CSS mobile ne
   prouve rien sur notre maîtrise agentique.
8. **Pas de tests end-to-end automatisés.** On écrit des tests unitaires sur l'idempotence et sur
   le refus d'exécution non approuvée — les deux endroits où un bug est éliminatoire. Le reste
   est couvert par la démo rejouée.
9. **Pas de gestion de fichiers binaires ni de pièces jointes.** Nos outils manipulent du texte.
10. **Pas de streaming token par token de la réponse du modèle.** Le plan s'affiche quand il est
    complet. Un plan à moitié affiché ne serait pas approuvable, donc le streaming n'apporterait
    ici qu'un effet visuel.

> 💬 ⭐ = notre candidat pour la carte bonus « LE NON ARGUMENTÉ » (+5). Le n°2 est notre repli.
> 💬 Préparez-vous à défendre le n°1 à l'oral en 30 secondes, sans lire.

---

## 4. Architecture

> 💬 Une photo de tableau blanc est acceptée — faites les deux : ce schéma ici, ET dessinez-le au
> 💬 marqueur. Celui qui présente doit pouvoir le refaire de mémoire pendant que l'autre se tait.

```
┌──────────────┐
│  NAVIGATEUR  │  1. l'utilisateur tape son intention
│    (front)   │  3. il coche / décoche chaque action du plan
└──────┬───────┘  5. il lit le journal, il annule
       │ HTTP (JSON)
       ▼
┌──────────────────────────────────────────────┐
│                   API  (back)                │
│  POST /plans        → crée un plan           │
│  POST /plans/:id/execute → exécute l'approuvé│
│  GET  /audit        → renvoie le journal     │
│  POST /audit/:id/undo → annule une action    │
└──────┬──────────────────────────┬────────────┘
       │                          │
       ▼                          ▼
┌──────────────────┐      ┌────────────────────┐
│   PLANIFICATEUR  │      │    EXÉCUTEUR       │
│  (appelle le LLM)│      │ (appelle les outils)│
│                  │      │                    │
│  LECTURE SEULE   │      │  EFFETS DE BORD    │
│  ne peut RIEN    │      │  vérifie la clé    │
│  écrire          │      │  d'idempotence     │
└────────┬─────────┘      └─────────┬──────────┘
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

**La règle d'or de cette architecture :** le PLANIFICATEUR et l'EXÉCUTEUR sont deux modules séparés.
Le planificateur n'importe aucun outil à effet de bord — physiquement, il ne *peut pas* exécuter.
C'est ce qui rend impossible le scénario éliminatoire « l'agent exécute avant validation ».

---

## 5. Les outils de l'agent

> 💬 C'est LA section que le jury regarde en premier au palier 1.
> 💬 `recherche()` n'est pas une signature. `search(query: str, k: int) -> list[Doc]` en est une.
> 💬 Types partout, valeur de retour partout.

| Outil | Signature typée | Effet de bord | Idempotence |
|---|---|---|---|
| Lister l'équipe | `list_team_members(department: str) -> list[Person]` | **NON** | — |
| Lire un modèle d'accueil | `get_onboarding_template(role: str) -> Checklist` | **NON** | — |
| Chercher dans la base | `find_employee(name: str) -> Employee \| None` | **NON** | — |
| Créer un ticket | `create_issue(title: str, body: str, assignee: str, labels: list[str]) -> Issue` | **OUI** | clé = hash(titre + assignee) |
| Envoyer un message | `send_message(to: str, subject: str, body: str) -> MessageReceipt` | **OUI** | clé = hash(to + sujet + corps) |
| Créer une fiche employé | `create_employee(name: str, role: str, start_date: date, email: str) -> Employee` | **OUI** | clé = email (unique en base) |
| Poser un événement | `create_calendar_event(title: str, start: datetime, duration_min: int, attendees: list[str]) -> Event` | **OUI** | clé = hash(titre + start) |
| Générer un fichier | `save_document(filename: str, content: str) -> FileRef` | **OUI** | clé = filename |

**Idempotence — comment ça marche chez nous :** avant d'exécuter une action à effet de bord,
l'exécuteur calcule une `idempotency_key` à partir du nom de l'outil et de ses arguments normalisés.
Si cette clé existe déjà dans le journal avec le statut `succès`, l'action n'est pas rejouée :
on renvoie le résultat précédent. Rejouer un plan deux fois ne crée donc jamais de doublon.

> 💬 Question quasi certaine à l'oral : « pourquoi la clé de create_employee est l'email et pas un hash ? »
> 💬 Réponse : parce que la base impose déjà une contrainte UNIQUE dessus — la clé métier existe, on la réutilise
> 💬 plutôt que d'en inventer une. Pour les autres outils, il n'y a pas d'identifiant naturel, donc on hache.

---

## 6. Le happy path de la démo (6 étapes)

> 💬 Vous rejouerez exactement ces 6 étapes au palier 4 ET en soutenance. Ne les changez plus après le palier 1.
> 💬 Racontez-les au jury au présent, comme si le projet était déjà fini.

1. J'ouvre l'application et je tape : **« Prépare l'arrivée de Sarah Martin, développeuse back-end, lundi prochain. »**
2. L'agent lit d'abord la base (outils de lecture), puis affiche un **plan de 5 actions**, chacune sur une carte : créer la fiche employé, créer le ticket d'onboarding, envoyer le message de bienvenue, poser la réunion d'intégration, générer le document d'accueil.
3. J'**approuve 4 actions** et je **refuse** l'envoi du message de bienvenue (« je veux l'écrire moi-même »).
4. Je clique sur **Exécuter**. Les 4 actions approuvées partent une par une, chaque carte passe au vert. La carte refusée reste grise et n'est jamais appelée.
5. J'ouvre le **journal d'audit** : 4 lignes horodatées, avec pour chacune l'outil appelé, les paramètres envoyés, le résultat reçu, et la clé d'idempotence.
6. J'**annule la dernière action** (l'événement de calendrier). L'objet disparaît de la base, et le journal conserve la trace de la création *et* de l'annulation.

**Le cas d'échec à montrer (1 minute) :** [[à choisir — voir note]]

> 💬 Candidats pour la minute "cas d'échec géré" : (a) je relance le même plan → l'idempotence bloque les
> 💬 doublons et le journal l'explique ; (b) un outil renvoie une erreur → l'exécution s'arrête proprement,
> 💬 les actions déjà faites restent, l'utilisateur voit lesquelles ; (c) l'intention est trop vague
> 💬 → l'agent demande une précision au lieu d'inventer. Choisissez-en UN et répétez-le.

---

## 7. Choix techniques — et ce qu'on a écarté

> 💬 « Aucun de ces choix ne sera jugé en soi. Ce qui sera jugé, c'est votre capacité à le justifier,
> 💬 et à me dire ce que vous avez écarté, et pourquoi. » — remplissez la 3e colonne, c'est elle qui compte.

| Brique | Notre choix | Écarté, et pourquoi |
|---|---|---|
| Langage back | [[Python]] | [[...]] |
| Framework back | [[FastAPI]] | [[Django : trop de conventions à expliquer pour 3 jours]] |
| Modèle | [[...]] | [[...]] |
| SDK d'agent | [[aucun — appel direct au SDK du fournisseur]] | [[LangChain : on ne veut pas défendre à l'oral du code qu'on n'a pas écrit ; notre boucle fait ~40 lignes]] |
| Base de données | [[SQLite]] | [[PostgreSQL : nécessite Docker, donc casse le "on clone et ça démarre"]] |
| Front | [[...]] | [[...]] |
| Hébergement | [[local + tunnel pour la démo]] | [[...]] |

---

## 8. Partage du travail

> 💬 « écrit noir sur blanc » — le jury vérifie. Et rappel : à chaque checkpoint c'est l'AUTRE qui parle.
> 💬 Donc chacun doit pouvoir expliquer la partie de l'autre. Prévoyez la relecture croisée du soir.

| Bloc | Responsable principal | Relecteur (doit savoir l'expliquer) |
|---|---|---|
| Planificateur + prompt système | [[Pierre Rouvellat]] | [[Kevin Rigal]] |
| Exécuteur + idempotence | [[Pierre Rouvellat]] | [[Kevin Rigal]] |
| Outils (lecture) | [[...]] | [[...]] |
| Outils (écriture + faux services) | [[...]] | [[...]] |
| Base de données + journal d'audit | [[...]] | [[...]] |
| Front : saisie + cartes d'approbation | [[...]] | [[...]] |
| Front : journal + annulation | [[...]] | [[...]] |
| README / AGENTS.md / JOURNAL.md | [[les deux, chacun ses entrées]] | — |

**Rituel de relecture croisée :** 20 minutes chaque soir. Chacun explique à l'autre les fichiers
qu'il n'a pas écrits. Si l'un sèche, on relit ensemble avant de rentrer.

---

## 9. Checklist avant de traverser la salle (palier 1)

> 💬 Une checklist incomplète coûte 20 minutes d'attente. Relisez-la à voix haute, à deux.

- [ ] SPEC.md : problème en 5 lignes ✓ / 3 user stories ✓ / hors-scope ≥ 5 items ✓
- [ ] Tableau des outils : nom + signature typée + effet de bord oui/non pour chacun
- [ ] Happy path en 6 étapes numérotées
- [ ] Partage du travail écrit
- [ ] Notre candidat « non argumenté » (+5) est choisi et répété
- [ ] Les deux savent expliquer le schéma entier, seuls
- [ ] `.gitignore` contient `.env` — vérifié avec `git status`
- [ ] `.env.example` existe, `.env` n'est pas suivi par git
- [ ] Toutes les notes `💬` supprimées de ce fichier
