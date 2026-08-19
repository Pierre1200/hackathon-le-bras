# Raccourcis du projet. `make` seul affiche l'aide.

.PHONY: aide test eval demarrer reset etat

aide:
	@echo "  make test      lance les tests automatises (rapide, gratuit)"
	@echo "  make eval      rejoue les cas d'evaluation et sort un score (appelle le modele)"
	@echo "  make demarrer  lance l'application sur http://127.0.0.1:8000"
	@echo "  make reset     remet la base et les dossiers de sortie a zero"
	@echo "  make etat      montre ce que contient la base"

test:
	.venv/bin/python -m pytest tests/ -q

eval:
	.venv/bin/python -m eval.lancer

demarrer:
	.venv/bin/uvicorn back.main:app --reload

# Remet l'application dans l'etat d'un depot fraichement clone.
# ARRETE LE SERVEUR AVANT : supprimer la base pendant qu'il tourne lui fait
# recreer un fichier vide, sans les tables.
reset:
	@pkill -f "uvicorn back.main" 2>/dev/null || true
	@rm -f lebras.db
	@find outbox documents -type f ! -name '.gitkeep' -delete 2>/dev/null || true
	@.venv/bin/python -c "from back import tools, persistance" >/dev/null 2>&1
	@echo "base et dossiers de sortie remis a zero"
	@$(MAKE) --no-print-directory etat

# Montre ce que contient la base, sans rien modifier.
etat:
	@.venv/bin/python -c "import sqlite3; from back.persistance import DB_PATH; db = sqlite3.connect(DB_PATH); print('  employes :', db.execute('SELECT COUNT(*) FROM employes').fetchone()[0]); print('  tickets  :', db.execute('SELECT COUNT(*) FROM tickets').fetchone()[0]); print('  plans    :', db.execute('SELECT COUNT(*) FROM plans').fetchone()[0]); print('  actions  :', db.execute('SELECT COUNT(*) FROM actions').fetchone()[0]); print('  annuaire :', ', '.join(r[0] for r in db.execute('SELECT nom FROM employes ORDER BY id')))"
	@echo "  outbox    :" $$(ls outbox/ 2>/dev/null | grep -v gitkeep | wc -l | tr -d ' ') "fichier(s)"
	@echo "  documents :" $$(ls documents/ 2>/dev/null | grep -v gitkeep | wc -l | tr -d ' ') "fichier(s)"
