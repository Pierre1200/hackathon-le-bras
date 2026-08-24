# JOURNAL.md — notre travail avec l'IA

Ce journal note les moments où l'IA nous a fait gagner du temps, et ceux où
elle nous en a fait perdre. Les seconds sont plus instructifs que les premiers.

**Notre méthode.** On a utilisé l'IA sans restriction pour écrire du code, mais
avec deux règles : tout code généré est relu avant d'être commité, et rien n'est
considéré comme vrai tant qu'on ne l'a pas exécuté. Les six entrées ci-dessous
sont toutes nées de la deuxième règle.

---

## Entrée 1 — 18 août — Écarter un framework qu'on n'aurait pas su défendre

**Contexte.** On cherchait comment construire la boucle d'agent. LangChain était
le choix évident, tout le monde l'utilise.

**Ce que l'IA a produit.** Une comparaison honnête, dont un point qu'on n'avait
pas vu : `AgentExecutor` de LangChain **exécute automatiquement** les outils que
le modèle demande. Or notre sujet, LE BRAS, repose exactement sur l'inverse —
proposer sans exécuter. On aurait passé notre temps à désactiver le comportement
par défaut du framework.

**Notre décision.** Écarter LangChain et LangGraph, et écrire la boucle
nous-mêmes. LangGraph a bien une primitive d'interruption adaptée, mais elle nous
aurait obligés à défendre à l'oral un *state graph* et un *checkpointer* qu'on
n'a pas écrits.

**Ce que ça a coûté.** Rien en temps : notre boucle fait une quarantaine de
lignes. Ça nous a même fait gagner du temps au moment de séparer proposition et
exécution.

**Leçon.** Le bon critère n'était pas « quel est le framework le plus utilisé »
mais « qu'est-ce que je saurai expliquer ». Sur un projet où l'oral compte
autant que le code, ce n'est pas la même question.

---

## Entrée 2 — 18 août — « On change une ligne » n'était pas vrai

**Contexte.** On avait mis le nom du modèle dans le `.env` pour pouvoir en
changer sans toucher au code. On voulait comparer Opus 5 et Haiku 4.5.

**Ce que l'IA a produit.** Un adaptateur propre, avec le modèle en variable
d'environnement. Elle nous avait affirmé qu'il suffirait de changer une ligne.

**Ce qui s'est passé.** Erreur 400 dès le passage à Haiku. Le paramètre `effort`,
généré avec le reste du code et jamais remis en question, n'existe pas sur ce
modèle. La promesse était fausse, et on ne l'a découvert qu'en essayant vraiment.

**Notre décision.** Ne pas retirer `effort` (il sert sur Opus) et ne pas mettre
de `if` dans la route. On a ajouté une table de réglages par modèle **dans
l'adaptateur**, parce que c'est son rôle d'absorber les différences entre
fournisseurs. On a aussi amélioré le message d'erreur : le premier disait « erreur
400 » sans dire quel paramètre posait problème.

**Ce que ça a coûté.** Dix minutes.

**Leçon.** Une abstraction ne se décrète pas, elle se teste. « On change une
ligne » n'est vrai que si quelqu'un a écrit le code qui rend ça vrai.

---

## Entrée 3 — 18 août — Un bug invisible tant qu'on ne teste qu'un cas

**Contexte.** On affiche le coût de chaque appel à l'écran. Après le passage à
Haiku, le coût affichait `0.00`.

**Ce que l'IA a produit.** Une table de tarifs indexée par nom de modèle, avec
une recherche par égalité stricte.

**Ce qui s'est passé.** On demande `claude-haiku-4-5`, l'API répond
`claude-haiku-4-5-20251001` — son identifiant daté complet. Aucune
correspondance, donc tarif à zéro. Le bug était invisible avec Opus, dont le nom
revenait identique.

**Notre décision.** Chercher d'abord le nom exact, puis une clé dont le nom
renvoyé est une extension.

**Ce que ça a coûté.** Cinq minutes, mais on aurait pu afficher `0,00 €` au
checkpoint sans jamais s'en apercevoir.

**Leçon.** Tant qu'on n'avait qu'un modèle, on ne testait pas la fonction de
coût : on testait un cas particulier. Ce qu'on croit tester et ce qu'on teste
vraiment sont deux choses différentes.

---

## Entrée 4 — 19 août — Du code généré qui contredisait notre propre spec

**Contexte.** On avait branché deux outils réels, dont un qui envoie un message
en écrivant un fichier. Tout fonctionnait.

**Ce que l'IA a produit.** Une boucle d'appel d'outils correcte et bien écrite,
qui exécutait tous les outils demandés par le modèle — y compris celui à effet
de bord.

**Ce qui s'est passé.** En relisant, on a réalisé que ça contredisait la phrase
la plus importante de notre `SPEC.md` : *« le planificateur n'importe aucun outil
à effet de bord, il ne peut pas exécuter »*. Concrètement, si on demandait
« envoie un message de bienvenue à Alice », l'agent l'envoyait. C'est précisément
le scénario que notre projet promet d'empêcher.

**Notre décision.** Séparer tout de suite au lieu d'attendre le palier suivant :
la boucle exécute les outils de lecture, et se contente d'enregistrer les outils
d'écriture comme actions proposées. Une liste de noms dans `tools.py`, un `if`
dans la boucle.

**Ce que ça a coûté.** Vingt minutes. Et ce travail n'était pas perdu : il était
de toute façon obligatoire au palier suivant.

**Leçon.** L'IA a écrit du code correct par rapport à ce qu'on lui demandait,
mais faux par rapport à ce qu'on avait promis. Elle ne relit pas notre spec à
notre place. C'est la relecture qui a attrapé ça, pas les tests — les tests
passaient.

---

## Entrée 5 — 19 août — Une phrase de prompt valait mieux que du code

**Contexte.** On demandait « envoie un message de bienvenue à Alice Dupont ».
L'agent répondait en demandant l'adresse email d'Alice — alors qu'un de nos
outils pouvait la lui donner.

**Ce que l'IA a produit.** Notre premier réflexe, soufflé par l'outil, était de
regarder la boucle : peut-être fallait-il enchaîner les appels différemment.

**Notre décision.** Ne pas toucher au code. On a ajouté une phrase au prompt
système : *« s'il te manque une information qu'un outil de consultation peut
fournir, va la chercher toi-même au lieu de la demander à l'utilisateur »*. Et
l'agent a enchaîné consultation puis proposition, tout seul.

**Ce que ça a coûté.** Deux minutes, contre probablement une heure si on avait
modifié la boucle.

**Leçon.** Sur un système agentique, le comportement se règle souvent dans le
texte, pas dans le code. Le sujet le disait : *« c'est presque toujours dans la
description des outils que ça se joue »*. On l'a vérifié.

---

## Entrée 6 — 19 août — Mesurer avant de croire qu'on a bien fait

**Contexte.** Notre agent trouvait les bonnes réponses, on le pensait efficace.

**Ce qui s'est passé.** En regardant la trace des appels d'outils, on a vu ceci
pour une seule demande : `lister_equipe` appelé **quatre fois de suite**, puis
l'action proposée. L'agent balayait les départements un par un pour retrouver une
personne, parce que notre seul outil de recherche partait d'un département.

**Notre décision.** Ajouter `chercher_personne`, qui part d'un nom, avec une
description qui dit explicitement au modèle de ne pas confondre les deux. Quatre
appels sont devenus deux.

**Ce que ça a coûté.** Dix minutes, et le coût par question a baissé.

**Leçon.** Le piège du sujet parlait d'outils qui renvoient trop de données.
Notre problème était l'inverse et plus discret : une surface d'outils incomplète
qui forçait le modèle à chercher à tâtons. Sans le panneau de trace, on ne
l'aurait jamais vu — l'agent donnait la bonne réponse.

---

## Entrée 7 — 19 août — Quand le prompt ne suffit pas, on vérifie

**Contexte.** L'agent devait proposer un plan d'accueil complet : cinq actions,
une par étape de la procédure de l'entreprise.

**Ce qui s'est passé.** Après avoir consulté la procédure, il rédigeait les
étapes **en texte** au lieu d'appeler les outils. Le paragraphe était juste,
mais `actions_proposees` restait vide : aucune carte à l'écran, rien à
approuver. Et de façon intermittente — ça marchait **une fois sur quatre**.

**Ce qu'on a essayé, dans l'ordre.** Reformuler le prompt trois fois. Passer de
4 à 8 tours d'outils, au cas où il manquerait de place. Tester un modèle plus
gros — Claude Sonnet 5 a échoué exactement pareil. Corriger deux descriptions
d'outils qui contredisaient le prompt : amélioré, mais toujours pas fiable.

**Notre décision.** Arrêter de demander poliment. La boucle **vérifie sa propre
sortie** : si l'agent a consulté la procédure d'accueil et n'a proposé aucune
action, on relance **une fois** avec une consigne explicite. La condition est
étroite — une simple question de consultation ne déclenche rien — et un drapeau
garantit qu'on ne relance qu'une seule fois.

**Ce que ça a coûté.** Environ une heure et cinquante centimes d'appels. Trois
fausses pistes avant la bonne.

**Leçon.** On a cherché dans le prompt parce que c'est là qu'on avait trouvé la
solution les fois d'avant — l'entrée 5 nous avait appris qu'une phrase valait
mieux que du code, et on a sur-appliqué la leçon. Un modèle qu'on doit supplier
de respecter une consigne, on ne le supplie pas : on vérifie sa sortie et on
relance. C'est du code, c'est déterministe, et ça se teste.

**Ce que l'éval a servi à voir.** Deux campagnes successives sur exactement le
même code : 94 % puis 100 %. Sans le score chiffré, on aurait conclu « ça
marche » sur la campagne qui passait. C'est précisément ce que le sujet appelle
« ne pas savoir si on régresse ».

---

## Entrée 8 — 19 août — Le même code, deux machines, deux résultats

**Contexte.** Kevin n'avait pas de clé d'API. Grâce au choix du jour 1 — un
client universel plutôt que le SDK d'un fournisseur — il a pu brancher un
modèle local via Ollama et travailler sans nous attendre.

**Ce qui s'est passé.** Chez lui, la moitié des actions échouaient alors que
tout marchait chez l'autre. Son modèle proposait des noms de paramètres
inventés : `contenu_de_la_messsage` — avec une faute de frappe — là où l'outil
attend `corps`. L'application affichait alors une erreur Python brute :
« missing 1 required positional argument ».

**Notre décision.** Ne pas revenir en arrière sur le fournisseur
interchangeable : c'est précisément ce qui lui avait permis de travailler. On a
ajouté une **validation des arguments contre le schéma de l'outil**, avant tout
appel. Un argument manquant ou inventé produit maintenant un message qui dit ce
qui manque et ce qui est en trop — lisible par le modèle, qui peut se corriger,
et par l'utilisateur, qui comprend.

**Ce que ça a coûté.** Vingt minutes, et trois tests de plus.

**Leçon.** Deux choses. D'abord, notre message d'erreur était exact et inutile :
il parlait de Python, pas du problème. Ensuite, la portabilité entre
fournisseurs a un prix qu'on ne voit qu'en le payant — on avait écrit dans
AGENTS.md que le typage strict nous manquerait, c'est resté théorique jusqu'au
jour où un vrai modèle a proposé de vrais mauvais arguments.

---

## Ce qu'on retient, au-delà des huit entrées

**L'IA écrit vite du code qui a l'air juste.** Nos huit problèmes ont tous passé
la relecture superficielle. Sept sur huit ont été trouvés en exécutant, en
mesurant ou en relisant notre propre spec — pas en lisant le code une fois.

**Les bugs les plus coûteux étaient invisibles.** Le coût affiché à zéro et les
quatre appels d'outils ne faisaient rien planter. Une application qui fonctionne
n'est pas une application qui fonctionne bien.

**On a gardé la décision.** À chaque fois, l'outil proposait une solution
plausible ; à chaque fois, le bon choix dépendait d'une contrainte qu'il ne
pouvait pas connaître — notre spec, notre barème, ce qu'on saurait défendre.

**Et une leçon qu'on a apprise deux fois.** L'entrée 5 nous a montré qu'une
phrase de prompt valait mieux qu'une heure de code. L'entrée 7 nous a montré
que l'inverse est vrai aussi. La vraie compétence n'est pas de savoir lequel
des deux marche — c'est de savoir quand on s'entête dans le mauvais.
