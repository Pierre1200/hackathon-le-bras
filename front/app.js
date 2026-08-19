// Base de l'API back (Pierre). Le back sert désormais ce front lui-même,
// donc la page et l'API partagent la même origine : une URL relative ("")
// suffit, et elle reste juste une fois l'application déployée — une adresse
// en dur pointerait vers le localhost du visiteur.
// Si le fichier est ouvert directement depuis le disque (file://), il n'y a
// pas d'origine HTTP à laquelle se rattacher : on vise alors le back local.
const API_BASE = window.location.protocol.startsWith("http") ? "" : "http://127.0.0.1:8000";

const statusEl = document.getElementById("status");
const statusText = document.getElementById("status-text");
const form = document.getElementById("message-form");
const messageInput = document.getElementById("message");
const submitBtn = document.getElementById("submit-btn");
const erreurEl = document.getElementById("erreur");
const result = document.getElementById("result");
const trace = document.getElementById("trace");
const traceListe = document.getElementById("trace-liste");
const actionsPanel = document.getElementById("actions");
const actionsListe = document.getElementById("actions-liste");
const executerBtn = document.getElementById("executer-btn");
const journalToggle = document.getElementById("journal-toggle");
const journalPanel = document.getElementById("journal-panel");
const journalListe = document.getElementById("journal-liste");

// Le plan actuellement affiché à l'écran (voir CONTRAT-API.md). null tant
// qu'aucun message n'a été envoyé et qu'aucun plan n'a été restauré au
// chargement. C'est sur son `id` qu'on exécute et qu'on relit après annulation.
let planCourant = null;

const LABEL_STATUT = {
  proposee: "Proposée",
  approuvee: "En cours",
  refusee: "Refusée",
  executee: "Exécutée",
  echouee: "Échouée",
  annulee: "Annulée",
};

async function verifierSante() {
  try {
    const reponse = await fetch(`${API_BASE}/api/sante`);
    if (!reponse.ok) throw new Error();
    const donnees = await reponse.json();
    statusEl.className = "status status--ok fade-in";
    statusText.textContent = `Back en ligne — ${donnees.modele}`;
  } catch {
    statusEl.className = "status status--down fade-in";
    statusText.textContent = "Back injoignable";
  }
}

// dollars -> "0,17 centime" (voir CONTRAT-API.md, carte bonus "coût affiché")
function formaterCout(dollars) {
  const centimes = dollars * 100;
  if (centimes < 0.01) return "< 0,01 centime";
  return `${centimes.toFixed(2).replace(".", ",")} centime`;
}

function afficherErreur(message) {
  erreurEl.textContent = message;
  erreurEl.hidden = false;
}

function masquerErreur() {
  erreurEl.hidden = true;
  erreurEl.textContent = "";
}

// ---------------------------------------------------------------------------
// Panneau debug : la séquence des outils réellement appelés pour produire
// la réponse. Doit être montrable en 30 secondes, sans ajouter de print.
// ---------------------------------------------------------------------------
function afficherTrace(outils) {
  traceListe.replaceChildren();

  if (!outils || outils.length === 0) {
    trace.hidden = true;
    return;
  }

  for (const appel of outils) {
    const item = document.createElement("li");
    item.className = "trace__item";

    const entete = document.createElement("div");
    entete.className = "trace__entete";

    const nom = document.createElement("code");
    nom.className = "trace__outil";
    nom.textContent = appel.outil;
    entete.append(nom);

    if (appel.statut) {
      const badge = document.createElement("span");
      const executee = appel.statut === "executee";
      badge.className = `trace__badge ${executee ? "trace__badge--executee" : "trace__badge--proposee"}`;
      badge.textContent = executee ? "Exécutée" : "Proposée";
      entete.append(badge);
    }

    if (appel.statut === "executee" && typeof appel.duree_ms === "number") {
      const duree = document.createElement("span");
      duree.className = "trace__duree";
      duree.textContent = `${appel.duree_ms} ms`;
      entete.append(duree);
    }

    const args = document.createElement("pre");
    args.className = "trace__args";
    args.textContent = JSON.stringify(appel.arguments);

    const resultat = document.createElement("pre");
    const enErreur = appel.resultat && typeof appel.resultat === "object" && "erreur" in appel.resultat;
    resultat.className = enErreur ? "trace__resultat trace__resultat--erreur" : "trace__resultat";
    resultat.textContent = JSON.stringify(appel.resultat);

    item.append(entete, args, resultat);
    traceListe.append(item);
  }

  trace.hidden = false;
}

// ---------------------------------------------------------------------------
// Panneau "actions" : une carte par action du plan, quel que soit son statut.
// C'est ici que se joue le palier 4 : approuver/refuser puis exécuter, et
// annuler une action déjà exécutée.
// ---------------------------------------------------------------------------

function carteAction(action) {
  const li = document.createElement("li");
  li.className = `actions__item actions__item--${action.statut}`;

  const entete = document.createElement("div");
  entete.className = "actions__entete";

  // Seule une action encore "proposee" peut être (dés)approuvée. Décochée
  // par défaut : le défaut, c'est non, rien ne part sans un geste explicite.
  if (action.statut === "proposee") {
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "actions__checkbox";
    checkbox.id = `action-${action.id}`;
    checkbox.dataset.actionId = String(action.id);
    checkbox.addEventListener("change", mettreAJourBoutonExecuter);

    const label = document.createElement("label");
    label.htmlFor = checkbox.id;
    label.className = "actions__outil";
    label.textContent = action.outil;

    entete.append(checkbox, label);
  } else {
    const outil = document.createElement("code");
    outil.className = "actions__outil";
    outil.textContent = action.outil;
    entete.append(outil);
  }

  const badge = document.createElement("span");
  badge.className = `actions__badge actions__badge--${action.statut}`;
  badge.textContent = LABEL_STATUT[action.statut] ?? action.statut;
  entete.append(badge);

  li.append(entete);

  const args = document.createElement("pre");
  args.className = "actions__args";
  args.textContent = JSON.stringify(action.arguments, null, 2);
  li.append(args);

  // Doublon arrêté par l'idempotence : l'action porte "executee" mais n'a
  // rien exécuté elle-même. Une des choses les plus parlantes à montrer.
  if (action.resultat?.deja_executee) {
    const doublon = document.createElement("p");
    doublon.className = "actions__doublon";
    doublon.textContent = `Déjà exécutée (doublon de l'action ${action.resultat.action_origine}).`;
    li.append(doublon);
  } else if (action.statut === "echouee" && action.resultat?.erreur) {
    const erreur = document.createElement("p");
    erreur.className = "actions__erreur";
    erreur.textContent = action.resultat.erreur;
    li.append(erreur);
  }

  if (action.statut === "executee") {
    const annulerBtn = document.createElement("button");
    annulerBtn.type = "button";
    annulerBtn.className = "actions__annuler-btn";
    annulerBtn.textContent = "Annuler";
    annulerBtn.addEventListener("click", () => annulerAction(action.id, annulerBtn));
    li.append(annulerBtn);
  }

  if (action.statut === "annulee") {
    const note = document.createElement("p");
    note.className = "actions__note";
    note.textContent = "Annulée.";
    li.append(note);
  }

  return li;
}

function mettreAJourBoutonExecuter() {
  const enAttente = actionsListe.querySelectorAll(".actions__checkbox").length > 0;
  executerBtn.hidden = !enAttente;
}

function afficherActions(actions) {
  actionsListe.replaceChildren();

  if (!actions || actions.length === 0) {
    actionsPanel.hidden = true;
    executerBtn.hidden = true;
    return;
  }

  for (const action of actions) {
    actionsListe.append(carteAction(action));
  }

  mettreAJourBoutonExecuter();
  actionsPanel.hidden = false;
}

// ---------------------------------------------------------------------------
// Redessine tout l'écran à partir d'un plan complet (même forme partout :
// réponse de /api/message, /api/plans/dernier, /api/plans/{id}/executer et
// /api/actions/{id}/annuler renvoient toutes un plan de cette forme).
// ---------------------------------------------------------------------------
function redessinerPlan(plan) {
  result.hidden = false;
  result.className = "result answer";
  result.replaceChildren();

  const texte = document.createElement("p");
  texte.className = "answer__text";
  texte.textContent = plan.reponse;

  const cout = document.createElement("p");
  cout.className = "answer__cost";
  cout.textContent = `${formaterCout(plan.cout_dollars)} — ${plan.tokens_entree} tokens entrée / ${plan.tokens_sortie} sortie`;

  result.append(texte, cout);

  afficherTrace(plan.outils_appeles);
  afficherActions(plan.actions);
}

// ---------------------------------------------------------------------------
// Exécuter : envoie uniquement les identifiants cochés. Tout le reste passe
// en "refusee" côté back — on n'a rien d'autre à envoyer.
// ---------------------------------------------------------------------------
async function executerPlan() {
  if (!planCourant) return;

  const idsApprouvees = [...actionsListe.querySelectorAll(".actions__checkbox:checked")].map(
    (case_) => Number(case_.dataset.actionId),
  );

  masquerErreur();
  executerBtn.disabled = true;
  executerBtn.textContent = "…";

  try {
    const reponse = await fetch(`${API_BASE}/api/plans/${planCourant.id}/executer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approuvees: idsApprouvees }),
    });
    const donnees = await reponse.json();
    if (!reponse.ok) throw new Error(donnees.detail ?? "Erreur inconnue.");

    planCourant = donnees;
    redessinerPlan(planCourant);
  } catch (error) {
    afficherErreur(error.message);
  } finally {
    executerBtn.disabled = false;
    executerBtn.textContent = "Exécuter";
  }
}

executerBtn.addEventListener("click", executerPlan);

// ---------------------------------------------------------------------------
// Annuler : uniquement sur une action "executee". N'affiche "annulée" que
// si le back répond 200 — un 502 laisse l'action executee, son effet existe
// toujours, et le dire "annulée" serait un mensonge.
// ---------------------------------------------------------------------------
async function annulerAction(actionId, bouton) {
  masquerErreur();
  bouton.disabled = true;
  bouton.textContent = "…";

  try {
    const reponse = await fetch(`${API_BASE}/api/actions/${actionId}/annuler`, { method: "POST" });
    const donnees = await reponse.json();
    if (!reponse.ok) throw new Error(donnees.detail ?? "Erreur inconnue.");

    planCourant = donnees;
    redessinerPlan(planCourant);
  } catch (error) {
    afficherErreur(error.message);
    bouton.disabled = false;
    bouton.textContent = "Annuler";
  }
}

// ---------------------------------------------------------------------------
// Envoi d'une intention. Une erreur ici ne doit pas effacer le plan déjà
// affiché : on le redessine tel quel et on ajoute juste le bandeau d'erreur.
// ---------------------------------------------------------------------------
form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const message = messageInput.value.trim();
  if (!message) return;

  masquerErreur();
  submitBtn.disabled = true;
  submitBtn.textContent = "…";
  result.hidden = false;
  result.className = "result loading";
  result.textContent = "L'agent réfléchit…";
  trace.hidden = true;
  actionsPanel.hidden = true;

  try {
    const reponse = await fetch(`${API_BASE}/api/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });

    // fetch ne lève pas d'exception sur un code d'erreur HTTP : il faut
    // vérifier reponse.ok soi-même (voir CONTRAT-API.md).
    const donnees = await reponse.json();

    if (!reponse.ok) {
      // 422 : FastAPI renvoie un detail structuré (liste d'erreurs de
      // validation), pas une phrase — on affiche donc le message prévu
      // par le contrat plutôt que donnees.detail brut.
      const messageErreur =
        reponse.status === 422
          ? "Le message ne peut pas être vide ou dépasser 2000 caractères."
          : donnees.detail ?? "Erreur inconnue.";
      throw new Error(messageErreur);
    }

    messageInput.value = "";
    planCourant = {
      id: donnees.plan_id,
      intention: message,
      reponse: donnees.reponse,
      modele: donnees.modele,
      tokens_entree: donnees.tokens_entree,
      tokens_sortie: donnees.tokens_sortie,
      cout_dollars: donnees.cout_dollars,
      outils_appeles: donnees.outils_appeles,
      actions: donnees.actions_proposees,
    };
    redessinerPlan(planCourant);
  } catch (error) {
    afficherErreur(error.message);
    // On ne laisse jamais un spinner infini ni un écran vide trompeur : on
    // revient au dernier plan connu s'il y en a un, sinon on masque juste
    // l'état "L'agent réfléchit…".
    if (planCourant) {
      redessinerPlan(planCourant);
    } else {
      result.hidden = true;
    }
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Envoyer";
  }
});

// ---------------------------------------------------------------------------
// Journal d'audit (palier 5) : tout ce qui a été décidé et fait, y compris
// les refus et les annulations — c'est volontaire, voir CONTRAT-API.md.
// ---------------------------------------------------------------------------

function carteJournal(entree) {
  const li = document.createElement("li");
  li.className = `journal__item journal__item--${entree.statut}`;

  const entete = document.createElement("div");
  entete.className = "journal__entete";

  const outil = document.createElement("code");
  outil.className = "journal__outil";
  outil.textContent = entree.outil;

  const badge = document.createElement("span");
  badge.className = `journal__badge journal__badge--${entree.statut}`;
  badge.textContent = LABEL_STATUT[entree.statut] ?? entree.statut;

  entete.append(outil, badge);

  if (typeof entree.duree_ms === "number") {
    const duree = document.createElement("span");
    duree.className = "journal__duree";
    duree.textContent = `${entree.duree_ms} ms`;
    entete.append(duree);
  }

  const horodatage = document.createElement("span");
  horodatage.className = "journal__horodatage";
  horodatage.textContent = (entree.execute_le ?? entree.cree_le ?? "").replace("T", " ");
  entete.append(horodatage);

  li.append(entete);

  // L'intention d'origine : c'est la réponse à "pourquoi l'agent a fait ça ?"
  const intention = document.createElement("p");
  intention.className = "journal__intention";
  intention.textContent = `« ${entree.intention} »`;
  li.append(intention);

  const args = document.createElement("pre");
  args.className = "journal__args";
  args.textContent = JSON.stringify(entree.arguments);
  li.append(args);

  if (entree.resultat?.deja_executee) {
    const doublon = document.createElement("p");
    doublon.className = "journal__doublon";
    doublon.textContent = `Déjà exécutée (doublon de l'action ${entree.resultat.action_origine}).`;
    li.append(doublon);
  } else if (entree.resultat?.erreur) {
    const erreur = document.createElement("p");
    erreur.className = "journal__erreur";
    erreur.textContent = entree.resultat.erreur;
    li.append(erreur);
  } else if (entree.resultat) {
    const resultat = document.createElement("pre");
    resultat.className = "journal__resultat";
    resultat.textContent = JSON.stringify(entree.resultat);
    li.append(resultat);
  }

  return li;
}

journalToggle.addEventListener("click", async () => {
  // Deuxième clic = replier, pas besoin de rappeler le back.
  if (!journalPanel.hidden) {
    journalPanel.hidden = true;
    return;
  }

  masquerErreur();
  journalToggle.disabled = true;

  try {
    const reponse = await fetch(`${API_BASE}/api/journal`);
    const donnees = await reponse.json();
    if (!reponse.ok) throw new Error(donnees.detail ?? "Erreur inconnue.");

    journalListe.replaceChildren();
    if (donnees.entrees.length === 0) {
      const vide = document.createElement("p");
      vide.className = "journal__vide";
      vide.textContent = "Aucune entrée pour l'instant.";
      journalListe.append(vide);
    } else {
      // Un compteur explicite : le jury doit voir d'un coup d'œil que rien
      // n'est masqué. Un journal d'audit tronqué sans le dire ne vaut rien.
      const compteur = document.createElement("p");
      compteur.className = "journal__compteur";
      const n = donnees.entrees.length;
      compteur.textContent = `${n} entrée${n > 1 ? "s" : ""}, de la plus récente à la plus ancienne`;
      journalListe.append(compteur);

      for (const entree of donnees.entrees) {
        journalListe.append(carteJournal(entree));
      }
    }
    journalPanel.hidden = false;
  } catch (error) {
    afficherErreur(error.message);
  } finally {
    journalToggle.disabled = false;
  }
});

// ---------------------------------------------------------------------------
// Restauration au chargement (palier 4) : le jury recharge la page en plein
// milieu, l'écran doit retrouver exactement où il en était.
// ---------------------------------------------------------------------------
async function restaurerDernierPlan() {
  try {
    const reponse = await fetch(`${API_BASE}/api/plans/dernier`);
    if (!reponse.ok) return;
    const plan = await reponse.json();
    if (!plan) return; // null = première ouverture, pas une erreur.

    planCourant = plan;
    redessinerPlan(plan);
  } catch {
    // Pas grave : l'écran reste vide, l'utilisateur peut taper une demande.
  }
}

verifierSante();
restaurerDernierPlan();
