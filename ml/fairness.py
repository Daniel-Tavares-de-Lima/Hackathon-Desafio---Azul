"""Fairness por região de origem (IBGE, pela UF do aeroporto de casa; P-16). Só reporta, não corrige.

Por região: score médio, taxa de oferta (decil 1 do score), erro do modelo (Brier e AUC da evasão nos elegíveis;
MAE do CLV) e, para contexto, o valor real (evasão e CLV futuros). Disparidade = máximo / mínimo entre regiões.

Uso: python -I ml/fairness.py   (grava ml/resultados/fairness_regiao.csv e fairness_disparidade.csv)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parent))
import features as F  # noqa: E402
from churn import RES  # noqa: E402
from score import SAIDA  # noqa: E402


def main():
    s = pd.read_parquet(SAIDA).set_index("cliente_id")
    s = s.join(F.alvos_oficiais()[["evasao", "clv_futuro_6m_brl"]])
    linhas = []
    for reg, g in s.groupby("regiao_origem"):
        e = g[g.elegivel_evasao]
        linhas.append({
            "regiao": reg, "clientes": len(g), "elegiveis": len(e),
            "score_medio_brl": g.score_valor_brl.mean(), "taxa_oferta_top_decil": (g.decil_score == 1).mean(),
            "evasao_real": e.evasao.mean(), "p_evasao_media": e.p_evasao.mean(),
            "brier_evasao": brier_score_loss(e.evasao, e.p_evasao), "auc_evasao": roc_auc_score(e.evasao, e.p_evasao),
            "clv_real_medio_brl": g.clv_futuro_6m_brl.mean(), "mae_clv_brl": (g.clv_previsto_6m_brl - g.clv_futuro_6m_brl).abs().mean(),
        })
    r = pd.DataFrame(linhas)
    r.to_csv(RES / "fairness_regiao.csv", index=False, float_format="%.4f")
    met = ["score_medio_brl", "taxa_oferta_top_decil", "brier_evasao", "auc_evasao", "mae_clv_brl", "clv_real_medio_brl"]
    disp = pd.DataFrame({"metrica": met, "min": [r[m].min() for m in met], "max": [r[m].max() for m in met],
                         "regiao_min": [r.regiao[r[m].idxmin()] for m in met], "regiao_max": [r.regiao[r[m].idxmax()] for m in met]})
    disp["razao_max_min"] = disp["max"] / disp["min"]
    disp.to_csv(RES / "fairness_disparidade.csv", index=False, float_format="%.4f")
    print(r.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    print(disp.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    assert np.isfinite(disp.razao_max_min).all()


if __name__ == "__main__":
    main()
