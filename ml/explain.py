"""SHAP (TreeExplainer) no corte 2026-02-28.

- Motivos por cliente (vão para gold.customer_scores via score.py): SHAP do modelo da dobra de churn.oof que
  produziu o p_evasao do cliente e que não viu o rótulo dele.
- Importância global e efeito nos expostos (shap_churn.csv, shap_ameacas.csv) e SHAP do CLV (shap_clv.csv): modelo
  treinado no corte inteiro, só para descrever o que o modelo aprendeu; não chega a nenhum cliente.

Motivo = feature com maior contribuição SHAP positiva (aumenta o risco), escrita com o valor do cliente.

Uso: python -I ml/explain.py   (grava ml/resultados/shap_*.csv e data/gold/_ml/motivos.parquet)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import shap

sys.path.insert(0, str(Path(__file__).resolve().parent))
import churn  # noqa: E402
import clv  # noqa: E402
import features as F  # noqa: E402
from churn import RES, TMP  # noqa: E402


def _n(x, casas=0):
    """Número no formato brasileiro (1.234,5)."""
    return f"{x:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(x):
    return f"{_n(100 * x)}%"


# feature -> frase neutra com o valor do cliente (v); o SHAP diz que o valor pesa a favor do risco, a frase só
# descreve o valor (o efeito não é monotônico: "muito" ou "pouco" depende do cliente). NaN cai no texto "sem ..."
FRASES = {
    "recencia_dias": lambda v: f"não voa há {_n(v)} dias",
    "taxa_mensal": lambda v: f"média de {_n(v, 1)} trechos por mês no histórico",
    "trechos_6m": lambda v: f"voou {_n(v)} trechos nos últimos 6 meses" if v > 0 else "não voou nos últimos 6 meses",
    "trechos_12m": lambda v: f"voou {_n(v)} trechos nos últimos 12 meses",
    "razao_tendencia": lambda v: (f"a frequência caiu {_pct(1 - v)} nos últimos 6 meses" if v < 1
                                  else f"a frequência recente é {_n(v, 1)} vezes a anterior"),
    "gasto_12m": lambda v: f"gastou R$ {_n(v)} em passagens nos últimos 12 meses",
    "tarifa_media": lambda v: f"paga tarifa média de R$ {_n(v)}",
    "antecedencia_mediana": lambda v: f"compra com {_n(v)} dias de antecedência (mediana)",
    "n_pares": lambda v: f"voou {_n(v)} rota(s) diferente(s) em 12 meses",
    "share_rota_fav": lambda v: f"{_pct(v)} dos voos concentrados numa única rota",
    "eventos_graves_90d": lambda v: (f"teve {_n(v)} voo(s) com atraso grave (> 60 min) ou cancelamento nos últimos 90 dias"
                                     if v > 0 else "nenhum atraso grave nos últimos 90 dias"),
    "cancelados_12m": lambda v: f"teve {_n(v)} voo(s) cancelado(s) em 12 meses",
    "pct_atraso30_12m": lambda v: f"{_pct(v)} dos voos com atraso acima de 30 min em 12 meses",
    "nivel_12m": lambda v: f"nível {F.NIVEIS[int(v)]} pelos voos dos últimos 12 meses",
    "folga_pct_nivel": lambda v: (f"está só {_pct(v)} acima do limite do nível, perto de cair" if v < 0.25
                                  else f"tem folga de {_pct(v)} sobre o limite do nível"),
    "falta_pct_proximo": lambda v: f"faltam {_pct(v)} para o próximo nível",
    "a_6m": lambda v: (f"sofreu {_n(v)} ameaça(s) de atraso grave (A) nos últimos 6 meses" if v > 0
                       else "sem ameaça de atraso grave (A) nos últimos 6 meses"),
    "dias_desde_a": lambda v: f"última ameaça de atraso grave (A) há {_n(v)} dias",
    "b_saida_fav_6m": lambda v: ("a Azul saiu da rota que ele mais voa (B)" if v > 0
                                 else "a rota que ele mais voa segue operada pela Azul"),
    "b_reducao_fav_6m": lambda v: ("a Azul reduziu os voos na rota que ele mais voa (B)" if v > 0
                                   else "sem redução de voos na rota que ele mais voa"),
    "c_queda_fav_6m": lambda v: ("um concorrente baixou a tarifa na rota que ele mais voa (C)" if v > 0
                                 else "sem queda de tarifa de concorrente na rota que ele mais voa"),
    "dias_desde_bc": lambda v: f"última ameaça na rota favorita (B/C) há {_n(v)} dias",
}
SEM_VALOR = {"dias_desde_a": "sem ameaça de atraso grave (A) em 12 meses",
             "dias_desde_bc": "sem ameaça na rota favorita (B/C) em 12 meses",
             "antecedencia_mediana": "sem compra de ida registrada", "folga_pct_nivel": "sem nível nos últimos 12 meses",
             "falta_pct_proximo": "já está no nível mais alto", "pct_atraso30_12m": "sem voo nos últimos 12 meses"}
assert set(FRASES) == set(F.MODELO)


# Contagem de evento: zero não é motivo de risco para quem lê (o modelo pode dar SHAP > 0 a "nenhum cancelamento"
# por correlação com frequência); nesses casos o motivo é pulado e entra o próximo.
SO_SE_HOUVE = {"eventos_graves_90d", "cancelados_12m", "a_6m", "b_saida_fav_6m", "b_reducao_fav_6m", "c_queda_fav_6m"}
AMEACAS = ["a_6m", "dias_desde_a", "b_saida_fav_6m", "b_reducao_fav_6m", "c_queda_fav_6m", "dias_desde_bc"]


def frase(col, v):
    return SEM_VALOR.get(col, f"sem dado de {col}") if pd.isna(v) else FRASES[col](v)


def motivos(X, sv, k=3):
    """Top-k features com SHAP > 0 por cliente, em frase; None quando não há k motivos válidos."""
    ordem = np.argsort(-sv, axis=1, kind="stable")
    cols = np.array(X.columns)
    linhas = []
    for i in range(len(X)):
        ok = [j for j in ordem[i] if sv[i, j] > 0 and not (cols[j] in SO_SE_HOUVE and X.iat[i, j] == 0)][:k]
        linhas.append([frase(cols[j], X.iat[i, j]) for j in ok] + [None] * (k - len(ok)))
    return pd.DataFrame(linhas, index=X.index, columns=[f"motivo_{n + 1}" for n in range(k)])


def importancia(sv, cols):
    return pd.DataFrame({"feature": cols, "shap_medio_abs": np.abs(sv).mean(axis=0)}).sort_values(
        "shap_medio_abs", ascending=False, kind="stable").reset_index(drop=True)


def main():
    te = F.base(F.CORTE_TESTE)
    el = te[te.elegivel_evasao]
    X = el[F.MODELO]
    m = churn.modelo().fit(X, el.evasao)
    sv = shap.TreeExplainer(m).shap_values(X)
    sv = sv[1] if isinstance(sv, list) else sv  # binário: log-odds da classe 1
    imp = importancia(sv, F.MODELO)
    imp["rank"] = imp.index + 1
    imp.to_csv(RES / "shap_churn.csv", index=False, float_format="%.5f")

    mc = clv.modelo().fit(te[F.MODELO], te.clv_futuro_6m_brl)
    imp_c = importancia(shap.TreeExplainer(mc).shap_values(te[F.MODELO]), F.MODELO)
    imp_c.to_csv(RES / "shap_clv.csv", index=False, float_format="%.5f")

    # Ameaças são raras: a média global dilui. Efeito nos expostos = SHAP médio de quem tem a ameaça (log-odds)
    exp = []
    for col in AMEACAS:
        e = X[col].notna() & (X[col] > 0) if not col.startswith("dias") else X[col].notna()
        j = F.MODELO.index(col)
        exp.append({"feature": col, "expostos": int(e.sum()), "shap_medio_expostos": sv[e.values, j].mean(),
                    "shap_medio_nao_expostos": sv[~e.values, j].mean(), "rank_global": int(imp.loc[imp.feature == col, "rank"].iloc[0])})
    exp = pd.DataFrame(exp)
    exp.to_csv(RES / "shap_ameacas.csv", index=False, float_format="%.4f")
    # Motivos: cada cliente explicado pelo modelo da dobra que o previu (o mesmo que gerou o p_evasao gravado)
    p, dobras = churn.oof(el, churn.modelo, F.MODELO, devolver_modelos=True)
    p_gravado = pd.read_parquet(TMP / "churn_oof.parquet").p_evasao.reindex(el.index)
    assert np.allclose(p, p_gravado, rtol=0, atol=1e-12), "dobras diferentes das de churn.py"
    sv_oof = np.full(X.shape, np.nan)
    for md, te in dobras:
        s = shap.TreeExplainer(md).shap_values(X.iloc[te])
        sv_oof[te] = s[1] if isinstance(s, list) else s
    assert not np.isnan(sv_oof).any()
    motivos(X, sv_oof).to_parquet(TMP / "motivos.parquet")
    print("SHAP evasão (top 10):\n", imp.head(10).to_string(index=False))
    print("ameaças (SHAP nos expostos, log-odds):")
    print(exp.to_string(index=False))
    print("SHAP CLV (top 5):\n", imp_c.head(5).to_string(index=False))


if __name__ == "__main__":
    main()
