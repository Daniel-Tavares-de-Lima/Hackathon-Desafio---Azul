# Comando unico: make all = ingest -> synthetic -> dbt build -> train -> score -> app
# Python roda com -I (isolado): dados baixados em data/bronze nunca entram no sys.path.
ifeq ($(OS),Windows_NT)
PY := .venv/Scripts/python
else
PY := .venv/bin/python
endif

.PHONY: all venv ingest ingest-tarifas ingest-vra gold synthetic

all: ingest gold synthetic

$(PY):
	python -m venv .venv
	$(PY) -m pip install -q -r requirements.txt

venv: $(PY)

ingest: ingest-tarifas ingest-vra

ingest-tarifas: $(PY)
	$(PY) -I pipelines/ingest_anac.py tarifas

ingest-vra: $(PY)
	$(PY) -I pipelines/ingest_anac.py vra

gold: $(PY)
	$(PY) -I pipelines/build_gold.py

synthetic: gold
	$(PY) -I pipelines/synthetic/generate.py
