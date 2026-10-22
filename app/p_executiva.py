import altair as alt
import numpy as np
import streamlit as st

import comum

st.title("Visão executiva")
st.caption(f"Visão em {comum.CORTE_TXT}, base sintética. Previsões para os 6 meses seguintes ao corte.")

s = comum.scores()
alto = s[s.faixa_valor == "alto"]
ameacados = set(comum.radar().cliente_id)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Clientes na base", comum.num(len(s)))
c2.metric("Receita em risco · alto valor", comum.brl(alto.receita_em_risco.sum()),
          help="Soma de risco de evasão × valor previsto (6 meses) nos 20% de maior valor (só elegíveis à evasão)")
c3.metric("Valor previsto (6 meses) · alto valor", comum.brl(alto.clv_previsto_6m_brl.sum()))
c4.metric("Alto valor com ameaça recente", comum.num(alto.cliente_id.isin(ameacados).sum()))

st.subheader("Distribuição do score de valor")
hist = s[s.score_valor_brl > 0].assign(log_score=lambda d: np.log10(d.score_valor_brl))
rotulo_rs = "'R$ ' + " + comum.TROCA_BR.format(x="format(pow(10, datum.value), ',.0f')")
st.altair_chart(alt.Chart(hist).mark_bar(color="#4f5d66").encode(
    x=alt.X("log_score:Q", bin=alt.Bin(maxbins=50),
            axis=alt.Axis(title="Score de valor (R$, escala log)", labelExpr=rotulo_rs, values=[1, 2, 3, 4, 5])),
    y=alt.Y("count():Q", axis=comum.eixo_br("Clientes"))).properties(height=260), width="stretch")
st.caption("Score = valor previsto (6 meses) × (1 − risco de evasão) + potencial de crescimento "
           "(docs/PREMISSAS.md, P-16).")

st.subheader("Personas")
p = comum.csv_ml("personas_score")
st.dataframe(comum.tabela_br(p, {"clientes": 0, "score_medio_brl": 0, "clv_previsto_medio_brl": 0,
                                 "pct_top_decil": "pct", "p_evasao_media": 2, "elegiveis": 0}),
             hide_index=True, column_config={
    "persona": "Persona", "clientes": "Clientes", "score_medio_brl": "Score médio (R$)",
    "clv_previsto_medio_brl": "Valor previsto médio 6 meses (R$)", "pct_top_decil": "% entre os 10% de maior valor",
    "p_evasao_media": "Risco de evasão médio", "elegiveis": "Elegíveis à evasão"})
