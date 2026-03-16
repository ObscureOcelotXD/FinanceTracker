# FinanceTracker — run with .env (optional) or with Infisical CLI injection

.PHONY: run run-infisical

# Normal run: uses .env if present (python-dotenv). No Infisical.
run:
	./start.sh

# Run with Infisical: CLI injects secrets into process env. No .env required.
# Requires: infisical login, infisical init (see docs/INFISICAL.md)
run-infisical:
	infisical run -- ./start.sh
