import pandas as pd
import streamlit as st

import comum
import tools

MIN_VOOS = 90  # par com pelo menos ~1 voo/dia previsto nos 3 meses, para o % não ser ruído

st.title("Atrito público")
st.caption(f"Visão em {comum.CORTE_TXT}. Voos do grupo Azul nos 3 meses até o corte (dez/2025 a fev/2026), "
           "dados públicos ANAC VRA (gold.route_disruptions).")


@st.cache_data(show_spinner=False)
def rotas() -> pd.DataFrame:
    d = tools._tabela(tools.GOLD, "route_disruptions")
    d = d[d.empresa_icao.isin(tools.GRUPO_AZUL) & (d.ano_mes > "2025-11") & (d.ano_mes <= tools.MES_CORTE)]
    d = d.assign(par_rota=["-".join(sorted(p)) for p in zip(d.origem_icao, d.destino_icao)])
    g = d.groupby("par_rota")[["voos_previstos", "voos_realizados", "voos_cancelados", "voos_atraso_30"]].sum()
    g = g[g.voos_previstos >= MIN_VOOS]
    g["pct_atraso_30"] = 100 * g.voos_atraso_30 / g.voos_realizados
    g["pct_cancelado"] = 100 * g.voos_cancelados / g.voos_previstos
    alto = set(comum.scores().query("faixa_valor == 'alto'").cliente_id)
    vg = tools._tabela(tools.SILVER, "synthetic_viagens")
    vg = vg[(vg.ano_mes > "2025-11") & (vg.ano_mes <= tools.MES_CORTE) & vg.cliente_id.isin(alto)]
    a = comum.ameacas_recentes().query("tipo_ameaca == 'A'")
    g["alto_valor_voaram"] = vg.groupby("par_rota").cliente_id.nunique()
    g["alto_valor_com_A"] = a[a.cliente_id.isin(alto)].groupby("par_rota").cliente_id.nunique()
    return g.fillna({"alto_valor_voaram": 0, "alto_valor_com_A": 0}).reset_index()


g = rotas()
ordem = st.radio("Ordenar por", ["% atraso > 30 min", "% cancelado"], horizontal=True)
g = g.sort_values("pct_atraso_30" if ordem.startswith("% atraso") else "pct_cancelado", ascending=False)
st.dataframe(g.head(20)[["par_rota", "voos_previstos", "pct_atraso_30", "pct_cancelado", "alto_valor_voaram",
                         "alto_valor_com_A"]], hide_index=True, column_config={
    "par_rota": "Rota", "voos_previstos": "Voos previstos (3m)",
    "pct_atraso_30": st.column_config.NumberColumn("% atraso > 30 min", format="%.1f"),
    "pct_cancelado": st.column_config.NumberColumn("% cancelado", format="%.1f"),
    "alto_valor_voaram": st.column_config.NumberColumn("Alto valor que voou (3m)", format="%d"),
    "alto_valor_com_A": st.column_config.NumberColumn("Alto valor com ameaça A (90d)", format="%d")})
st.caption(f"Só pares com pelo menos {MIN_VOOS} voos previstos no período. Alto valor = decis 1 e 2 do score; "
           "clientes e viagens são sintéticos.")

st.subheader("Temas de reclamação (reviews públicos)")
reviews = tools.GOLD / "review_atritos" / "data.parquet"
if reviews.exists():
    st.dataframe(pd.read_parquet(reviews), hide_index=True)
else:
    st.caption("Em construção: a análise de sentimento dos reviews públicos ainda não gerou gold.review_atritos.")
