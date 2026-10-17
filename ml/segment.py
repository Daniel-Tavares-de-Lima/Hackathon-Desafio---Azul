"""Personas: k-means sobre features padronizadas no corte 2026-02-28, k em {4, 5} pela silhueta.

Só clientes que voaram no histórico; quem não voou recebe a persona "Sem voo no histórico".
Nomes saem dos centróides por regras fixas (abaixo), não do arquétipo do gerador.

Uso: python -I ml/segment.py   (grava ml/resultados/personas*.csv e data/gold/_ml/personas.parquet)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
import features as F  # noqa: E402
from churn import RES, TMP  # noqa: E402

SEM_VOO = "Sem voo no histórico"
# (nome, coluna do centróide, maior ou menor); cada regra pega o cluster ainda sem nome mais extremo; o último fica com o resto
REGRAS = [
    ("Frequente de negócios", "log_taxa", "max"),
    ("Multirrota", "share_rota_fav", "min"),
    ("Em ascensão", "razao_tendencia", "max"),
    ("Caçador de tarifa", "log_tarifa", "min"),
]
RESTO = "Ocasional"


def matriz(f):
    return pd.DataFrame({
        "log_taxa": np.log1p(f.taxa_mensal),
        "log_tarifa": np.log(f.tarifa_media),
        "log_antecedencia": np.log1p(f.antecedencia_mediana.fillna(f.antecedencia_mediana.median())),
        "share_rota_fav": f.share_rota_fav,
        "razao_tendencia": f.razao_tendencia,
    }, index=f.index)


def nomear(centros):
    nomes, livres = {}, list(centros.index)
    for nome, col, modo in REGRAS[: len(centros) - 1]:
        c = centros.loc[livres, col]
        k = c.idxmax() if modo == "max" else c.idxmin()
        nomes[k] = nome
        livres.remove(k)
    nomes[livres[0]] = RESTO
    return nomes


def main():
    f = F.montar_features(F.CORTE_TESTE)
    voou = f[f.trechos_hist > 0]
    X = matriz(voou)
    Z = StandardScaler().fit_transform(X)
    amostra = np.random.default_rng(F.SEED).choice(len(Z), 10_000, replace=False)
    sil, modelos = {}, {}
    for k in (4, 5):
        modelos[k] = KMeans(k, n_init=10, random_state=F.SEED).fit(Z)
        sil[k] = silhouette_score(Z[amostra], modelos[k].labels_[amostra])
    k = max(sil, key=sil.get)
    rot = pd.Series(modelos[k].labels_, index=voou.index)
    centros = X.groupby(rot).mean()
    nomes = nomear(centros)
    persona = rot.map(nomes).reindex(f.index).fillna(SEM_VOO)

    resumo = voou.assign(persona=rot.map(nomes)).groupby("persona").agg(
        clientes=("taxa_mensal", "size"), trechos_mes=("taxa_mensal", "mean"), tarifa_media_brl=("tarifa_media", "mean"),
        antecedencia_mediana_dias=("antecedencia_mediana", "median"), share_rota_fav=("share_rota_fav", "mean"),
        razao_tendencia=("razao_tendencia", "median"), gasto_12m_brl=("gasto_12m", "mean"))
    resumo.loc[SEM_VOO, "clientes"] = int((persona == SEM_VOO).sum())
    resumo.to_csv(RES / "personas.csv", float_format="%.3f")
    pd.DataFrame({"k": list(sil), "silhueta": list(sil.values())}).to_csv(RES / "personas_silhueta.csv", index=False, float_format="%.4f")
    persona.rename("persona").to_frame().to_parquet(TMP / "personas.parquet")
    print(f"k={k}, silhueta {sil}")
    print(resumo.round(2).to_string())


if __name__ == "__main__":
    main()
