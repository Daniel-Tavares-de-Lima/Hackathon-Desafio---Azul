"""CLV de 6 meses (clv_futuro_6m_brl = receita aérea bruta de mar a ago/2026). A base só tem 6 meses de futuro:
não há rótulo de 12 meses e nada aqui o extrapola.

Baseline RFM: gasto dos últimos 12 meses / 2 (ritmo recente). Modelo: LightGBM regressor (Tweedie: alvo >= 0
com muitos zeros). Mesmas duas avaliações do churn.py (temporal principal; OOF no corte 2026-02 para produção).

Uso: python -I ml/clv.py   (grava ml/resultados/clv_metricas.csv e data/gold/_ml/clv_oof.parquet)
"""
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import KFold

sys.path.insert(0, str(Path(__file__).resolve().parent))
import features as F  # noqa: E402
from churn import PARAMS, RES, TMP  # noqa: E402


def modelo():
    return lgb.LGBMRegressor(**PARAMS, objective="tweedie", tweedie_variance_power=1.3)


def baseline_rfm(b):
    return b.gasto_12m / 2


def gain_top10(y, pred):
    """Fração do valor futuro total capturada pelos 10% com maior previsão."""
    y, pred = np.asarray(y), np.asarray(pred)
    top = np.argsort(-pred, kind="stable")[: int(round(0.1 * len(y)))]
    return y[top].sum() / y.sum()


def metricas(y, pred):
    return {"mae_brl": mean_absolute_error(y, pred), "r2": r2_score(y, pred), "gain_top10": gain_top10(y, pred)}


def oof(b):
    pred = pd.Series(np.nan, index=b.index)
    for tr, te in KFold(5, shuffle=True, random_state=F.SEED).split(b):
        m = modelo().fit(b.iloc[tr][F.MODELO], b.clv_futuro_6m_brl.iloc[tr])
        pred.iloc[te] = m.predict(b.iloc[te][F.MODELO])
    return pred


def main():
    tr, te = F.base(F.CORTE_TREINO), F.base(F.CORTE_TESTE)
    y = te.clv_futuro_6m_brl
    po = oof(te)
    linhas = [
        {"avaliacao": "temporal 2025-08 -> 2026-02", "modelo": "lightgbm",
         **metricas(y, modelo().fit(tr[F.MODELO], tr.clv_futuro_6m_brl).predict(te[F.MODELO]))},
        {"avaliacao": "temporal 2025-08 -> 2026-02", "modelo": "baseline_rfm_gasto12m_div2", **metricas(y, baseline_rfm(te))},
        {"avaliacao": "produção: OOF 5 dobras em 2026-02", "modelo": "lightgbm", **metricas(y, po)},
        {"avaliacao": "referência", "modelo": "aleatório", "mae_brl": np.nan, "r2": np.nan, "gain_top10": 0.10},
        {"avaliacao": "referência", "modelo": "oráculo (ordem perfeita)", "mae_brl": 0.0, "r2": 1.0, "gain_top10": gain_top10(y, y)},
    ]
    m = pd.DataFrame(linhas)
    m.to_csv(RES / "clv_metricas.csv", index=False, float_format="%.4f")
    po.rename("clv_previsto_6m_brl").to_frame().to_parquet(TMP / "clv_oof.parquet")
    print(m.to_string(index=False, float_format=lambda x: f"{x:.4f}"))


if __name__ == "__main__":
    main()
