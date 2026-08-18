# Contrat d'interface front ↔ back

> Pour Kevin. Ce document décrit **exactement** ce que le back renvoie.
> Tant que ce contrat ne change pas, le front et le back avancent en parallèle
> sans se bloquer. Si Pierre doit le modifier, il prévient **avant** de pousser.

**Base :** `http://127.0.0.1:8000`
Le back doit tourner (`uvicorn back.main:app --reload`). CORS est ouvert : le front
peut être servi depuis n'importe quel port ou ouvert en `file://`.

---

## `GET /api/sante`

Vérifie que le back tourne. N'appelle pas le modèle : instantané et gratuit.
Pratique pour afficher une pastille verte / rouge.

**Réponse `200`**
```json
{ "statut": "ok", "modele": "claude-opus-5" }
```

---

## `POST /api/message`

Envoie un message au modèle.

**Requête** — en-tête `Content-Type: application/json`
```json
{ "message": "Bonjour, réponds en une phrase." }
```
`message` est obligatoire, entre 1 et 2000 caractères.

**Réponse `200`**
```json
{
  "reponse": "Bonjour ! Comment puis-je vous aider ?",
  "modele": "claude-opus-5",
  "tokens_entree": 34,
  "tokens_sortie": 62,
  "cout_dollars": 0.00172
}
```

**Compter environ 3 à 5 secondes de réponse.** Prévois un état « chargement »,
sinon l'utilisateur croit que rien ne se passe.

---

## Les erreurs

| Code | Quand | Quoi afficher |
|---|---|---|
| `422` | `message` vide ou > 2000 caractères | « Le message ne peut pas être vide. » |
| `502` | Le fournisseur a échoué (clé invalide, réseau, quota) | Le champ `detail` : il contient déjà un message en français, affichable tel quel. |

Les erreurs ont toujours cette forme :
```json
{ "detail": "Cle d'API invalide ou absente. Verifie ANTHROPIC_API_KEY dans le .env." }
```

---

## Exemple complet, copiable tel quel

```js
async function envoyerMessage(texte) {
  const reponse = await fetch("http://127.0.0.1:8000/api/message", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: texte }),
  });

  // fetch ne lève pas d'exception sur un code d'erreur HTTP :
  // il faut vérifier reponse.ok soi-même.
  const donnees = await reponse.json();

  if (!reponse.ok) {
    throw new Error(donnees.detail ?? "Erreur inconnue");
  }

  return donnees;  // { reponse, modele, tokens_entree, tokens_sortie, cout_dollars }
}
```

---

## À afficher à l'écran

Le champ `reponse`, évidemment. Mais **aussi le coût** :

> `0,17 centime — 34 tokens entrée / 62 sortie`

« Coût affiché » est une carte bonus du barème. C'est cinq lignes de JavaScript
pour des points gratuits, ne les laisse pas passer.

---

## Ce qui va changer au palier 3

Pour information, pour que tu conçoives ton front en conséquence :
`/api/message` sera remplacée par `POST /api/plans`, qui renverra une **liste
d'actions proposées**, chacune avec un identifiant, un libellé lisible et ses
paramètres. Ton écran devra afficher une carte par action, avec un bouton
approuver et un bouton refuser. Le format exact arrivera avant que tu en aies besoin.
