// Base de l'API back (Pierre).
// Le back sert désormais ce front lui-même, donc la page et l'API partagent
// la même origine : une URL relative ("") suffit, et elle reste juste une
// fois l'application déployée — une adresse en dur pointerait vers le
// localhost du visiteur.
// Si le fichier est ouvert directement depuis le disque (file://), il n'y a
// pas d'origine HTTP à laquelle se rattacher : on vise alors le back local.
const API_BASE = window.location.protocol.startsWith("http")
  ? ""
  : "http://127.0.0.1:8000";

const statusEl = document.getElementById("status");
const statusText = document.getElementById("status-text");
const form = document.getElementById("message-form");
const messageInput = document.getElementById("message");
const submitBtn = document.getElementById("submit-btn");
const result = document.getElementById("result");
const trace = document.getElementById("trace");
const traceListe = document.getElementById("trace-liste");

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

// Panneau debug : la séquence des outils réellement appelés pour produire
// la réponse (palier "outils" — doit être montrable en 30 secondes, sans
// ajouter de print). `outils` peut être vide (aucun outil nécessaire) ou
// absent (ancien back sans ce champ) : dans les deux cas on masque le panneau.
function afficherTrace(outils) {
  traceListe.replaceChildren();

  if (!outils || outils.length === 0) {
    trace.hidden = true;
    return;
  }

  for (const appel of outils) {
    const item = document.createElement("li");
    item.className = "trace__item";

    const nom = document.createElement("code");
    nom.className = "trace__outil";
    nom.textContent = appel.outil;

    const args = document.createElement("pre");
    args.className = "trace__args";
    args.textContent = JSON.stringify(appel.arguments);

    const resultat = document.createElement("pre");
    const enErreur = appel.resultat && typeof appel.resultat === "object" && "erreur" in appel.resultat;
    resultat.className = enErreur ? "trace__resultat trace__resultat--erreur" : "trace__resultat";
    resultat.textContent = JSON.stringify(appel.resultat);

    item.append(nom, args, resultat);
    traceListe.append(item);
  }

  trace.hidden = false;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const message = messageInput.value.trim();
  if (!message) return;

  submitBtn.disabled = true;
  submitBtn.textContent = "…";
  result.hidden = false;
  result.className = "result loading";
  result.textContent = "L'agent réfléchit…";
  trace.hidden = true;

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
          ? "Le message ne peut pas être vide."
          : donnees.detail ?? "Erreur inconnue.";
      throw new Error(messageErreur);
    }

    result.className = "result answer";
    result.replaceChildren();

    const texte = document.createElement("p");
    texte.className = "answer__text";
    texte.textContent = donnees.reponse;

    const cout = document.createElement("p");
    cout.className = "answer__cost";
    cout.textContent = `${formaterCout(donnees.cout_dollars)} — ${donnees.tokens_entree} tokens entrée / ${donnees.tokens_sortie} sortie`;

    result.append(texte, cout);
    afficherTrace(donnees.outils_appeles);
  } catch (error) {
    result.className = "result error";
    result.textContent = error.message;
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Envoyer";
  }
});

verifierSante();
