# Brief front — palier 4 et 5

Tout le back est prêt et testé. Il ne manque que l'écran.
Formats exacts dans [CONTRAT-API.md](CONTRAT-API.md) — ce fichier-ci dit juste
**quoi faire, dans quel ordre**.

Tu as déjà : la saisie, l'affichage de la réponse, le coût, le panneau debug,
et les cartes de propositions. C'est la suite.

---

## 1. Approuver / Refuser + Exécuter ⭐ **le plus important**

Le palier 4 est le seul obligatoire des six, et c'est ce qui lui manque.

Sur chaque carte de `actions_proposees` dont le `statut` vaut `proposee` :
deux boutons, ou une case à cocher. Puis **un bouton Exécuter** global.

```js
async function executer(planId, idsApprouvees) {
  const r = await fetch(`/api/plans/${planId}/executer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approuvees: idsApprouvees }),
  });
  const d = await r.json();
  if (!r.ok) throw new Error(d.detail);
  return d;   // le plan entier remis à jour : tu redessines avec, c'est tout
}
```

**Tu n'envoies que les approuvées.** Tout ce qui n'est pas dans la liste passe
en `refusee` automatiquement — tu n'as pas à gérer les refus.

Le `plan_id` est dans la réponse de `/api/message`.

Après exécution, redessine à partir du plan renvoyé. Les statuts deviennent
`executee`, `refusee` ou `echouee`.

---

## 2. Restauration au chargement ⭐

> *« Je recharge la page en plein milieu. On verra bien. »* — le checkpoint

Au chargement de la page :

```js
const plan = await (await fetch("/api/plans/dernier")).json();
if (plan) redessiner(plan);   // null = première ouverture, pas une erreur
```

Le plan revient avec les statuts à jour. L'utilisateur retrouve exactement son
écran.

---

## 3. Bouton Annuler

Sur les actions dont le `statut` vaut **`executee` uniquement**. Les autres
cas renvoient un 400.

```js
const r = await fetch(`/api/actions/${actionId}/annuler`, { method: "POST" });
const d = await r.json();
if (!r.ok) throw new Error(d.detail);   // message déjà en français, affichable tel quel
```

> ⚠️ **N'affiche « annulé » que si tu as reçu un 200.** En cas de 502, l'action
> reste `executee` et son effet existe toujours. Afficher « annulé » sur un
> effet encore présent serait un mensonge — c'est précisément ce que le palier 5
> sanctionne.

---

## 4. Écran journal ⭐ *(palier 5 — observabilité)*

> *« Je dois pouvoir répondre à "pourquoi l'agent a fait ça ?" en moins de
> 30 secondes, en regardant votre app, pas votre code. »*

```js
const { entrees } = await (await fetch("/api/journal")).json();
```

Un onglet ou un panneau dépliable. Chaque entrée contient :

| Champ | À afficher |
|---|---|
| `intention` | **la demande qui a provoqué l'action** — c'est la réponse à « pourquoi » |
| `outil` + `arguments` | ce qui a été fait |
| `statut` | executee / refusee / annulee / echouee |
| `execute_le` | horodatage |
| `duree_ms` | latence |
| `resultat` | ce que ça a donné |

**Ne filtre pas les `refusee` ni les `annulee`.** Savoir ce qui n'a **pas** été
fait fait partie de l'audit.

Cas particulier : si `resultat.deja_executee` vaut `true`, l'action n'a rien
exécuté — c'était un doublon arrêté par l'idempotence. Affiche-le
explicitement, genre « déjà exécutée (doublon de l'action 2) ». C'est une des
meilleures choses à montrer au jury.

---

## 5. Erreurs visibles *(palier 5)*

> *« Un spinner infini est un bug, pas une gestion d'erreur. »*

Toutes les erreurs du back arrivent dans `detail`, **déjà rédigées en français**,
affichables telles quelles.

```js
if (!r.ok) afficherErreur(d.detail ?? "Erreur inconnue.");
```

| Code | Quand |
|---|---|
| `422` | Message vide, que des espaces, ou > 2000 caractères |
| `400` | Refus métier (annuler une action non exécutée, etc.) |
| `404` | Plan ou action inconnu |
| `502` | Le fournisseur de modèle ne répond pas |

Et **remets toujours le bouton en état** dans un `finally`, même en cas
d'erreur. Le jury va cliquer dix fois sur Envoyer et couper le réseau.

---

## Les statuts, en un coup d'œil

```
proposee ──approuvée──▶ executee ──▶ annulee
    │                       │
    └──non approuvée──▶ refusee    echouee
```

| `statut` | À l'écran |
|---|---|
| `proposee` | Carte avec **Approuver** / **Refuser** |
| `refusee` | Grisé, barré — **rien n'a été fait** |
| `executee` | Vert, avec un bouton **Annuler** |
| `echouee` | Rouge, avec `resultat.erreur` |
| `annulee` | Grisé, mention « annulée » |

---

## Ordre conseillé

1. **Approuver / Refuser + Exécuter** — sans ça, pas de palier 4
2. **Restauration au chargement** — le jury recharge la page, c'est annoncé
3. **Erreurs visibles** — rapide, et c'est du palier 5
4. **Écran journal** — l'observabilité du palier 5
5. **Bouton Annuler** — l'étape 6 du parcours

---

## Pour tester sans clé d'API

Tu peux fabriquer un plan directement en base et travailler ton écran dessus,
sans dépenser un centime :

```bash
.venv/bin/python -c "
from back import persistance as p
p.enregistrer_plan(
    intention=\"Prepare l'arrivee de Sarah Martin.\",
    reponse='Je propose 3 actions.', modele='test',
    tokens_entree=0, tokens_sortie=0, cout_dollars=0.0, trace=[],
    actions_proposees=[
        {'outil':'creer_fiche_employe','arguments':{'nom':'Sarah Martin','role':'Dev','departement':'Ingenierie','email':'sarah@lebras.fr','date_arrivee':'2026-08-24'}},
        {'outil':'creer_ticket','arguments':{'titre':'Preparer le poste','description':'PC, VPN','assigne_a':'david.petit@lebras.fr'}},
        {'outil':'envoyer_message','arguments':{'destinataire':'sarah@lebras.fr','sujet':'Bienvenue','corps':'A lundi !'}},
    ],
)
print('plan cree')
"
```

Puis `GET /api/plans/dernier` te le renvoie. Approuver, exécuter et annuler
fonctionnent tous **sans appel au modèle** — seule la création d'un plan en
coûte un.

---

## Vérifier que tu n'as rien cassé

```bash
make test
```

26 tests, moins d'une seconde, gratuit.
