"""Circularidade do sintético: quanto features, personas e modelo recuperam o arquétipo oculto do gerador.

ÚNICO arquivo de ml/ que lê synthetic_archetypes_validacao, e só para medir, depois que tudo já foi treinado e
gravado; nada daqui volta para modelo, score ou app (o contrato da tabela proíbe uso como feature).

Uso: python -I ml/circularidade.py   (grava ml/resultados/circularidade_*.csv)
"""
import sys
from pathlib import Path

import pandas as pd
from sklearn.metrics import adjusted_rand_score, roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parent))
import features as F  # noqa: E402
from churn import RES  # noqa: E402
from score import SAIDA  # noqa: E402


def main():
    arq = F._ler("synthetic_archetypes_validacao").set_index("cliente_id").arquetipo
    f = F.montar_features(F.CORTE_TESTE)
    s = pd.read_parquet(SAIDA).set_index("cliente_id").join(arq).join(F.alvos_oficiais().evasao)
    a = arq.reindex(f.index)

    # 1) proxies de uma coluna só (referência da auditoria: 0,887 e 0,862; a definição exata varia em +-0,01)
    vg = F._ler("synthetic_viagens")
    vg = vg[vg.data_voo <= F.CORTE_TESTE]
    antec = vg.groupby("cliente_id").antecedencia_dias.mean()  # média de todos os trechos, só quem tem viagem
    proxy = pd.DataFrame([
        {"arquetipo": "lazer_premium", "feature": "antecedência média (clientes com viagem)",
         "auc": roc_auc_score(arq.reindex(antec.index) == "lazer_premium", antec), "referencia_auditoria": 0.887},
        {"arquetipo": "corporativo_frequente", "feature": "trechos voados no histórico (todos os clientes)",
         "auc": roc_auc_score(a == "corporativo_frequente", f.trechos_hist), "referencia_auditoria": 0.862},
    ])
    proxy.to_csv(RES / "circularidade_proxy.csv", index=False, float_format="%.4f")

    # 2) personas x arquétipo: pureza (fração do arquétipo dominante) e ARI
    v = s[s.persona != "Sem voo no histórico"]
    tab = pd.crosstab(v.persona, v.arquetipo)
    pureza = (tab.max(axis=1) / tab.sum(axis=1)).rename("pureza")
    tab = tab.join(pureza).join(tab.idxmax(axis=1).rename("arquetipo_dominante"))
    tab.to_csv(RES / "circularidade_personas.csv", float_format="%.4f")
    resumo = {"pureza_global": tab.drop(columns=["pureza", "arquetipo_dominante"]).max(axis=1).sum() / len(v),
              "pureza_maioria_trivial": v.arquetipo.value_counts(normalize=True).iloc[0],
              "ari_personas_arquetipo": adjusted_rand_score(v.arquetipo, v.persona)}

    # 3) modelo de evasão por arquétipo (elegíveis): AUC e calibração dentro de cada um
    e = s[s.elegivel_evasao]
    por = e.groupby("arquetipo").apply(lambda g: pd.Series({
        "elegiveis": len(g), "evasao_real": g.evasao.mean(), "p_media": g.p_evasao.mean(),
        "auc": roc_auc_score(g.evasao, g.p_evasao) if g.evasao.nunique() == 2 else float("nan")}), include_groups=False)
    por.to_csv(RES / "circularidade_churn_arquetipo.csv", float_format="%.4f")
    pd.DataFrame([resumo]).to_csv(RES / "circularidade_resumo.csv", index=False, float_format="%.4f")
    print(proxy.to_string(index=False), "\n", tab.round(3).to_string(), "\n", resumo, "\n", por.round(3).to_string())


if __name__ == "__main__":
    main()
