import altair as alt
import streamlit as st

import comum
import tools

st.title("Simulador de ROI")
st.warning("Os efeitos das ações são **supostos** (calibração própria, sem experimento nem fonte pública; "
           "docs/PREMISSAS.md, P-17). O simulador mostra a ordem de grandeza, não um resultado medido.")

lote = comum.lote_nba()
a = lote[lote.acao != "sem_acao_automatica"].sort_values("roi_estimado", ascending=False).copy()
a["efeito"] = a.acao.map(lambda x: tools.CATALOGO[x][0])
a["salvos"] = a.p_evasao * a.efeito
a["protegida"] = a.salvos * a.clv_previsto_6m_brl
a["custo_acum"] = a.custo_estimado.cumsum()
a["protegida_acum"] = a.protegida.cumsum()

total = float(a.custo_estimado.sum())
verba = st.slider("Verba de retenção (R$)", 0, int(total) + 1, min(100_000, int(total)), step=5_000)
sel = a[a.custo_acum <= verba]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Clientes acionados", f"{len(sel):,}".replace(",", "."))
c2.metric("Clientes salvos (esperado)", f"{sel.salvos.sum():,.0f}".replace(",", "."),
          help="Soma de p_evasao x efeito suposto")
c3.metric("Receita protegida (6m)", comum.brl(sel.protegida.sum()), help="Soma de p_evasao x CLV x efeito suposto")
c4.metric("Retorno por R$ 1", f"{sel.protegida.sum() / max(sel.custo_estimado.sum(), 1):.1f}".replace(".", ","))

curva = alt.Chart(a.iloc[::10]).mark_line().encode(
    x=alt.X("custo_acum:Q", title="Verba gasta (R$)"), y=alt.Y("protegida_acum:Q", title="Receita protegida (R$)"))
marca = alt.Chart().mark_rule(color="gray", strokeDash=[4, 4]).encode(x=alt.datum(verba))
st.altair_chart((curva + marca).properties(height=320), width="stretch")
n = f"{len(a):,}".replace(",", ".")
st.caption(f"Ordem do agente: maior ROI estimado primeiro, entre os {n} clientes com ação recomendada "
           "(elegíveis de decil 1 a 5). Custos: pontos a R\\$ 0,02 + contato humano R\\$ 20 ou digital R\\$ 1, com teto "
           "por cliente (P-17).")

st.dataframe(sel.assign(acao=sel.acao.map(comum.ACOES)).groupby("acao").agg(
    clientes=("cliente_id", "count"), custo=("custo_estimado", "sum"), receita_protegida=("protegida", "sum"))
    .reset_index(), hide_index=True, column_config={
    "acao": "Ação", "clientes": "Clientes",
    "custo": st.column_config.NumberColumn("Custo (R$)", format="%.0f"),
    "receita_protegida": st.column_config.NumberColumn("Receita protegida (R$)", format="%.0f")})
