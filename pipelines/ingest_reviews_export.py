"""Leitor do export OFICIAL de reviews do app (pronto para plugar; P-18). Nada aqui faz scraping.

Formatos aceitos (documentação pública conferida em 2026-10-20):
  Google Play Console, relatório de avaliações: gs://<bucket>/reviews/reviews_<pacote>_AAAAMM.csv (UTF-16), colunas
    "Package Name", "App Version Code", "App Version Name", "Reviewer Language", "Device",
    "Review Submit Date and Time", "Review Submit Millis Since Epoch", "Review Last Update Date and Time",
    "Review Last Update Millis Since Epoch", "Star Rating", "Review Title", "Review Text",
    "Developer Reply Date and Time", "Developer Reply Millis Since Epoch", "Developer Reply Text", "Review Link"
    https://support.google.com/googleplay/android-developer/answer/6135870
  App Store Connect: a Apple não oferece CSV de reviews; o caminho oficial é a API
    GET /v1/apps/{id}/customerReviews (JSON), salva como .json. Atributos usados de data[].attributes:
    rating, title, body, createdDate (territory e reviewerNickname são descartados).
    https://developer.apple.com/documentation/appstoreconnectapi/customerreview/attributes-data.dictionary

Uso: python -I pipelines/ingest_reviews_export.py [arquivo ...]   (padrão: data/bronze/reviews_export/*.csv|*.json)
Saída: data/silver/reviews/data.parquet com fonte, data, ano_mes, nota, texto, versao_app.
Anonimização na ingestão: autor, apelido, aparelho, idioma, link, ids e resposta da empresa nunca são lidos; o texto
passa por anonimizar(). Arquivos de export são dados não confiáveis: só lidos como CSV/JSON.
"""
import csv
import io
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ENTRADA = ROOT / "data" / "bronze" / "reviews_export"
SAIDA = ROOT / "data" / "silver" / "reviews" / "data.parquet"

# ponytail: regex simples; nome próprio só depois de palavra-gatilho. NER de verdade se o export real vazar nomes.
PADROES = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email]"),
    (re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"), "[cpf]"),
    (re.compile(r"(?:\+?55\s?)?\(?\b\d{2}\)?\s?9?\d{4}[-\s]?\d{4}\b"), "[telefone]"),
    (re.compile(r"\b(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{6}\b"), "[localizador]"),
    (re.compile(r"\b((?i:atendente|comiss[aá]ri[oa]|funcion[aá]ri[oa]|piloto|chamad[oa]|meu nome [eé]|sou [oa]))"
                r"\s+[A-ZÀ-Ú][a-zà-ú]+(?:\s+[A-ZÀ-Ú][a-zà-ú]+)?"), r"\1 [nome]"),
]


def anonimizar(texto):
    for rx, troca in PADROES:
        texto = rx.sub(troca, texto)
    return texto


def ler_play(path):
    bruto = Path(path).read_bytes()
    txt = bruto.decode("utf-16") if bruto[:2] in (b"\xff\xfe", b"\xfe\xff") else bruto.decode("utf-8-sig")
    linhas = []
    for r in csv.DictReader(io.StringIO(txt)):
        linhas.append({"fonte": "google_play", "data": r["Review Submit Date and Time"][:10],
                       "nota": r["Star Rating"], "versao_app": r["App Version Name"] or None,
                       "texto": " ".join(x for x in (r["Review Title"], r["Review Text"]) if x)})
    return linhas


def ler_appstore(path):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return [{"fonte": "app_store", "data": a["createdDate"][:10], "nota": a["rating"], "versao_app": None,
             "texto": " ".join(x for x in (a.get("title"), a.get("body")) if x)}
            for a in (item["attributes"] for item in d["data"])]


def ingerir(arquivos, saida=SAIDA):
    linhas = []
    for a in arquivos:
        linhas += ler_play(a) if Path(a).suffix.lower() == ".csv" else ler_appstore(a)
    df = pd.DataFrame(linhas, columns=["fonte", "data", "nota", "versao_app", "texto"])
    df["data"] = pd.to_datetime(df["data"]).dt.date
    df["ano_mes"] = pd.to_datetime(df["data"]).dt.strftime("%Y-%m")
    df["nota"] = df["nota"].astype("int32")
    df["texto"] = df["texto"].fillna("").map(anonimizar)
    df = df[df.nota.between(1, 5)].drop_duplicates()
    df = df[["fonte", "data", "ano_mes", "nota", "texto", "versao_app"]].sort_values(["data", "fonte"])
    Path(saida).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(saida, index=False)
    return df


if __name__ == "__main__":
    arqs = sys.argv[1:] or sorted(p for p in ENTRADA.glob("*") if p.suffix.lower() in (".csv", ".json"))
    if not arqs:
        sys.exit(f"nenhum export em {ENTRADA} (Play Console CSV ou App Store Connect JSON); nada a fazer")
    print(f"{len(ingerir(arqs))} reviews -> {SAIDA}")
