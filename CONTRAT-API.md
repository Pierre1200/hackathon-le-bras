# Contrat d'interface front ↔ back

> Pour Kevin. Décrit **exactement** ce que le back renvoie.
> Tant que ce contrat ne change pas, le front et le back avancent en parallèle.
> Si Pierre doit le modifier, il prévient **avant** de pousser.

**Base :** l'API est servie par le même serveur que le front, donc une URL
relative suffit (`fetch("/api/message")`). CORS reste ouvert si tu ouvres le
fichier en `file://` pendant que tu développes.

---

## `GET /api/sante`

Vérifie que le back tourne. N'appelle pas le modèle : instantané et gratuit.

```json
{
  "statut": "ok",
  "modele": "claude-haiku-4-5",
  "fournisseur": "https://api.anthropic.com/v1/"
}
```

---

## `POST /api/message`

**Requête** — en-tête `Content-Type: application/json`

```json
{ "message": "Envoie un message de bienvenue à Alice Dupont." }
```

`message` est obligatoire, entre 1 et 2000 caractères.

**Réponse `200`**

```json
{
  "reponse": "Je propose d'envoyer un message de bienvenue à Alice Dupont…",
  "modele": "claude-haiku-4-5-20251001",
  "tokens_entree": 2712,
  "tokens_sortie": 233,
  "cout_dollars": 0.003877,

  "outils_appeles": [
    {
      "outil": "chercher_personne",
      "arguments": { "nom": "Alice Dupont" },
      "statut": "executee",
      "duree_ms": 1.5,
      "resultat": [
        { "nom": "Alice Dupont", "role": "Lead backend",
          "departement": "Ingenierie", "email": "alice.dupont@lebras.fr" }
      ]
    },
    {
      "outil": "envoyer_message",
      "arguments": { "destinataire": "alice.dupont@lebras.fr",
                     "sujet": "Bienvenue", "corps": "…" },
      "statut": "proposee",
      "duree_ms": 0.0,
      "resultat": { "action_enregistree": "action-1" }
    }
  ],

  "actions_proposees": [
    {
      "id": "action-1",
      "outil": "envoyer_message",
      "arguments": { "destinataire": "alice.dupont@lebras.fr",
                     "sujet": "Bienvenue", "corps": "…" }
    }
  ]
}
```

Compter **1 à 5 secondes** selon le nombre d'outils appelés. L'état de chargement
que tu as déjà fait reste indispensable.

---

## Les trois champs nouveaux

### `statut` dans `outils_appeles` — **le plus important**

Deux valeurs, et la différence est le cœur du projet :

| Valeur | Ce que ça veut dire |
|---|---|
| `"executee"` | L'outil a **vraiment tourné**. C'est une lecture, rien n'a été modifié. |
| `"proposee"` | L'outil a des conséquences réelles, donc il **n'a pas été exécuté**. Il attend l'accord de l'utilisateur. |

**À distinguer visuellement.** Une action proposée n'est pas une action faite —
si les deux se ressemblent à l'écran, on perd ce que le projet promet.
Suggestion : vert pour `executee`, orange ou pointillés pour `proposee`.

### `duree_ms`

La latence de l'outil en millisecondes. À afficher dans le panneau debug : la
carte bonus demande **tokens + coût + latence**. Tu as déjà les deux premiers.

### `actions_proposees`

À la racine de la réponse. La liste des actions en attente de validation, chacune
avec son `id`, son `outil` et ses `arguments`. **Une liste vide est le cas normal** :
la plupart des questions n'appellent aucune action.

Quand elle n'est pas vide, c'est là que tu affiches des **cartes** : ce que l'agent
propose de faire, en clair. Au palier 4 chaque carte aura un bouton **Approuver**
et un bouton **Refuser** — tu peux déjà prévoir la place.

> Rien de ce qui apparaît dans `actions_proposees` n'a été exécuté. Aucun fichier
> n'a été écrit, aucun message envoyé. C'est une proposition sur papier.

---

## Les erreurs

| Code | Quand | Quoi afficher |
|---|---|---|
| `422` | `message` vide ou > 2000 caractères | « Le message ne peut pas être vide. » |
| `502` | Le fournisseur a échoué (clé, réseau, quota) | Le champ `detail`, déjà rédigé en français. |

```json
{ "detail": "Cle d'API refusee. Verifie LLM_API_KEY dans le .env, et qu'elle correspond bien au fournisseur configure." }
```

**Un outil en erreur ne produit pas de code HTTP d'erreur.** La requête réussit
(200) et l'erreur apparaît dans le `resultat` de l'outil concerné :

```json
{ "erreur": "L'outil 'chercher_personne' n'existe pas ou est desactive." }
```

C'est voulu : l'agent doit pouvoir dire qu'il n'a pas pu, plutôt que de faire
tomber l'application. Ton panneau debug colore déjà ce cas, garde-le.

---

## Exemple complet, copiable

```js
async function envoyerMessage(texte) {
  const reponse = await fetch("/api/message", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: texte }),
  });

  // fetch ne lève pas d'exception sur un code d'erreur HTTP :
  // il faut vérifier reponse.ok soi-même.
  const donnees = await reponse.json();

  if (!reponse.ok) {
    throw new Error(
      reponse.status === 422
        ? "Le message ne peut pas être vide."
        : donnees.detail ?? "Erreur inconnue."
    );
  }

  return donnees;
}
```

---

## Ce qui changera au palier 4

Une nouvelle route arrivera : `POST /api/executer`, à qui tu enverras les `id`
des actions approuvées. Elle exécutera **uniquement** celles-là et renverra le
journal de ce qui a été fait. La forme de `/api/message` ne changera pas.
