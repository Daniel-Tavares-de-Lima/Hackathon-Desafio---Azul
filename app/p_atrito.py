import altair as alt
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

st.subheader("Temas de reclamação (Consumidor.gov.br)")
EMPRESAS = {"AZU": "Azul", "GLO": "Gol", "TAM": "LATAM"}
temas_gold = tools.GOLD / "friction_themes" / "data.parquet"
if not temas_gold.exists():
    st.caption("Sem gold.friction_themes: rode `python -I pipelines/ingest_consumidor.py` (P-18).")
    st.stop()

ft = pd.read_parquet(temas_gold)
DEC = ["nota_media", "pct_resolvidas", "pct_insatisfeitos", "pct_respondidas", "tempo_resposta_medio_dias"]
ft = ft[ft.empresa.isin(EMPRESAS)].astype({c: float for c in DEC}).assign(companhia=lambda d: d.empresa.map(EMPRESAS))
ult, fim = sorted(ft.ano_mes.unique())[-6], ft.ano_mes.max()
st.caption(f"Reclamações públicas do Consumidor.gov.br (Senacon), agregadas; dados abertos da ANAC, licença "
           f"Creative Commons Attribution (cc-by). Série {ft.ano_mes.min()} a {fim}: a ANAC ainda não publicou 2026; "
           f"a janela VRA vai até 2026-08 (corte do modelo em {tools.MES_CORTE}). Sem citações: a fonte não publica "
           "texto livre. Só quem reclama aparece (viés de seleção); o tema vem do problema escolhido pelo consumidor "
           "(de/para em P-18; \"canais de venda/app\" = dificuldade de contratar ou acessar os canais de venda).")

emp = st.radio("Companhia", list(EMPRESAS.values()), horizontal=True)
d = ft[ft.companhia == emp]
st.altair_chart(alt.Chart(d).mark_line(point=True).encode(
    x=alt.X("ano_mes:O", title="Mês de abertura"), y=alt.Y("reclamacoes:Q", title="Reclamações"),
    color=alt.Color("tema:N", title="Tema"),
    tooltip=["ano_mes", "tema", "reclamacoes", "nota_media", "pct_resolvidas"]).properties(height=320),
    width="stretch")

st.markdown(f"**Satisfação por tema, {ult} a {fim}** (nota média 1 a 5 de quem avaliou; % resolvidas na visão do "
            "consumidor, entre as avaliadas)")
r = ft[ft.ano_mes >= ult].assign(soma_nota=lambda x: x.nota_media.fillna(0) * x.avaliadas,
                                 soma_res=lambda x: x.pct_resolvidas.fillna(0) * x.avaliadas)
r = r.groupby(["tema", "companhia"])[["reclamacoes", "avaliadas", "soma_nota", "soma_res"]].sum()
base = r.avaliadas.where(r.avaliadas > 0)  # avaliada = tem nota = Resolvida ou Não Resolvida (mesma base)
r["nota_media"], r["pct_resolvidas"] = r.soma_nota / base, r.soma_res / base
tab = r.nota_media.unstack("companhia").round(2).add_prefix("Nota ")
tab = tab.join(r.pct_resolvidas.unstack("companhia").round(1).add_prefix("% resolvidas "))
tab = tab.join(r.reclamacoes.unstack("companhia").add_prefix("Reclamações "))
st.dataframe(tab.reset_index(), hide_index=True)

st.markdown("**Ponte: tema atraso/cancelamento ↔ rotas com atraso (gold VRA)**")
vra = tools._tabela(tools.GOLD, "route_disruptions")
vra = vra.assign(empresa=vra.empresa_icao.replace({"ACN": "AZU"}))  # P-15
vra = vra[vra.empresa.isin(EMPRESAS) & (vra.ano_mes >= ft.ano_mes.min()) & (vra.ano_mes <= fim)]
v = vra.groupby(["empresa", "ano_mes"])[["voos_previstos", "voos_realizados", "voos_atraso_30", "voos_cancelados"]].sum()
a = ft[ft.tema == "atraso/cancelamento"].set_index(["empresa", "ano_mes"]).reclamacoes
p = v.join(a, how="inner").reset_index()
p["companhia"] = p.empresa.map(EMPRESAS)
p["reclamacoes_por_10k_voos"] = 1e4 * p.reclamacoes / p.voos_previstos
p["pct_atraso_30"] = 100 * p.voos_atraso_30 / p.voos_realizados
p["pct_cancelado"] = 100 * p.voos_cancelados / p.voos_previstos
st.altair_chart(alt.Chart(p).mark_line(point=True).encode(
    x=alt.X("ano_mes:O", title="Mês"), y=alt.Y("reclamacoes_por_10k_voos:Q",
                                              title="Reclamações de atraso/cancelamento por 10 mil voos"),
    color=alt.Color("companhia:N", title="Companhia"),
    tooltip=["companhia", "ano_mes", alt.Tooltip("reclamacoes_por_10k_voos:Q", format=".1f"),
             alt.Tooltip("pct_atraso_30:Q", format=".1f"), alt.Tooltip("pct_cancelado:Q", format=".1f")])
    .properties(height=280), width="stretch")
az = p[p.empresa == "AZU"]
def br(x):
    return f"{x:.2f}".replace(".", ",")


st.caption(f"Azul, {az.ano_mes.min()} a {az.ano_mes.max()} (n = {len(az)} meses): correlação mensal entre reclamações "
           f"de atraso/cancelamento e % de voos com atraso > 30 min = {br(az.reclamacoes.corr(az.pct_atraso_30))}; "
           f"com % cancelado = {br(az.reclamacoes.corr(az.pct_cancelado))}. Descritivo, no nível da companhia "
           "(a reclamação não traz rota). Denominador = voos previstos do VRA **doméstico** (P-02); as reclamações "
           "incluem voos internacionais, o que infla mais a LATAM (no arquivo, ~22% das reclamações dela têm um "
           "código não documentado que parece \"internacional\", contra ~11% da Azul e ~4% da Gol; não filtrado por "
           "falta de dicionário oficial, P-18). A ameaça A do radar continua vindo só do VRA; nada aqui toca cliente "
           "sintético.")
