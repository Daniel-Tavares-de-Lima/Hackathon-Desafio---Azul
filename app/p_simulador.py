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
passos = list(range(0, int(total) + 5_000, 5_000))
verba = st.select_slider("Verba de retenção", passos, value=min(100_000, passos[-1]), format_func=comum.brl)
sel = a[a.custo_acum <= verba]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Clientes acionados", comum.num(len(sel)))
c2.metric("Clientes salvos (esperado)", comum.num(sel.salvos.sum()), help="Soma de risco de evasão × efeito suposto")
c3.metric("Receita protegida (6 meses)", comum.brl(sel.protegida.sum()),
          help="Soma de risco de evasão × valor previsto (6 meses) × efeito suposto")
c4.metric("Retorno por R$ 1", comum.num(sel.protegida.sum() / max(sel.custo_estimado.sum(), 1), 1))

curva = alt.Chart(a.iloc[::10]).mark_line(color="#4f5d66").encode(
    x=alt.X("custo_acum:Q", axis=comum.eixo_br("Verba gasta (R$)")),
    y=alt.Y("protegida_acum:Q", axis=comum.eixo_br("Receita protegida (R$)")))
marca = alt.Chart().mark_rule(color="gray", strokeDash=[4, 4]).encode(x=alt.datum(verba))
st.altair_chart((curva + marca).properties(height=320), width="stretch")
st.caption(f"Ordem do agente: maior retorno estimado primeiro, entre os {comum.num(len(a))} clientes com ação "
           "recomendada (elegíveis entre os 50% de maior valor). Custos: pontos a R\\$ 0,02 + contato humano R\\$ 20 ou digital R\\$ 1, com teto "
           "por cliente (P-17).")

resumo = sel.assign(acao=sel.acao.map(comum.ACOES)).groupby("acao").agg(
    clientes=("cliente_id", "count"), custo=("custo_estimado", "sum"), receita_protegida=("protegida", "sum"))
st.dataframe(comum.tabela_br(resumo.reset_index(), {"clientes": 0, "custo": 0, "receita_protegida": 0}),
             hide_index=True, column_config={"acao": "Ação", "clientes": "Clientes", "custo": "Custo (R$)",
                                             "receita_protegida": "Receita protegida (R$)"})
