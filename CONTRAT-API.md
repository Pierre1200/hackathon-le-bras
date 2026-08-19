# Contrat d'interface front ↔ back

> Pour Kevin. Décrit **exactement** ce que le back renvoie.
> Si Pierre doit le modifier, il prévient **avant** de pousser.

**Base :** le back sert le front, donc les URL relatives suffisent (`fetch("/api/message")`).

---

## Le parcours en 6 étapes, et la route de chacune

| Étape | Ce que fait l'utilisateur | Route |
|---|---|---|
| 1 | Tape son intention | `POST /api/message` |
| 2 | Voit le plan d'actions | *(dans la réponse ci-dessus)* |
| 3 | Approuve / refuse chaque carte | *(côté front, rien à appeler)* |
| 4 | Clique sur **Exécuter** | `POST /api/plans/{id}/executer` |
| 5 | Consulte le journal | `GET /api/journal` |
| 6 | Annule la dernière action | `POST /api/actions/{id}/annuler` |
| — | Recharge la page | `GET /api/plans/dernier` |

---

## Le cycle de vie d'une action — **à comprendre avant de coder**

```
proposee ──approuvée par l'utilisateur──▶ approuvee ──▶ executee ──▶ annulee
    │                                                       │
    └──non approuvée──▶ refusee              echouee ◀──────┘
                                          (l'outil a planté)
```

| `statut` | Ce que ça veut dire | À l'écran |
|---|---|---|
| `proposee` | Rien n'a été fait. En attente de décision. | Carte avec **Approuver** / **Refuser** |
| `approuvee` | État transitoire, tu ne le verras quasiment jamais | — |
| `refusee` | L'utilisateur a dit non. **Rien n'a été fait.** | Grisé, barré |
| `executee` | L'action a réellement eu lieu | Vert, avec un bouton **Annuler** |
| `echouee` | L'outil a été appelé mais a échoué. Voir `resultat.erreur`. | Rouge, message d'erreur |
| `annulee` | L'effet a été défait | Grisé, mention « annulée » |

---

## `POST /api/message` — étapes 1 et 2

**Requête**
```json
{ "message": "Prépare l'arrivée de Sarah Martin, développeuse back-end, le 24 août." }
```

**Réponse `200`** — mêmes champs qu'avant, **plus `plan_id`** :

```json
{
  "plan_id": 1,
  "reponse": "Je propose 3 actions…",
  "modele": "claude-haiku-4-5-20251001",
  "tokens_entree": 2712,
  "tokens_sortie": 233,
  "cout_dollars": 0.003877,
  "outils_appeles": [ … ],
  "actions_proposees": [ … ]
}
```

> ⚠️ **Ce qui change pour toi :** les actions ont maintenant un **`id` entier**
> (identifiant en base), plus `"action-1"`. C'est cet `id` que tu renverras pour
> approuver. Et elles portent un `statut`, un `cle_idempotence`, un `duree_ms`.

Forme complète d'une action :

```json
{
  "id": 1,
  "plan_id": 1,
  "outil": "creer_fiche_employe",
  "arguments": {
    "nom": "Sarah Martin",
    "role": "Developpeuse back-end",
    "departement": "Ingenierie",
    "email": "sarah.martin@lebras.fr",
    "date_arrivee": "2026-08-24"
  },
  "cle_idempotence": "f08eee1f2458…",
  "statut": "proposee",
  "resultat": null,
  "cree_le": "2026-08-19T09:53:40+00:00",
  "execute_le": null,
  "duree_ms": null
}
```

`resultat`, `execute_le` et `duree_ms` valent `null` tant que l'action n'a pas été exécutée.

---

## `POST /api/plans/{plan_id}/executer` — étape 4

**Requête** — tu envoies **uniquement les identifiants approuvés** :

```json
{ "approuvees": [1, 2] }
```

> **Le défaut, c'est non.** Tout ce qui n'est pas dans cette liste passe en
> `refusee`. Tu n'as pas à envoyer les refus.

**Réponse `200`** — le **plan entier remis à jour**. Tu n'as qu'à redessiner ton écran avec, sans rien recalculer.

**Erreurs**

| Code | Quand |
|---|---|
| `404` | Le plan n'existe pas |
| `400` | Un `id` approuvé n'appartient pas à ce plan — la requête entière est refusée |

**Rejouable sans risque :** rappeler cette route ne refait rien. Les actions ne sont plus `proposee`, donc elles sont ignorées. Un double clic sur **Exécuter** est sans conséquence.

---

## `POST /api/actions/{action_id}/annuler` — étape 6

Pas de corps de requête.

**Réponse `200`** — le plan entier remis à jour, comme pour l'exécution.

**Erreurs — toutes avec un message affichable tel quel dans `detail`**

| Code | Quand | Exemple de `detail` |
|---|---|---|
| `404` | L'action n'existe pas | « Aucune action numero 99. » |
| `400` | Statut ≠ `executee` | « L'action 3 est 'refusee' : seule une action executee peut etre annulee. » |
| `400` | C'était un doublon | « L'action 4 n'a rien execute : c'etait un doublon de l'action 1. Annulez l'action 1 pour defaire reellement l'effet. » |
| `502` | L'annulation a échoué | Le message de l'outil |

> **N'affiche « annulé » que si tu as reçu un `200`.** En cas de `502`, l'action
> reste `executee` et son effet existe toujours. Afficher « annulé » sur un effet
> encore présent serait un mensonge — c'est exactement ce que le palier 5 sanctionne.

**Ne montre le bouton Annuler que sur les actions `executee`.** Les trois autres cas te renverront un 400.

---

## `GET /api/plans/dernier` — le rechargement de page

**C'est la route la plus importante du palier 4.** Le jury va recharger la page en plein milieu.

Au chargement, appelle-la : elle renvoie le dernier plan avec ses actions et leurs statuts actuels. Tu retrouves exactement l'écran quitté.

**Réponse `200`** : un plan complet, ou **`null`** s'il n'y a encore aucun plan — ce n'est pas une erreur, c'est une application ouverte pour la première fois.

```json
{
  "id": 1,
  "intention": "Prépare l'arrivée de Sarah Martin…",
  "reponse": "Je propose 3 actions.",
  "modele": "claude-haiku-4-5",
  "tokens_entree": 2712, "tokens_sortie": 233, "cout_dollars": 0.003877,
  "outils_appeles": [ … ],
  "cree_le": "2026-08-19T09:53:40+00:00",
  "actions": [ … ]
}
```

`GET /api/plans/{id}` existe aussi, même forme, `404` si l'id est inconnu.

---

## `GET /api/journal` — étape 5

Paramètre optionnel `?limite=50` (défaut 50).

```json
{
  "entrees": [
    {
      "id": 5,
      "plan_id": 2,
      "outil": "creer_ticket",
      "arguments": { … },
      "statut": "executee",
      "resultat": {
        "deja_executee": true,
        "action_origine": 2,
        "resultat": { "id": 1, "titre": "Preparer le poste de Sarah" }
      },
      "cree_le": "2026-08-19T09:54:03+00:00",
      "execute_le": "2026-08-19T09:54:03+00:00",
      "duree_ms": 0.0,
      "intention": "Prépare encore l'arrivée de Sarah Martin."
    }
  ]
}
```

Du plus récent au plus ancien. Chaque entrée porte **`intention`** en plus : l'intention qui a provoqué l'action. C'est ce qui permet de répondre à « pourquoi l'agent a fait ça ? » — l'exigence d'observabilité du palier 5.

**Le journal contient aussi les actions `refusee` et `annulee`.** C'est voulu : savoir ce qui n'a pas été fait fait partie de l'audit. Ne les filtre pas.

### Le cas `deja_executee`

Quand `resultat.deja_executee` vaut `true`, l'action **n'a rien exécuté** : c'était un doublon, l'idempotence l'a arrêtée. `action_origine` donne le numéro de celle qui a réellement agi.

Affiche-le explicitement — par exemple « déjà exécutée (doublon de l'action 2) ». C'est une des meilleures choses à montrer au jury.

---

## Exemple complet, copiable

```js
// 1. Créer un plan
async function envoyerIntention(texte) {
  const r = await fetch("/api/message", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: texte }),
  });
  const d = await r.json();
  if (!r.ok) throw new Error(d.detail ?? "Erreur inconnue.");
  return d;
}

// 2. Exécuter les actions cochées
async function executer(planId, idsApprouvees) {
  const r = await fetch(`/api/plans/${planId}/executer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approuvees: idsApprouvees }),
  });
  const d = await r.json();
  if (!r.ok) throw new Error(d.detail ?? "Erreur inconnue.");
  return d;   // le plan entier remis à jour
}

// 3. Annuler
async function annuler(actionId) {
  const r = await fetch(`/api/actions/${actionId}/annuler`, { method: "POST" });
  const d = await r.json();
  if (!r.ok) throw new Error(d.detail ?? "Erreur inconnue.");
  return d;   // le plan entier remis à jour
}

// 4. Au chargement de la page
async function restaurer() {
  const r = await fetch("/api/plans/dernier");
  return await r.json();   // un plan, ou null
}
```

---

## Les erreurs, en général

| Code | Quand | Quoi afficher |
|---|---|---|
| `422` | `message` vide ou > 2000 caractères | « Le message ne peut pas être vide. » |
| `400` | Requête refusée pour une raison métier | Le champ `detail`, rédigé en français |
| `404` | Plan ou action inconnu | Le champ `detail` |
| `502` | Le fournisseur de modèle ou une annulation a échoué | Le champ `detail` |

**Un outil qui échoue ne produit pas de code HTTP d'erreur.** La requête réussit et l'échec apparaît dans le `statut` de l'action (`echouee`) et dans `resultat.erreur`.
