import streamlit as st

import comum

st.title("Personas")
st.caption(f"Visão em {comum.CORTE_TXT}, base sintética. Personas do k-means (ml/segment.py); ação = decisão do "
           "agente em lote para os elegíveis entre os 50% de maior valor (os demais o agente não aciona).")

perfil = comum.csv_ml("personas").merge(comum.csv_ml("personas_score")[
    ["persona", "score_medio_brl", "clv_previsto_medio_brl", "pct_top_decil", "p_evasao_media"]], on="persona")
lote = comum.lote_nba()
com_acao = lote[lote.acao != "sem_acao_automatica"]
top = (com_acao.groupby("persona").acao.agg(lambda x: x.value_counts().index[0]).map(comum.ACOES)
       .rename("acao_mais_recomendada"))
qtd = com_acao.groupby("persona").size().rename("clientes_com_acao")
perfil = perfil.merge(top, on="persona", how="left").merge(qtd, on="persona", how="left")

st.dataframe(comum.tabela_br(perfil, {
    "clientes": 0, "trechos_mes": 2, "tarifa_media_brl": 0, "antecedencia_mediana_dias": 0, "share_rota_fav": "pct",
    "razao_tendencia": 2, "gasto_12m_brl": 0, "score_medio_brl": 0, "clv_previsto_medio_brl": 0,
    "pct_top_decil": "pct", "p_evasao_media": 2, "clientes_com_acao": 0}), hide_index=True, column_config={
    "persona": "Persona", "clientes": "Clientes", "trechos_mes": "Trechos/mês", "tarifa_media_brl": "Tarifa média (R$)",
    "antecedencia_mediana_dias": "Antecedência (dias)", "share_rota_fav": "% na rota favorita",
    "razao_tendencia": st.column_config.Column("Tendência", help="trechos/mês recentes ÷ anteriores (1 = estável)"),
    "gasto_12m_brl": "Gasto 12 meses (R$)", "score_medio_brl": "Score médio (R$)",
    "clv_previsto_medio_brl": "Valor previsto médio 6 meses (R$)", "pct_top_decil": "% entre os 10% de maior valor",
    "p_evasao_media": "Risco de evasão médio", "acao_mais_recomendada": "Ação mais recomendada",
    "clientes_com_acao": "Clientes com ação"})

st.subheader("Ações do agente por persona")
mix = com_acao.assign(acao=com_acao.acao.map(comum.ACOES)).pivot_table(
    index="persona", columns="acao", values="cliente_id", aggfunc="count", fill_value=0)
NEUTRAS = ["#4f5d66", "#8a9ba8", "#b5543a", "#c9a227", "#6f8f72", "#a3a3a3", "#3d3d3d"]
st.bar_chart(mix, horizontal=True, height=320, color=NEUTRAS[:len(mix.columns)])
