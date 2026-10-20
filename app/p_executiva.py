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
c1.metric("Clientes na base", f"{len(s):,}".replace(",", "."))
c2.metric("Receita em risco · alto valor", comum.brl(alto.receita_em_risco.sum()),
          help="Soma de p_evasao x CLV de 6 meses nos decis 1 e 2 (só elegíveis à evasão)")
c3.metric("CLV 6m · alto valor", comum.brl(alto.clv_previsto_6m_brl.sum()))
c4.metric("Alto valor com ameaça recente", f"{alto.cliente_id.isin(ameacados).sum():,}".replace(",", "."))

st.subheader("Distribuição do score de valor")
hist = s[s.score_valor_brl > 0].assign(log_score=lambda d: np.log10(d.score_valor_brl))
st.altair_chart(alt.Chart(hist).mark_bar().encode(
    x=alt.X("log_score:Q", bin=alt.Bin(maxbins=50), title="Score de valor (log10 de R$)"),
    y=alt.Y("count():Q", title="Clientes")).properties(height=260), width="stretch")
st.caption("Score = CLV 6m x (1 - p_evasao) + potencial de crescimento (docs/PREMISSAS.md, P-16). "
           "1 = R\\$ 10, 3 = R\\$ 1.000, 4 = R\\$ 10.000.")

st.subheader("Personas")
p = comum.csv_ml("personas_score")
st.dataframe(p, hide_index=True, column_config={
    "persona": "Persona", "clientes": "Clientes",
    "score_medio_brl": st.column_config.NumberColumn("Score médio (R$)", format="%.0f"),
    "clv_previsto_medio_brl": st.column_config.NumberColumn("CLV 6m médio (R$)", format="%.0f"),
    "pct_top_decil": st.column_config.NumberColumn("% no top decil", format="percent"),
    "p_evasao_media": st.column_config.NumberColumn("p_evasao média", format="%.2f"),
    "elegiveis": "Elegíveis à evasão"})
