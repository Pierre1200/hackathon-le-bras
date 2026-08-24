# Démo — 5 minutes

4 minutes de parcours nominal, 1 minute de cas d'échec géré.

**Qui parle :** Kevin ouvre et mène le parcours nominal. Pierre prend le relais
sur le cas d'échec et les questions techniques. **Les deux parlent** — le barème
le vérifie.

**Qui tape :** celui qui ne parle pas. On ne parle pas en tapant.

---

## Avant de commencer — 2 minutes, hors chrono

```bash
make reset
```

```bash
make demarrer
```

Puis dans le navigateur : **`Cmd + Shift + R`** une fois.

- [ ] Un **second terminal** ouvert, avec la commande du cas d'échec déjà tapée
      (voir 4:00), prête à lancer d'un coup d'Entrée
- [ ] Un **troisième terminal** dans le dossier du projet, pour `ls outbox/`
- [ ] Le nom qu'on va utiliser **n'est pas dans l'annuaire** — vérifier avec
      `make etat` (l'annuaire contient Alice Dupont, Bruno Martin, Chloe Bernard,
      David Petit, Emma Roux)
- [ ] La page est en haut, le champ est vide

---

## 0:00 → 0:25 · L'accroche

> **Kevin.** « LE BRAS, c'est un agent qui transforme une intention écrite en
> français en un plan d'actions réelles. Il montre le plan, et **il n'exécute
> que ce qu'un humain a approuvé**. Je vous montre le parcours complet. »

*(ne pas détailler l'architecture ici — on la garde pour les questions)*

---

## 0:25 → 1:30 · L'intention devient un plan

**Taper :**

```
Prépare l'arrivée de Nadia Belkacem, développeuse full stack, le 15 septembre.
```

> **Kevin, pendant que ça tourne.** « Là il consulte l'annuaire pour vérifier
> qu'elle n'y est pas déjà, puis il va chercher la procédure d'accueil de
> l'entreprise. Il ne devine pas ce qu'il faut faire : il lit la procédure. »

⏱️ **Compter 15 secondes.** Huit appels d'outils s'enchaînent. C'est long à
l'écran : il faut parler pendant, pas attendre en silence. Le paragraphe
ci-dessus est calibré pour couvrir l'attente.

**Quand le plan s'affiche :**

> « Cinq actions proposées, une par étape de la procédure. Il a déduit son
> email de la convention de l'entreprise, son département depuis son poste, et
> converti la date. **Rien n'a été fait** — ce sont des propositions. »

---

## 1:30 → 2:15 · La trace

**Montrer le panneau « Outils appelés ».**

> **Kevin.** « Voilà exactement comment il y est arrivé. Chaque ligne : l'outil,
> ses arguments, sa durée en millisecondes, et son statut.
>
> Regardez la différence de statut. Celles-ci sont **exécutées** — ce sont des
> consultations, rien n'a été modifié. Celles-là sont **proposées** — elles ont
> des conséquences réelles, donc elles n'ont pas tourné. »

**Et le coût, en bas de la réponse :**

> « Tokens en entrée, en sortie, et le coût réel de cette requête. On sait ce
> que coûte notre produit. »

---

## 2:15 → 3:10 · On approuve, on refuse, on exécute

**Cocher 4 actions sur 5. Laisser le message de bienvenue décoché.**

> **Pierre.** « J'approuve quatre actions. Je refuse le message de bienvenue —
> je veux l'écrire moi-même. »

**Cliquer sur Exécuter.**

> « Les quatre approuvées passent en **Exécutée**. La refusée passe en
> **Refusée** — et sa fonction n'a jamais été appelée. »

**Dans le troisième terminal :**

```bash
ls outbox/
```

> « Vide. L'agent avait proposé d'envoyer un message, on a refusé, **rien n'est
> parti**. C'est toute la promesse du projet, et elle est vérifiable en trois
> secondes. »

---

## 3:10 → 3:45 · Le journal d'audit

**Ouvrir le journal.**

> **Pierre.** « Tout ce qui a été décidé et fait. Cinq entrées — le compteur le
> dit, rien n'est masqué.
>
> Et la refusée y est aussi. **Savoir ce qui n'a pas été fait fait partie de
> l'audit.**
>
> Chaque entrée porte l'intention qui l'a provoquée. C'est la réponse à
> "pourquoi l'agent a fait ça", en regardant l'application, pas le code. »

---

## 3:45 → 4:00 · L'annulation

**Cliquer sur Annuler sur la fiche employée.**

> **Pierre.** « L'annulation défait vraiment l'effet : la fiche disparaît de
> l'annuaire. Le journal garde la trace de la création **et** de l'annulation. »

*(si le temps manque, cette section peut sauter — la garder pour les questions)*

---

## 4:00 → 5:00 · Le cas d'échec géré

> **Kevin.** « Maintenant ce qui se passe quand ça casse. Je coupe l'accès au
> fournisseur de modèle. »

**Second terminal — arrêter le serveur (`Ctrl+C`) et relancer :**

```bash
LLM_API_KEY=fausse-cle .venv/bin/uvicorn back.main:app
```

**Retourner dans le navigateur, taper n'importe quoi :**

```
Qui travaille en ingénierie ?
```

> « Un message clair, en français, qui dit quoi corriger. **Pas un spinner
> infini, pas une trace Python, et surtout aucune réponse inventée.**
>
> C'est un 502 et pas un 500 : 500 dirait que notre code a planté, 502 dit
> qu'un service dont on dépend a échoué. La distinction compte quand on
> diagnostique à trois heures du matin. »

**Conclure :**

> « Sur un système agentique, une application qui échoue bruyamment vaut
> infiniment mieux qu'une application qui invente une réponse. C'est la seule
> chose qu'on ne s'autorise pas. »

---

## Après la démo, si on vous laisse la main

```bash
make test
```
29 tests, moins d'une seconde, aucun appel au modèle.

```bash
make eval
```
7 cas rejoués contre le vrai modèle, score chiffré, coût affiché. 30 secondes.

---

## Si ça rate en direct

| Ce qui arrive | Ce qu'on dit |
|---|---|
| C'est lent | « Il enchaîne quatre outils, c'est normal » |
| Un 502 non prévu | « Le fournisseur ne répond pas. Regardez : l'app ne tombe pas, elle dit quoi corriger » — c'est le cas d'échec, en avance |
| Le mauvais outil est choisi | « Regardons la description de l'outil, c'est presque toujours là que ça se joue » *(et on ouvre `tools.py`)* |
| Moins de 5 actions proposées | « Le modèle n'est pas déterministe. Notre éval mesure ça : on est à 100 % sur sept cas, et le tableau des campagnes est dans `eval/cases.md` » |
| Un blanc | « Je réfléchis deux secondes » |

**Ne jamais inventer.** Et jamais « c'est l'IA qui l'a écrit » — le sujet dit
explicitement que ce n'est pas une réponse.

---

## Remise en état après la démo

```bash
make reset
```

Et relancer le serveur normalement, sans la fausse clé.
