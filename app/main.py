"""Painel ÓRBITA. Uso: streamlit run app/main.py"""
import streamlit as st

import comum

st.set_page_config(page_title="ÓRBITA · Radar de Ameaças", layout="wide")
pg = st.navigation([
    st.Page("p_radar.py", title="Radar de ameaças", default=True),
    st.Page("p_executiva.py", title="Visão executiva"),
    st.Page("p_personas.py", title="Personas"),
    st.Page("p_cliente.py", title="Cliente 360"),
    st.Page("p_atrito.py", title="Atrito público"),
    st.Page("p_simulador.py", title="Simulador de ROI"),
])
st.sidebar.caption(f"Visão em {comum.CORTE_TXT} (data de corte), base sintética.")
pg.run()
comum.rodape()
