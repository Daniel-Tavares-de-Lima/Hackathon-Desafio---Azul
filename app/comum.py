"""Dados em cache e o painel de decisão do agente, compartilhados pelas páginas do app.

Lê só gold, silver do histórico e ml/resultados. Nunca lê synthetic_alvos, synthetic_viagens_futuro,
synthetic_customer_threats_rotulo nem synthetic_archetypes_validacao.
"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

APP = Path(__file__).resolve().parent
ROOT = APP.parent
sys.path[:0] = [str(APP), str(ROOT / "agent")]
import guardrails  # noqa: E402
import nba_agent  # noqa: E402
import tools  # noqa: E402

LOG_APROVACOES = APP / ".cache" / "aprovacoes.jsonl"
CORTE_TXT = "28/02/2026"
TIPOS = {"A": "A · Atraso grave", "B": "B · Rota órfã", "C": "C · Concorrente baixou tarifa"}
ACOES = {
    "recuperacao_servico": "Recuperação de serviço",
    "oferta_rota_favorita": "Oferta na rota favorita",
    "bonus_pontos": "Bônus de pontos",
    "upgrade": "Upgrade com pontos",
    "desafio_manutencao_nivel": "Desafio de manutenção de nível",
    "contato_humano": "Contato humano",
    "sem_acao_automatica": "Sem ação automática",
}
DETALHES = nba_agent.NOME_GATILHO  # id técnico da ameaça -> nome legível
FAIXAS = nba_agent.NOME_FAIXA
num = nba_agent.br  # número no padrão brasileiro: num(1234.5, 1) -> '1.234,5'
# Eixo Altair no padrão brasileiro: troca o separador de milhar (,) por ponto e o decimal (.) por vírgula.
TROCA_BR = ("replace(replace(replace({x}, regexp(',', 'g'), '_'), regexp('[.]', 'g'), ','), regexp('_', 'g'), '.')")
DEMO_A = "9132e89e-9a62-4c3a-8cb0-51f621090395"
DEMO_NIVEL = "85e407cb-e65a-4be9-a5ab-eb6b99cbecd0"


def brl(v: float) -> str:
    return f"R$ {num(v)}"


def eixo_br(titulo: str, fmt: str = ",.0f", **kw) -> alt.Axis:
    """Eixo com rótulos no padrão brasileiro (format do d3 + troca de separadores no Vega)."""
    return alt.Axis(title=titulo, format=fmt, labelExpr=TROCA_BR.format(x="datum.label"), **kw)


def tabela_br(df: pd.DataFrame, casas: dict):
    """Styler com números no padrão brasileiro. casas = {coluna: nº de casas, ou 'pct' para fração 0-1}.
    A ordenação da tabela continua pelo valor numérico."""
    fmt = {c: (lambda v: "" if pd.isna(v) else f"{num(100 * v, 1)}%") if k == "pct" else
           (lambda v, k=k: "" if pd.isna(v) else num(v, k)) for c, k in casas.items() if c in df}
    return df.style.format(fmt)


@st.cache_data(show_spinner=False)
def scores() -> pd.DataFrame:
    """gold.customer_scores sem a região (só existe para fairness) + receita em risco = p_evasao x CLV."""
    s = tools._tabela(tools.GOLD, "customer_scores").drop(columns=list(tools.SENSIVEIS))
    s = s.assign(receita_em_risco=s.p_evasao * s.clv_previsto_6m_brl)
    s["faixa_valor"] = s.decil_score.map(nba_agent.faixa_valor)
    return s


@st.cache_data(show_spinner=False)
def rotas_b() -> tuple[int, int]:
    """Pares (não direcionais) de gold.route_exits em set/2025–ago/2026 (docs/ROTEIRO_PITCH.md): saída = saida_total
    com mes_saida na janela; redução = reducao na janela, fora dos pares com saída total em algum mês da janela."""
    e = tools._tabela(tools.GOLD, "route_exits")
    w = e[(e.ano_mes >= "2025-09") & (e.ano_mes <= "2026-08")]
    saida = w[w.saida_total & (w.mes_saida >= "2025-09") & (w.mes_saida <= "2026-08")].par_rota.nunique()
    reducao = len(set(w[w.reducao].par_rota) - set(w[w.saida_total].par_rota))
    return int(saida), int(reducao)


@st.cache_data(show_spinner=False)
def ameacas_recentes() -> pd.DataFrame:
    """Ameaças do histórico nas mesmas janelas do agente: A nos últimos 90 dias, B e C nos últimos 180 até o corte."""
    t = tools._tabela(tools.SILVER, "synthetic_customer_threats").copy()
    t["data_ameaca"] = pd.to_datetime(t["data_ameaca"])
    dias = (tools.DATA_CORTE - t["data_ameaca"]).dt.days
    janela = (t.tipo_ameaca == "A") & (dias <= tools.JANELA_A_DIAS) | (t.tipo_ameaca != "A") & (dias <= tools.JANELA_BC_DIAS)
    return t[janela & (dias >= 0)]


@st.cache_data(show_spinner=False)
def radar() -> pd.DataFrame:
    """Um cliente por linha: tipos de ameaça recentes, rota da ameaça mais recente, score, CLV e risco."""
    t = ameacas_recentes().sort_values("data_ameaca", ascending=False)
    por_cli = t.groupby("cliente_id").agg(
        tipos=("tipo_ameaca", lambda x: "".join(sorted(set(x)))),
        rota=("par_rota", "first"), ultima=("data_ameaca", "first")).reset_index()
    por_cli["principal"] = por_cli.tipos.str[0]  # prioridade A > B > C, a mesma do agente
    por_cli["rota"] = por_cli.rota.map({r: nba_agent.rota(r) for r in por_cli.rota.unique()})  # cidades (VRA)
    return por_cli.merge(scores(), on="cliente_id")


@st.cache_data(show_spinner=False)
def lote_nba() -> pd.DataFrame:
    """Decisões do agente em lote (app/lote.py). Gera o arquivo se faltar (~1 minuto)."""
    import lote
    if lote.defasado():  # score, código do agente ou KB mais novos que o cache
        with st.spinner("Atualizando as recomendações em lote (~1 min)...", show_time=True):
            subprocess.run([sys.executable, "-I", str(APP / "lote.py")], check=True)
    return pd.read_parquet(lote.SAIDA).merge(scores(), on="cliente_id")


@st.cache_data(show_spinner=False)
def csv_ml(nome: str) -> pd.DataFrame:
    return pd.read_csv(ROOT / "ml" / "resultados" / f"{nome}.csv")


def rodape():
    st.divider()
    st.caption("Dados sintéticos e públicos (ANAC). Nenhum dado real de cliente.")


def _registrar(dec: dict, mensagem: str, status: str):
    LOG_APROVACOES.parent.mkdir(exist_ok=True)
    reg = {"quando": datetime.now().isoformat(timespec="seconds"), "status": status, "cliente_id": dec["cliente_id"],
           "acao": dec["acao"], "custo_estimado": dec["custo_estimado"], "mensagem": mensagem}
    with LOG_APROVACOES.open("a", encoding="utf-8") as f:
        f.write(json.dumps(reg, ensure_ascii=False) + "\n")
    st.session_state.setdefault("aprovacoes", []).append(reg)


def md(txt: str) -> str:
    """Escapa o cifrão: no markdown do Streamlit, "R$ ... R$" vira fórmula LaTeX."""
    return txt.replace("$", "\\$")


def painel_decisao(dec: dict, chave: str):
    """Mostra a decisão do agente de forma legível. Aprovar/Descartar só registra localmente: nada é enviado."""
    acao = dec["acao"]
    if acao == "sem_acao_automatica":
        st.warning(f"**{ACOES[acao]}.** {md(dec['justificativa'])}")
        return
    st.markdown(f"### Ação recomendada: {ACOES[acao]}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Retorno estimado", brl(dec["roi_estimado"]))
    c2.metric("Custo estimado", brl(dec["custo_estimado"]))
    c3.metric("Canal", "Humano" if dec["canal"] == "atendimento_humano" else "App",
              help="Humano = atendimento por especialista; App = mensagem pelo aplicativo")
    st.markdown(f"**Justificativa.** {md(dec['justificativa'])}")
    st.caption("O retorno usa um efeito suposto (calibração própria, sem experimento). Premissas: docs/PREMISSAS.md, "
               "P-11 (níveis) e P-17 (efeitos, custos e teto).")
    st.markdown("**Regras citadas**")
    for r in dec["regras_citadas"]:
        selo = f" · :orange-badge[{r['status']}]" if r["status"] else ""
        st.markdown(f"- [{r['id']}]({r['url']}){selo}  \n  {md(r['trecho'])}  \n  _Fonte: {md(r['fonte'])}_")
    if not dec["regras_citadas"]:
        st.caption("Nenhuma regra citada: esta ação não promete benefício.")
    dc = dec.get("decisao_comercial")
    if dc:
        st.markdown(f"**Decisão comercial (sem regra pública)**  \n- {dc['item']}: "
                    f"{num(dc['pontos'])} pontos ({md(brl(dc['custo_brl']))}), sujeito à aprovação humana")
    texto = st.text_area("Mensagem ao cliente (editável)", dec["mensagem"], key=f"msg_{chave}", height=120)
    oferta = dec["mensagem_oferta"]
    st.caption("Só a frase de contexto pode ser editada. A oferta (números, pontos, prazos e condições) precisa ficar "
               "intacta; para mudá-la, descarte e gere a ação de novo.")
    # Edição manual pelo aprovador: oferta intacta e, no resto, sem número, valor, benefício ou promessa.
    erros = guardrails.checar_mensagem_editada(texto, dec["mensagem"][: -len(oferta)].strip(), oferta)
    if erros:
        st.error("Guardrail: " + "; ".join(erros) + ". Ajuste o texto antes de aprovar.")
    botoes = st.container(horizontal=True)
    if botoes.button("Aprovar", key=f"aprovar_{chave}", type="primary", disabled=bool(erros)):
        _registrar(dec, texto, "aprovada")
        st.success("Aprovada e registrada no log local (app/.cache/aprovacoes.jsonl). Nada foi enviado ao cliente.")
    if botoes.button("Descartar", key=f"descartar_{chave}"):
        _registrar(dec, texto, "descartada")
        st.info("Descartada e registrada no log local.")
    with st.expander("JSON completo do agente"):
        st.json(dec)
