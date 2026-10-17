# Comando unico: make all = ingest -> synthetic -> dbt build -> train -> score -> app
# Python roda com -I (isolado): dados baixados em data/bronze nunca entram no sys.path.
ifeq ($(OS),Windows_NT)
PY := .venv/Scripts/python
else
PY := .venv/bin/python
endif

# Janela ANAC fixa (P-01): termina em 2026-08. Exportada para sobrepor o .env; a ingestao e idempotente
# (CSV presente no bronze nao e baixado de novo; silver so e refeito se faltar ou for mais velho que o bronze).
ANAC_END_MONTH ?= 2026-08
ANAC_MONTHS ?= 24
export ANAC_END_MONTH ANAC_MONTHS

.PHONY: all venv ingest ingest-tarifas ingest-vra gold synthetic ml test

all: ingest gold synthetic ml test

$(PY):
	python -m venv .venv
	$(PY) -m pip install -q -r requirements.txt

venv: $(PY)

ingest: ingest-tarifas ingest-vra

ingest-tarifas: $(PY)
	$(PY) -I pipelines/ingest_anac.py tarifas

ingest-vra: $(PY)
	$(PY) -I pipelines/ingest_anac.py vra

gold: ingest
	$(PY) -I pipelines/build_gold.py

synthetic: gold
	$(PY) -I pipelines/synthetic/generate.py

# Modelos (churn, CLV, personas, SHAP), score -> gold.customer_scores, fairness e circularidade. Ordem importa:
# score.py lê as previsões out-of-fold de churn/clv, as personas e os motivos; fairness e circularidade leem o score.
ml: synthetic
	$(PY) -I ml/features.py
	$(PY) -I ml/churn.py
	$(PY) -I ml/clv.py
	$(PY) -I ml/segment.py
	$(PY) -I ml/explain.py
	$(PY) -I ml/score.py
	$(PY) -I ml/fairness.py
	$(PY) -I ml/circularidade.py

test: synthetic ml
	$(PY) -I tests/test_contratos.py
