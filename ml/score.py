"""Score de Alto Valor no corte 2026-02-28 -> data/gold/customer_scores/data.parquet (contrato gold_customer_scores.yaml).

score_valor_brl = clv_previsto_6m_brl x (1 - p_evasao) + POTENCIAL x clv_previsto_6m_brl x clip(razao_tendencia - 1; 0; 1)

- 1º termo: receita de 6 meses que se espera reter. O CLV previsto já embute alguma evasão; multiplicar por (1 - p)
  pesa de novo o risco de propósito, para o ranking preferir valor estável a valor incerto (decisão de produto).
- 2º termo (potencial): prêmio de até 25% do CLV para quem acelerou (frequência dos últimos 6 meses acima da dos
  meses anteriores; dobrar a frequência dá o teto). O horizonte é de 6 meses e o crescimento continua depois dele;
  25% é peso de produto, sem fonte pública: dá desempate a quem está subindo sem deixar um cliente pequeno em alta
  passar um grande estável (o termo nunca passa de 1/4 do próprio CLV).
- Não elegíveis à evasão (< 3 trechos esperados em 6 meses) não têm p_evasao; no score usam a prevalência de evasão
  dos elegíveis (P-16).
- p_evasao e clv_previsto vêm das previsões out-of-fold (churn.py, clv.py): nenhum cliente é pontuado por um modelo
  que viu o rótulo dele.

Uso: python -I ml/score.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import features as F  # noqa: E402
from churn import RES, TMP  # noqa: E402

sys.path.insert(0, str(F.ROOT / "pipelines"))
from build_gold import checar_contrato  # noqa: E402

POTENCIAL = 0.25
SAIDA = F.ROOT / "data" / "gold" / "customer_scores" / "data.parquet"
CONTRATO = F.ROOT / "contracts" / "gold_customer_scores.yaml"


def calcular(clv, p, razao):
    return clv * (1 - p) + POTENCIAL * clv * np.clip(razao - 1, 0, 1)


def main():
    f = F.montar_features(F.CORTE_TESTE)
    p = pd.read_parquet(TMP / "churn_oof.parquet").p_evasao.reindex(f.index)
    clv = pd.read_parquet(TMP / "clv_oof.parquet").clv_previsto_6m_brl.reindex(f.index).clip(lower=0)
    pers = pd.read_parquet(TMP / "personas.parquet").persona.reindex(f.index)
    mot = pd.read_parquet(TMP / "motivos.parquet").reindex(f.index)
    assert p[f.elegivel_evasao].notna().all() and p[~f.elegivel_evasao].isna().all()
    p_ref = p.mean()
    p_uso = p.fillna(p_ref)

    d = pd.DataFrame({
        "cliente_id": f.index,
        "data_corte": F.CORTE_TESTE.date(),
        "regiao_origem": f.regiao_origem.values,
        "elegivel_evasao": f.elegivel_evasao.values,
        "p_evasao": p.values,
        "clv_previsto_6m_brl": clv.values,
        "potencial_brl": (POTENCIAL * clv * np.clip(f.razao_tendencia - 1, 0, 1)).values,
        "score_valor_brl": calcular(clv, p_uso, f.razao_tendencia).values,
        "persona": pers.values,
    })
    d["decil_score"] = (10 - pd.qcut(d.score_valor_brl.rank(method="first"), 10, labels=False)).astype("int64")
    d = d.join(mot.reset_index(drop=True))
    d = d.sort_values(["decil_score", "score_valor_brl", "cliente_id"], ascending=[True, False, True], kind="stable")
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    d.to_parquet(SAIDA, compression="zstd", index=False)
    erros = checar_contrato(CONTRATO)
    assert not erros, erros

    # sensibilidade do peso do potencial: quanto do top decil muda sem ele
    top = set(d.cliente_id[d.decil_score == 1])
    s0 = calcular(clv, p_uso, f.razao_tendencia * 0 + 1)
    top0 = set(s0.nlargest(len(top)).index)
    resumo = pd.DataFrame([{"clientes": len(d), "elegiveis": int(d.elegivel_evasao.sum()), "p_ref_nao_elegiveis": p_ref,
                            "score_medio_brl": d.score_valor_brl.mean(), "corte_top_decil_brl": d.score_valor_brl[d.decil_score == 1].min(),
                            "overlap_top_decil_sem_potencial": len(top & top0) / len(top)}])
    resumo.to_csv(RES / "score_resumo.csv", index=False, float_format="%.4f")
    d.groupby("persona").agg(clientes=("cliente_id", "size"), score_medio_brl=("score_valor_brl", "mean"),
                             clv_previsto_medio_brl=("clv_previsto_6m_brl", "mean"),
                             pct_top_decil=("decil_score", lambda x: (x == 1).mean()), p_evasao_media=("p_evasao", "mean"),
                             elegiveis=("elegivel_evasao", "sum")).to_csv(RES / "personas_score.csv", float_format="%.4f")
    print(resumo.T.to_string(header=False))


if __name__ == "__main__":
    main()
