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

c = st.columns(5)
c[0].metric("Score de valor", comum.brl(sc["score_valor_brl"]), f"decil {sc['decil_score']}", delta_color="off")
c[1].metric("p_evasao", "não elegível" if sc["p_evasao"] is None else f"{sc['p_evasao']:.2f}")
c[2].metric("CLV 6m", comum.brl(sc["clv_previsto_6m_brl"]))
c[3].metric("Persona", sc["persona"])
c[4].metric("Nível 2026", perfil["nivel_vigente"],
            None if perfil["folga_pct_2025"] is None else f"folga {perfil['folga_pct_2025']:.0%} em 2025",
            delta_color="off")
st.markdown("**Top 3 motivos de risco (SHAP)**")
st.markdown(comum.md("\n".join(f"{i}. {m}" for i, m in enumerate(sc["motivos"], 1)))
            or "_Sem motivos (não elegível)._")
st.caption(f"Consentimento de marketing: {'sim' if perfil['consentimento_marketing'] else 'não'} · "
           f"2026 até o corte: {perfil['trechos_2026']} trechos e "
           + f"{perfil['pontos_2026']:,} pontos qualificáveis".replace(",", "."))

if st.button("Gerar próxima melhor ação", type="primary"):
    st.session_state["c360_decisao"] = nba_agent.decidir(cid)
dec = st.session_state.get("c360_decisao")
if dec and dec["cliente_id"] == cid:
    comum.painel_decisao(dec, "c360")

e, d = st.columns(2)
with e:
    st.subheader("Ameaças no histórico")
    am = tools._tabela(tools.SILVER, "synthetic_customer_threats").query("cliente_id == @cid")
    am = am.assign(tipo=am.tipo_ameaca.map(comum.TIPOS)).sort_values("data_ameaca", ascending=False)
    st.dataframe(am[["data_ameaca", "tipo", "detalhe", "par_rota"]], hide_index=True,
                 column_config={"data_ameaca": "Data", "tipo": "Tipo", "detalhe": "Detalhe", "par_rota": "Rota"})
with d:
    st.subheader("Viagens no histórico")
    vg = tools._tabela(tools.SILVER, "synthetic_viagens").query("cliente_id == @cid").sort_values(
        "data_voo", ascending=False)
    st.dataframe(vg[["data_voo", "origem_icao", "destino_icao", "tarifa_brl", "atraso_partida_min", "cancelado"]],
                 hide_index=True, column_config={
                     "data_voo": "Data", "origem_icao": "Origem", "destino_icao": "Destino",
                     "tarifa_brl": st.column_config.NumberColumn("Tarifa (R$)", format="%.0f"),
                     "atraso_partida_min": "Atraso (min)", "cancelado": "Cancelado"})
