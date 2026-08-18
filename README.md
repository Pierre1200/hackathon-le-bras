# LE BRAS

> Un agent qui ne se contente pas de parler : il agit. Mais rien ne part sans vous.

Hackathon Full Stack Agentique IA — Holberton School. Sujet 03.
**Binôme :** [[Prénom 1]] & [[Prénom 2]]

---

## Quickstart (< 5 min)

> ⚠️ À remplir au fur et à mesure. Test de validation : on efface tout, on `git clone`,
> et on suit ces commandes sans rien deviner. Si ça démarre, la section est bonne.

```bash
git clone [[url]] && cd lebras
cp .env.example .env      # puis renseigner LLM_API_KEY
[[commande d'installation]]
[[commande de lancement]]
```

Puis ouvrir http://localhost:8000

---

## Ce que fait le projet

[[3 lignes maximum]]

## Architecture

[[schéma + 5 lignes. Voir SPEC.md pour le détail.]]

Le point important : le **planificateur** et l'**exécuteur** sont deux modules séparés.
Le planificateur n'importe aucun outil à effet de bord — il ne *peut pas* exécuter.
Aucune action ne part sans approbation humaine explicite.

## Choix techniques

[[tableau : notre choix / ce qu'on a écarté et pourquoi]]

## Limites connues

> Une limite assumée et écrite vaut mieux qu'une limite découverte par le jury.

- Les services externes sont **simulés** : la messagerie écrit des fichiers dans `outbox/`,
  le reste vit dans une base SQLite locale. C'est un choix documenté, pas un oubli.
- [[...]]
