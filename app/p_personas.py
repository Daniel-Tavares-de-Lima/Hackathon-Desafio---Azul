import streamlit as st

import comum

st.title("Personas")
st.caption(f"Visão em {comum.CORTE_TXT}, base sintética. Personas do k-means (ml/segment.py); ação = decisão do "
           "agente em lote para os elegíveis de decil 1 a 5 (os demais o agente não aciona).")

perfil = comum.csv_ml("personas").merge(comum.csv_ml("personas_score")[
    ["persona", "score_medio_brl", "clv_previsto_medio_brl", "pct_top_decil", "p_evasao_media"]], on="persona")
lote = comum.lote_nba()
com_acao = lote[lote.acao != "sem_acao_automatica"]
top = (com_acao.groupby("persona").acao.agg(lambda x: x.value_counts().index[0]).map(comum.ACOES)
       .rename("acao_mais_recomendada"))
qtd = com_acao.groupby("persona").size().rename("clientes_com_acao")
perfil = perfil.merge(top, on="persona", how="left").merge(qtd, on="persona", how="left")

st.dataframe(perfil, hide_index=True, column_config={
    "persona": "Persona", "clientes": st.column_config.NumberColumn("Clientes", format="%d"),
    "trechos_mes": st.column_config.NumberColumn("Trechos/mês", format="%.2f"),
    "tarifa_media_brl": st.column_config.NumberColumn("Tarifa média (R$)", format="%.0f"),
    "antecedencia_mediana_dias": st.column_config.NumberColumn("Antecedência (dias)", format="%.0f"),
    "share_rota_fav": st.column_config.NumberColumn("% na rota favorita", format="percent"),
    "razao_tendencia": st.column_config.NumberColumn("Tendência", format="%.2f",
                                                     help="trechos/mês recentes ÷ anteriores (1 = estável)"),
    "gasto_12m_brl": st.column_config.NumberColumn("Gasto 12m (R$)", format="%.0f"),
    "score_medio_brl": st.column_config.NumberColumn("Score médio (R$)", format="%.0f"),
    "clv_previsto_medio_brl": st.column_config.NumberColumn("CLV 6m médio (R$)", format="%.0f"),
    "pct_top_decil": st.column_config.NumberColumn("% no top decil", format="percent"),
    "p_evasao_media": st.column_config.NumberColumn("p_evasao média", format="%.2f"),
    "acao_mais_recomendada": "Ação mais recomendada",
    "clientes_com_acao": st.column_config.NumberColumn("Clientes com ação", format="%d")})

st.subheader("Ações do agente por persona")
mix = com_acao.assign(acao=com_acao.acao.map(comum.ACOES)).pivot_table(
    index="persona", columns="acao", values="cliente_id", aggfunc="count", fill_value=0)
NEUTRAS = ["#4f5d66", "#8a9ba8", "#b5543a", "#c9a227", "#6f8f72", "#a3a3a3", "#3d3d3d"]
st.bar_chart(mix, horizontal=True, height=320, color=NEUTRAS[:len(mix.columns)])
