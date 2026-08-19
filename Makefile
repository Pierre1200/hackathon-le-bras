# Raccourcis du projet. `make` seul affiche l'aide.

.PHONY: aide test eval demarrer

aide:
	@echo "  make test      lance les tests automatises (rapide, gratuit)"
	@echo "  make eval      rejoue les cas d'evaluation et sort un score (appelle le modele)"
	@echo "  make demarrer  lance l'application sur http://127.0.0.1:8000"

test:
	.venv/bin/python -m pytest tests/ -q

eval:
	.venv/bin/python -m eval.lancer

demarrer:
	.venv/bin/uvicorn back.main:app --reload
