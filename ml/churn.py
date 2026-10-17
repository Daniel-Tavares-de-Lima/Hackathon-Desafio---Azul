"""Risco de evasão (6 meses), só elegíveis. LightGBM vs baseline logístico RFM.

Duas avaliações (model_card.md explica por quê):
- temporal (principal): treina no corte 2025-08-31 (rótulo set/2025-fev/2026 recalculado de synthetic_viagens),
  avalia no corte 2026-02-28 contra synthetic_alvos.
- produção: o modelo usado no score é treinado no corte 2026-02-28; a probabilidade de cada cliente vem de
  validação cruzada em 5 dobras por cliente (out-of-fold), avaliada no mesmo corte (não temporal).

Uso: python -I ml/churn.py   (grava ml/resultados/churn_*.csv e data/gold/_ml/churn_oof.parquet)
"""
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I tira o diretório do script do sys.path
import features as F  # noqa: E402

RES = F.ROOT / "ml" / "resultados"
TMP = F.ROOT / "data" / "gold" / "_ml"   # intermediários entre etapas do ml (não são tabela de consumo)
RFM = ["recencia_dias", "taxa_mensal", "gasto_12m", "razao_tendencia"]
PARAMS = dict(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=50, subsample=0.8,
              subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0, random_state=F.SEED, n_jobs=1,
              deterministic=True, force_row_wise=True, verbose=-1)


def modelo():
    return lgb.LGBMClassifier(**PARAMS)


def baseline():
    return make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))


def metricas(y, p):
    y, p = np.asarray(y), np.asarray(p)
    top = p >= np.quantile(p, 0.9)
    return {"auc_pr": average_precision_score(y, p), "prevalencia": y.mean(), "auc_roc": roc_auc_score(y, p),
            "precisao_top10": y[top].mean(), "recall_top10": y[top].sum() / y.sum(), "brier": brier_score_loss(y, p)}


def calibracao(y, p):
    d = pd.DataFrame({"y": np.asarray(y), "p": np.asarray(p)})
    d["decil"] = 10 - pd.qcut(d.p.rank(method="first"), 10, labels=False)  # 1 = maior risco
    return d.groupby("decil").agg(n=("y", "size"), p_media=("p", "mean"), evasao_real=("y", "mean")).reset_index()


def elegiveis(corte):
    b = F.base(corte)
    b = b[b.elegivel_evasao]
    assert b.evasao.notna().all()
    return b


def oof(b, cria, cols, devolver_modelos=False):
    """Probabilidade out-of-fold (5 dobras estratificadas por cliente) no mesmo corte.
    Com devolver_modelos, devolve também [(modelo da dobra, posições dos clientes que ele previu)]."""
    p = pd.Series(np.nan, index=b.index)
    dobras = []
    for tr, te in StratifiedKFold(5, shuffle=True, random_state=F.SEED).split(b, b.evasao):
        m = cria().fit(b.iloc[tr][cols], b.evasao.iloc[tr])
        p.iloc[te] = m.predict_proba(b.iloc[te][cols])[:, 1]
        dobras.append((m, te))
    return (p, dobras) if devolver_modelos else p


def main():
    RES.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)
    tr, te = elegiveis(F.CORTE_TREINO), elegiveis(F.CORTE_TESTE)
    linhas, calib = [], []
    for nome, cria, cols in [("lightgbm", modelo, F.MODELO), ("baseline_logistica_rfm", baseline, RFM)]:
        p = cria().fit(tr[cols], tr.evasao).predict_proba(te[cols])[:, 1]
        linhas.append({"avaliacao": "temporal 2025-08 -> 2026-02", "modelo": nome, **metricas(te.evasao, p)})
        calib.append(calibracao(te.evasao, p).assign(avaliacao="temporal", modelo=nome))
        po = oof(te, cria, cols)
        linhas.append({"avaliacao": "produção: OOF 5 dobras em 2026-02", "modelo": nome, **metricas(te.evasao, po)})
        calib.append(calibracao(te.evasao, po).assign(avaliacao="oof", modelo=nome))
        if nome == "lightgbm":
            po.rename("p_evasao").to_frame().to_parquet(TMP / "churn_oof.parquet")
    m = pd.DataFrame(linhas)
    m.insert(2, "n_treino", [len(tr), len(te) * 4 // 5] * 2)  # OOF: cada dobra treina em 4/5
    m.insert(3, "n_teste", len(te))
    m.to_csv(RES / "churn_metricas.csv", index=False, float_format="%.4f")
    pd.concat(calib).to_csv(RES / "churn_calibracao.csv", index=False, float_format="%.4f")
    print(m.to_string(index=False, float_format=lambda x: f"{x:.4f}"))


if __name__ == "__main__":
    main()
