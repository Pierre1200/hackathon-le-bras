# AGENTS.md

Documentation de la partie agentique : prompts système, outils, boucle.

---

## 1. Prompt système du planificateur

> À coller ici tel quel, sans le reformuler. Le jury compare ce fichier au code.

```
[[prompt système]]
```

**Pourquoi ce prompt est écrit comme ça :** [[2-3 lignes]]

---

## 2. Outils et signatures

| Outil | Signature | Effet de bord | Clé d'idempotence |
|---|---|---|---|
| [[...]] | [[...]] | [[oui/non]] | [[...]] |

> Le tableau complet est dans SPEC.md §5 — garder les deux synchronisés.

---

## 3. Schéma de la boucle

```
intention (texte)
      │
      ▼
 PLANIFICATEUR ──► le modèle appelle les outils de LECTURE seulement
      │            (il se documente avant de proposer)
      ▼
 plan = liste d'actions proposées   ◄── AUCUN effet de bord jusqu'ici
      │
      ▼
 ⏸  ATTENTE HUMAINE : l'utilisateur approuve / refuse action par action
      │
      ▼
 EXÉCUTEUR ──► pour chaque action APPROUVÉE uniquement :
      │          1. calculer la clé d'idempotence
      │          2. si déjà exécutée → renvoyer l'ancien résultat, ne rien refaire
      │          3. sinon → appeler l'outil, écrire dans le journal d'audit
      ▼
 journal d'audit consultable + annulation de la dernière action
```

---

## 4. Garde-fous

- [[Le planificateur n'a pas accès aux outils d'écriture — contrainte d'import, pas de discipline]]
- [[Idempotence sur toute action à effet de bord]]
- [[...]]
