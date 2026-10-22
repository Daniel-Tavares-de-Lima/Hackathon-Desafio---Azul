import altair as alt
import streamlit as st

import comum
import nba_agent

st.title("Radar de ameaças")
st.caption(f"Visão em {comum.CORTE_TXT}, base sintética. Janelas até o corte: A nos últimos 90 dias, B e C nos "
           "últimos 180 dias (as mesmas que o agente usa).")

saidas, reducoes = comum.rotas_b()
with st.container(border=True):
    st.markdown(f"**Rotas · set/2025–ago/2026 (ANAC VRA):** {comum.num(saidas)} pares em que a Azul saiu · "
                f"{comum.num(reducoes)} em que reduziu a oferta")

r = comum.radar()
t = comum.ameacas_recentes()
alto = set(comum.scores().query("faixa_valor == 'alto'").cliente_id)


def contador(col, titulo, mask, ajuda):
    ids = set(t.loc[mask, "cliente_id"])
    col.metric(titulo, comum.num(len(ids)), f"{comum.num(len(ids & alto))} de alto valor", delta_color="off",
               delta_arrow="off", help=ajuda)


c1, c2, c3 = st.columns(3)
contador(c1, comum.TIPOS["A"], t.tipo_ameaca == "A", "Clientes com dois atrasos graves (atraso ou cancelamento) "
                                                     "em 90 dias")
contador(c2, comum.TIPOS["B"] + " (saída + redução)", t.tipo_ameaca == "B",
         f"Saída total: {comum.num(t[t.detalhe == 'saida_total'].cliente_id.nunique())} · redução: "
         f"{comum.num(t[t.detalhe == 'reducao'].cliente_id.nunique())} clientes")
contador(c3, comum.TIPOS["C"], t.tipo_ameaca == "C", "Queda de tarifa de concorrente no par que o cliente voa")

f1, f2 = st.columns([3, 1])
tipos = f1.multiselect("Tipo de ameaça", list(comum.TIPOS), default=list(comum.TIPOS), format_func=comum.TIPOS.get)
so_alto = f2.checkbox("Só alto valor (20% de maior valor)")
v = r[r.tipos.apply(lambda x: any(k in x for k in tipos))]
if so_alto:
    v = v[v.faixa_valor == "alto"]
sem_p = v.p_evasao.isna().sum()
v = v.dropna(subset=["p_evasao"]).sort_values("receita_em_risco", ascending=False)
v = v.assign(valor=v.faixa_valor.map(comum.FAIXAS), ameaca=v.principal.map(comum.TIPOS),
             score_txt=v.score_valor_brl.map(comum.brl), risco_txt=v.p_evasao.map(lambda x: comum.num(x, 2)),
             em_risco_txt=v.receita_em_risco.map(comum.brl))
st.caption(f"{comum.num(len(v))} clientes ameaçados com risco estimado" +
           (f"; {comum.num(sem_p)} não elegíveis à evasão (sem risco estimado) ficam fora." if sem_p else "."))

corte_valor = comum.scores().query("faixa_valor == 'alto'").score_valor_brl.min()
pts = alt.Chart(v).mark_circle(size=28, opacity=0.6).encode(
    x=alt.X("p_evasao:Q", axis=comum.eixo_br("Risco de evasão", ".1f", values=[i / 10 for i in range(11)]), scale=alt.Scale(domain=[0, 1])),
    y=alt.Y("score_valor_brl:Q", axis=comum.eixo_br("Valor (score, R$, escala log)"), scale=alt.Scale(type="log")),
    color=alt.Color("ameaca:N", legend=alt.Legend(title="Ameaça principal", labelLimit=300), scale=alt.Scale(
        domain=list(comum.TIPOS.values()), range=["#b5543a", "#6b7b8c", "#c9a227"])),
    tooltip=[alt.Tooltip("cliente_id", title="Cliente"), alt.Tooltip("tipos", title="Ameaças"),
             alt.Tooltip("rota", title="Rota"), alt.Tooltip("score_txt", title="Score"),
             alt.Tooltip("risco_txt", title="Risco de evasão"), alt.Tooltip("em_risco_txt", title="Receita em risco")])
linhas = (alt.Chart().mark_rule(strokeDash=[4, 4], color="gray").encode(x=alt.datum(0.35))
          + alt.Chart().mark_rule(strokeDash=[4, 4], color="gray").encode(y=alt.datum(corte_valor)))
rotulos = alt.Chart().mark_text(align="right", color="gray", fontWeight="bold").encode(
    x=alt.datum(0.99), y=alt.datum(v.score_valor_brl.max() if len(v) else 1),
    text=alt.datum("Agir já: alto valor, risco alto"))
st.altair_chart((pts + linhas + rotulos).properties(height=380), width="stretch")
st.caption(f"Linhas: risco alto a partir de 0,35; alto valor a partir de {comum.brl(corte_valor)} de score "
           "(limite dos 20% de maior valor). Quadrante superior direito = prioridade.")
st.dataframe(
    comum.tabela_br(v[["cliente_id", "tipos", "rota", "valor", "score_valor_brl", "clv_previsto_6m_brl",
                       "p_evasao", "receita_em_risco"]],
                    {"score_valor_brl": 0, "clv_previsto_6m_brl": 0, "p_evasao": 2, "receita_em_risco": 0}),
    hide_index=True, height=300,
    column_config={
        "cliente_id": "Cliente", "tipos": "Ameaças", "rota": "Rota", "valor": "Valor",
        "score_valor_brl": "Score (R$)", "clv_previsto_6m_brl": "Valor previsto 6 meses (R$)",
        "p_evasao": "Risco de evasão",
        "receita_em_risco": st.column_config.Column("Receita em risco (R$)",
                                                    help="Risco de evasão × valor previsto (6 meses)")})

st.subheader("Agir")
ids = v.cliente_id.tolist()
rotulo = dict(zip(v.cliente_id, v.cliente_id + " · " + v.tipos + " · " + v.rota + " · risco " + v.em_risco_txt))
cid = st.selectbox("Cliente (ordenado por receita em risco; digite para buscar)", ids, format_func=rotulo.get,
                   key="radar_cliente")
if st.button("Agir", type="primary", disabled=cid is None):
    st.session_state["radar_decisao"] = nba_agent.decidir(cid)
dec = st.session_state.get("radar_decisao")
if dec and dec["cliente_id"] == cid:
    comum.painel_decisao(dec, "radar")
