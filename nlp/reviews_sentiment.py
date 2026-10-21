"""Tema e sentimento de reviews do app por regras (sem LLM, sem modelo baixado). Pronto para plugar; P-18.

Entrada: data/silver/reviews/data.parquet (pipelines/ingest_reviews_export.py).
Saída:   data/gold/review_themes/data.parquet, tabela irmã de gold.friction_themes
         (fonte x tema x mês x sentimento x volume; contrato contracts/export_review_themes.yaml).

Tema: multirrótulo, taxonomia fechada igual à de gold.friction_themes. Cada tema tem uma lista de padrões; o texto
(minúsculo, sem acento) recebe todo tema com padrão casando a partir do início de uma palavra. Nenhum -> 'outro'.
Sentimento: a nota manda (1-2 negativo, 3 neutro, 4-5 positivo). O léxico (palavras positivas - negativas, com
negação "nao/nunca/nem" invertendo a palavra seguinte) só decide a nota 3 e só derruba a nota quando discorda por
2 ou mais palavras (ex.: 5 estrelas com texto de reclamação vira negativo). Regras e limites em nlp/README.md.

Uso: python -I nlp/reviews_sentiment.py
"""
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ENTRADA = ROOT / "data" / "silver" / "reviews" / "data.parquet"
SAIDA = ROOT / "data" / "gold" / "review_themes" / "data.parquet"

# Regex aplicado ao texto normalizado, sempre a partir do início de uma palavra (\b). Radical sem fim de palavra
# casa derivados ("atras" -> atrasou); com \b no fim, só a palavra exata ("pontos?\b" não casa "pontual").
TEMAS = {
    "atraso/cancelamento": [r"atras", r"cancel", r"remarc", r"overbook", r"preteri", r"voo mudou", r"alteraram o voo"],
    "bagagem": [r"bagag", r"malas?\b", r"extravi", r"despach"],
    "reembolso": [r"reembols", r"estorn", r"devolu", r"ressarc", r"dinheiro de volta"],
    # mesmo tema de gold.friction_themes ("Dificuldade para contratar / acesso aos canais de venda"); em review de
    # loja quase tudo aqui é o próprio app e o check-in nele
    "canais de venda/app": [r"app\b", r"aplicativo", r"check-?in", r"check in", r"cartao de embarque", r"trava",
                            r"login", r"atualiza", r"bug", r"erro", r"site\b", r"senha"],
    "atendimento": [r"atend", r"sac\b", r"chat\b", r"telefon", r"ligu", r"ligac", r"suporte", r"resposta", r"descaso"],
    "pontos/resgate": [r"pontos?\b", r"milhas?\b", r"resgat", r"fidelidade", r"tudoazul", r"clube\b", r"categoria"],
    "preco": [r"caro\b", r"cara\b", r"preco", r"tarifa", r"taxas?\b", r"cobr", r"valor", r"promoc", r"barat"],
}
_RX = {tema: re.compile(r"\b(?:" + "|".join(pads) + ")") for tema, pads in TEMAS.items()}
POSITIVAS = {"bom", "boa", "otimo", "otima", "excelente", "facil", "rapido", "pratico", "funciona", "gostei",
             "recomendo", "perfeito", "melhor", "top", "maravilhoso", "eficiente", "resolveu", "ajudou", "adoro"}
NEGATIVAS = {"ruim", "pessimo", "pessima", "horrivel", "lento", "trava", "erro", "pior", "descaso",
             "absurdo", "lixo", "problema", "demora", "dificil", "falha", "decepcao", "vergonha", "perdi"}
NEGACAO = {"nao", "nunca", "nem"}


def normalizar(t):
    t = unicodedata.normalize("NFKD", t.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9\- ]+", " ", t)


def temas(texto):
    t = normalizar(texto)
    achados = [tema for tema, rx in _RX.items() if rx.search(t)]
    return achados or ["outro"]


def lexico(texto):
    palavras = normalizar(texto).split()
    saldo = 0
    for i, p in enumerate(palavras):
        sinal = 1 if p in POSITIVAS else -1 if p in NEGATIVAS else 0
        if sinal and i and palavras[i - 1] in NEGACAO and p not in NEGACAO:
            sinal = -sinal
        saldo += sinal
    return saldo


def sentimento(nota, texto):
    s = lexico(texto)
    pela_nota = "negativo" if nota <= 2 else "neutro" if nota == 3 else "positivo"
    if nota == 3 and s:
        return "positivo" if s > 0 else "negativo"
    if pela_nota == "positivo" and s <= -2:
        return "negativo"
    if pela_nota == "negativo" and s >= 2:
        return "neutro"  # texto elogia mas a nota é baixa: não vira positivo, só deixa de contar como reclamação
    return pela_nota


def classificar(df):
    df = df.assign(tema=df.texto.map(temas), sentimento=[sentimento(n, t) for n, t in zip(df.nota, df.texto)])
    return df.explode("tema")


def gold(df, saida=SAIDA):
    g = (classificar(df).groupby(["fonte", "tema", "ano_mes", "sentimento"]).size().rename("reviews")
         .astype("int64").reset_index())
    Path(saida).parent.mkdir(parents=True, exist_ok=True)
    g.to_parquet(saida, index=False)
    return g


if __name__ == "__main__":
    if not ENTRADA.exists():
        sys.exit(f"sem {ENTRADA}: rode pipelines/ingest_reviews_export.py com um export oficial; nada a fazer")
    print(gold(pd.read_parquet(ENTRADA)).to_string(index=False))
