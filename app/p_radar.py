import altair as alt
import streamlit as st

import comum
import nba_agent

st.title("Radar de ameaças")
st.caption(f"Visão em {comum.CORTE_TXT}, base sintética. Janelas até o corte: A nos últimos 90 dias, B e C nos "
           "últimos 180 dias (as mesmas que o agente usa).")

r = comum.radar()
t = comum.ameacas_recentes()
alto = set(comum.scores().query("faixa_valor == 'alto'").cliente_id)


def contador(col, titulo, mask, ajuda):
    ids = set(t.loc[mask, "cliente_id"])
    col.metric(titulo, f"{len(ids):,}".replace(",", "."), f"{len(ids & alto):,} de alto valor".replace(",", "."),
               delta_color="off", help=ajuda)


c1, c2, c3 = st.columns(3)
contador(c1, comum.TIPOS["A"], t.tipo_ameaca == "A", "Clientes com 2 eventos graves (atraso/cancelamento) em 90 dias")
contador(c2, comum.TIPOS["B"] + " (saída + redução)", t.tipo_ameaca == "B",
         f"Saída total: {t[t.detalhe == 'saida_total'].cliente_id.nunique()} · redução: "
         f"{t[t.detalhe == 'reducao'].cliente_id.nunique()} clientes")
contador(c3, comum.TIPOS["C"], t.tipo_ameaca == "C", "Queda de tarifa de concorrente no par que o cliente voa")

f1, f2 = st.columns([3, 1])
tipos = f1.multiselect("Tipo de ameaça", list(comum.TIPOS), default=list(comum.TIPOS), format_func=comum.TIPOS.get)
so_alto = f2.checkbox("Só alto valor (decil 1 e 2)")
v = r[r.tipos.apply(lambda x: any(k in x for k in tipos))]
if so_alto:
    v = v[v.faixa_valor == "alto"]
sem_p = v.p_evasao.isna().sum()
v = v.dropna(subset=["p_evasao"]).sort_values("receita_em_risco", ascending=False)
st.caption(f"{len(v):,} clientes ameaçados com risco estimado".replace(",", ".") +
           (f"; {sem_p} não elegíveis à evasão (sem p_evasao) ficam fora." if sem_p else "."))

corte_valor = comum.scores().query("faixa_valor == 'alto'").score_valor_brl.min()
pts = alt.Chart(v.assign(ameaca=v.principal.map(comum.TIPOS))).mark_circle(size=28, opacity=0.6).encode(
    x=alt.X("p_evasao:Q", title="Risco (p_evasao)", scale=alt.Scale(domain=[0, 1])),
    y=alt.Y("score_valor_brl:Q", title="Valor (score, R$, escala log)", scale=alt.Scale(type="log")),
    color=alt.Color("ameaca:N", title="Ameaça principal", scale=alt.Scale(
        domain=list(comum.TIPOS.values()), range=["#b5543a", "#6b7b8c", "#c9a227"])),
    tooltip=["cliente_id", "tipos", "rota", alt.Tooltip("score_valor_brl:Q", format=",.0f"),
             alt.Tooltip("p_evasao:Q", format=".2f"), alt.Tooltip("receita_em_risco:Q", format=",.0f")])
linhas = (alt.Chart().mark_rule(strokeDash=[4, 4], color="gray").encode(x=alt.datum(0.35))
          + alt.Chart().mark_rule(strokeDash=[4, 4], color="gray").encode(y=alt.datum(corte_valor)))
rotulos = alt.Chart().mark_text(align="right", color="gray", fontWeight="bold").encode(
    x=alt.datum(0.99), y=alt.datum(v.score_valor_brl.max() if len(v) else 1),
    text=alt.datum("Agir já: alto valor, risco alto"))
st.altair_chart((pts + linhas + rotulos).properties(height=380), width="stretch")
st.caption(f"Linhas: risco alto a partir de 0,35; alto valor a partir de {comum.brl(corte_valor)} de score "
           "(decil 2). Quadrante superior direito = prioridade.")
st.dataframe(
    v[["cliente_id", "tipos", "rota", "faixa_valor", "score_valor_brl", "clv_previsto_6m_brl", "p_evasao",
       "receita_em_risco"]],
    hide_index=True, height=300,
    column_config={
        "cliente_id": "Cliente", "tipos": "Ameaças", "rota": "Rota", "faixa_valor": "Valor",
        "score_valor_brl": st.column_config.NumberColumn("Score (R$)", format="%.0f"),
        "clv_previsto_6m_brl": st.column_config.NumberColumn("CLV 6m (R$)", format="%.0f"),
        "p_evasao": st.column_config.NumberColumn("p_evasao", format="%.2f"),
        "receita_em_risco": st.column_config.NumberColumn("Receita em risco (R$)", format="%.0f",
                                                          help="p_evasao x CLV de 6 meses")})

st.subheader("Agir")
ids = v.cliente_id.tolist()
rotulo = v.set_index("cliente_id").apply(
    lambda x: f"{x.name} · {x.tipos} · {x.rota} · risco {comum.brl(x.receita_em_risco)}", axis=1).to_dict()
cid = st.selectbox("Cliente (ordenado por receita em risco; digite para buscar)", ids, format_func=rotulo.get,
                   key="radar_cliente")
if st.button("Agir", type="primary", disabled=cid is None):
    st.session_state["radar_decisao"] = nba_agent.decidir(cid)
dec = st.session_state.get("radar_decisao")
if dec and dec["cliente_id"] == cid:
    comum.painel_decisao(dec, "radar")
