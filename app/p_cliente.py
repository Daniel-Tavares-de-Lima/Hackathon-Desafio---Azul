import streamlit as st

import comum
import nba_agent
import tools

st.title("Cliente 360")
st.caption(f"Visão em {comum.CORTE_TXT}, base sintética. Histórico até o corte.")

cid = st.text_input("Id do cliente", comum.DEMO_NIVEL, key="c360_id").strip()
perfil, sc = tools.get_customer_profile(cid), tools.get_scores_and_reasons(cid)
if perfil is None or sc is None:
    st.error("Cliente não encontrado.")
    st.stop()

c = st.columns(3)
c[0].metric("Score de valor", comum.brl(sc["score_valor_brl"]), nba_agent.faixa_decil(int(sc["decil_score"])),
            delta_color="off", delta_arrow="off")
c[1].metric("Risco de evasão", "não elegível" if sc["p_evasao"] is None else comum.num(sc["p_evasao"], 2))
c[2].metric("Valor previsto (6 meses)", comum.brl(sc["clv_previsto_6m_brl"]))
folga = "" if perfil["folga_pct_2025"] is None else f" (folga de {comum.num(100 * perfil['folga_pct_2025'])}% em 2025)"
st.markdown(f"**Persona:** {sc['persona']} · **Nível 2026:** {perfil['nivel_vigente']}{folga}")
st.markdown("**Por que este cliente está em risco**")
st.markdown(comum.md("\n".join(f"{i}. {m}" for i, m in enumerate(sc["motivos"], 1)))
            or "_Sem motivos (não elegível)._")
st.caption(f"Consentimento de marketing: {'sim' if perfil['consentimento_marketing'] else 'não'} · "
           f"2026 até o corte: {perfil['trechos_2026']} trechos e {comum.num(perfil['pontos_2026'])} pontos qualificáveis")

if st.button("Gerar próxima melhor ação", type="primary"):
    st.session_state["c360_decisao"] = nba_agent.decidir(cid)
dec = st.session_state.get("c360_decisao")
if dec and dec["cliente_id"] == cid:
    comum.painel_decisao(dec, "c360")

e, d = st.columns(2)
with e:
    st.subheader("Ameaças no histórico")
    am = tools._tabela(tools.SILVER, "synthetic_customer_threats").query("cliente_id == @cid")
    am = am.assign(tipo=am.tipo_ameaca.map(comum.TIPOS), detalhe=am.detalhe.map(comum.DETALHES).fillna(am.detalhe),
                   par_rota=am.par_rota.map(nba_agent.rota)).sort_values("data_ameaca", ascending=False)
    st.dataframe(am[["data_ameaca", "tipo", "detalhe", "par_rota"]], hide_index=True,
                 column_config={"data_ameaca": "Data", "tipo": "Tipo", "detalhe": "Detalhe", "par_rota": "Rota"})
with d:
    st.subheader("Viagens no histórico")
    vg = tools._tabela(tools.SILVER, "synthetic_viagens").query("cliente_id == @cid").sort_values(
        "data_voo", ascending=False)
    vg = vg.assign(origem=vg.origem_icao.map(nba_agent.cidade), destino=vg.destino_icao.map(nba_agent.cidade))
    st.dataframe(comum.tabela_br(vg[["data_voo", "origem", "destino", "tarifa_brl", "atraso_partida_min",
                                     "cancelado"]], {"tarifa_brl": 0}),
                 hide_index=True, column_config={
                     "data_voo": "Data", "origem": "Origem", "destino": "Destino", "tarifa_brl": "Tarifa (R$)",
                     "atraso_partida_min": "Atraso (min)", "cancelado": "Cancelado"})
