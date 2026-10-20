"""Ferramentas do agente NBA: leem só saídas prontas (gold, silver do histórico e KB). Nada aqui decide ação.

Fontes lidas: gold.customer_scores, gold.route_exits, gold.route_disruptions, silver.synthetic_clientes,
silver.synthetic_fidelidade e silver.synthetic_customer_threats (só o HISTÓRICO, mês <= 2026-02).
Nunca lidas: synthetic_customer_threats_rotulo, synthetic_alvos, synthetic_viagens_futuro, archetypes.
Premissas dos números (efeito, custo, teto, valor do ponto): docs/PREMISSAS.md, P-17.
"""
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "data" / "gold"
SILVER = ROOT / "data" / "silver"
KB_DIR = Path(__file__).resolve().parent / "kb"

DATA_CORTE = pd.Timestamp("2026-02-28")
MES_CORTE = "2026-02"
JANELA_A_DIAS = 90       # ameaça A recente (mesma janela de 90 dias da regra A grave, P-12)
JANELA_BC_DIAS = 180     # B e C nos últimos 6 meses (mesma janela das features de ameaça, P-16)
HUBS = ["SBKP", "SBCF", "SBRF"]  # hubs da Azul (P-08)
GRUPO_AZUL = {"AZU", "ACN"}      # P-15
# Colunas que o agente nunca recebe (fairness/LGPD). A região só existe para o relatório de fairness (P-16).
SENSIVEIS = {"regiao_origem"}

# --- P-17: premissas de produto (calibração própria, sem fonte pública) ---
VALOR_PONTO_BRL = 0.02   # custo de 1 ponto Azul Fidelidade para a Azul
CUSTO_CONTATO_HUMANO = 20.0
CUSTO_CONTATO_DIGITAL = 1.0
TETO_PCT_CLV = 0.05      # teto de custo por cliente = 5% do CLV de 6 meses ...
TETO_ABS_BRL = 500.0     # ... limitado a R$ 500 (fora o custo do contato)
CATALOGO = {
    # acao: (efeito suposto = redução relativa de p_evasao, % do CLV gasto em pontos, contato humano?)
    "recuperacao_servico": (0.25, 0.03, True),
    "oferta_rota_favorita": (0.20, 0.02, False),
    "bonus_pontos": (0.10, 0.015, False),
    "upgrade": (0.12, 0.02, False),
    "desafio_manutencao_nivel": (0.20, 0.02, False),
    "contato_humano": (0.10, 0.0, True),
}
# Benefícios que cada ação promete; cada um precisa de trecho na KB válido para o nível do cliente.
# O crédito de pontos de cortesia NÃO está aqui: não tem regra pública, sai em `decisao_comercial` (P-17).
# Contato humano de rota órfã não promete benefício (a regra ANAC de reacomodação trata de atraso, não de saída).
BENEFICIOS_ACAO = {
    "recuperacao_servico": ["assistencia_material", "reacomodacao"],
    "oferta_rota_favorita": ["bonus_pontos_nivel"],
    "bonus_pontos": ["bonus_pontos_nivel"],
    "upgrade": ["upgrade_desconto"],
    "desafio_manutencao_nivel": ["desafio_manutencao"],
    "contato_humano": [],
}


def beneficios_texto(acao: str) -> set[str]:
    """Benefícios que o texto da ação pode citar: os da KB mais o crédito de pontos (decisão comercial), se houver."""
    return set(BENEFICIOS_ACAO.get(acao, [])) | ({"credito_pontos"} if CATALOGO.get(acao, (0, 0))[1] > 0 else set())
LIMIARES = {  # P-11 (igual à KB, ver LACUNAS.md para a divergência de pontos por real)
    "Topázio": {"trechos": 6, "pontos": 6000, "gasto": None, "e": False},
    "Safira": {"trechos": 10, "pontos": 10000, "gasto": None, "e": False},
    "Diamante": {"trechos": 12, "pontos": 12000, "gasto": 25000, "e": True},
    "Diamante Unique": {"trechos": 26, "pontos": 26000, "gasto": 50000, "e": True},
}


@lru_cache(maxsize=None)
def _tabela(camada: Path, nome: str) -> pd.DataFrame:
    return pd.read_parquet(camada / nome / "data.parquet")


def _linha(df, cliente_id):
    r = df[df.cliente_id == cliente_id]
    return None if r.empty else r.iloc[0].to_dict()


def get_customer_profile(cliente_id: str) -> dict | None:
    """Casa, consentimento LGPD e posição no programa (2025 completo e 2026 até o corte)."""
    cli = _linha(_tabela(SILVER, "synthetic_clientes"), cliente_id)
    if cli is None:
        return None
    fid = _tabela(SILVER, "synthetic_fidelidade")
    f = fid[fid.cliente_id == cliente_id].set_index("ano")
    f25, f26 = f.loc[2025], f.loc[2026]
    folga = f25.folga_pct_nivel_alcancado
    return {
        "cliente_id": cliente_id,
        "aeroporto_casa": cli["aeroporto_casa"],
        "consentimento_marketing": bool(cli["consentimento_marketing"]),
        "nivel_vigente": f26.nivel_vigente,
        "nivel_alcancado_2025": f25.nivel_alcancado,
        "folga_pct_2025": None if pd.isna(folga) else float(folga),
        "trechos_2026": int(f26.trechos),
        "pontos_2026": int(f26.pontos_qualificaveis),
        "gasto_2026_brl": float(f26.gasto_aereo_brl),
    }


def get_scores_and_reasons(cliente_id: str) -> dict | None:
    """Score, p_evasao, CLV, persona e motivos SHAP. Remove colunas sensíveis antes de entregar ao agente."""
    s = _linha(_tabela(GOLD, "customer_scores"), cliente_id)
    if s is None:
        return None
    out = {k: v for k, v in s.items() if k not in SENSIVEIS and k != "data_corte"}
    out["p_evasao"] = None if pd.isna(out["p_evasao"]) else float(out["p_evasao"])
    out["motivos"] = [m for m in (out.pop("motivo_1"), out.pop("motivo_2"), out.pop("motivo_3")) if isinstance(m, str)]
    return out


def get_threats(cliente_id: str) -> list[dict]:
    """Ameaças do histórico (synthetic_customer_threats), mais recente primeiro, dentro das janelas A/B/C."""
    t = _tabela(SILVER, "synthetic_customer_threats")
    t = t[t.cliente_id == cliente_id].copy()
    t["data_ameaca"] = pd.to_datetime(t["data_ameaca"])
    dias = (DATA_CORTE - t["data_ameaca"]).dt.days
    t = t[(dias >= 0) & (((t.tipo_ameaca == "A") & (dias <= JANELA_A_DIAS))
                         | ((t.tipo_ameaca != "A") & (dias <= JANELA_BC_DIAS)))]
    t = t.assign(dias_desde=dias).sort_values("data_ameaca", ascending=False)
    cols = ["tipo_ameaca", "detalhe", "par_rota", "data_ameaca", "dias_desde", "origem_icao", "destino_icao"]
    return [{**r, "data_ameaca": r["data_ameaca"].date().isoformat()} for r in t[cols].to_dict("records")]


def _sentido(par_rota: str, casa: str) -> tuple[str, str]:
    a, b = par_rota.split("-")
    return (b, a) if casa == b else (a, b)


def get_route_friction(par_rota: str) -> dict:
    """Atraso > 30 min e cancelamento do grupo Azul no par, nos 3 meses até o corte (gold.route_disruptions)."""
    d = _tabela(GOLD, "route_disruptions")
    a, b = par_rota.split("-")
    d = d[d.empresa_icao.isin(GRUPO_AZUL) & (d.ano_mes > "2025-11") & (d.ano_mes <= MES_CORTE)
          & (((d.origem_icao == a) & (d.destino_icao == b)) | ((d.origem_icao == b) & (d.destino_icao == a)))]
    real, prev = d.voos_realizados.sum(), d.voos_previstos.sum()
    if prev == 0:
        return {"par_rota": par_rota, "voos_previstos_3m": 0, "pct_atraso_30": None, "pct_cancelado": None}
    return {"par_rota": par_rota, "voos_previstos_3m": int(prev),
            "pct_atraso_30": round(100 * d.voos_atraso_30.sum() / real, 1) if real else None,
            "pct_cancelado": round(100 * d.voos_cancelados.sum() / prev, 1)}


def get_network_alternative(par_rota: str, casa: str) -> dict:
    """Alternativa pela malha no mês do corte (gold.route_exits, grupo Azul): voo direto restante e conexão via hub."""
    e = _tabela(GOLD, "route_exits")
    m = e[e.ano_mes == MES_CORTE].set_index(["origem_icao", "destino_icao"]).voos_azul
    o, dst = _sentido(par_rota, casa)
    direto = int(m.get((o, dst), 0))
    melhor = None
    for h in HUBS:
        if h in (o, dst):
            continue
        n = min(int(m.get((o, h), 0)), int(m.get((h, dst), 0)))
        if n > 0 and (melhor is None or n > melhor[1]):
            melhor = (h, n)
    return {"origem": o, "destino": dst, "voos_diretos_mes": direto,
            "hub": melhor[0] if melhor else None, "voos_conexao_mes": melhor[1] if melhor else 0}


def faltam_para_manter(nivel: str, trechos: int, pontos: int, gasto: float) -> dict | None:
    """Quanto falta em 2026 para repetir o nível de 2025 (regras P-11 / KB criterios_niveis_2026).

    P-11: o nível de 2025 vale até o fim de 2026; a meta de 2026 garante o nível em 2027. `cumprido` = algum caminho
    da regra já foi atingido (OU: trechos ou pontos; E: trechos e pontos, ou o gasto).
    """
    r = LIMIARES.get(nivel)
    if r is None:
        return None
    ft, fp = max(r["trechos"] - trechos, 0), max(r["pontos"] - pontos, 0)
    fg = max(r["gasto"] - gasto, 0) if r["gasto"] else None
    cumprido = (ft == 0 and fp == 0) or fg == 0 if r["e"] else (ft == 0 or fp == 0)
    return {"nivel": nivel, "faltam_trechos": ft, "faltam_pontos": fp, "faltam_gasto_brl": fg,
            "regra": "trechos E pontos, ou gasto" if r["e"] else "trechos OU pontos", "e": r["e"],
            "cumprido": cumprido}


def get_offer_catalog() -> dict:
    return {a: {"efeito_suposto": e, "pct_clv_pontos": p, "contato_humano": h,
                "beneficios": BENEFICIOS_ACAO[a], "credito_pontos_comercial": p > 0}
            for a, (e, p, h) in CATALOGO.items()}


def teto_custo(clv: float) -> float:
    """Teto proporcional ao valor: 5% do CLV de 6 meses, até R$ 500, mais o custo do contato humano."""
    return min(TETO_PCT_CLV * clv, TETO_ABS_BRL) + CUSTO_CONTATO_HUMANO


def estimate_offer_roi(acao: str, p_evasao: float, clv: float) -> dict:
    """ROI = p_evasao x CLV x efeito suposto - custo. Custo = pontos (% do CLV, com teto) + contato."""
    efeito, pct, humano = CATALOGO[acao]
    custo_pontos = min(pct * clv, TETO_PCT_CLV * clv, TETO_ABS_BRL)
    custo = custo_pontos + (CUSTO_CONTATO_HUMANO if humano else CUSTO_CONTATO_DIGITAL)
    pontos = int(round(custo_pontos / VALOR_PONTO_BRL, -2))
    return {"custo_estimado": round(custo, 2), "pontos": pontos, "custo_pontos": round(custo_pontos, 2),
            "roi_estimado": round(p_evasao * clv * efeito - custo, 2), "efeito_suposto": efeito}


# ------------------------------- KB + RAG (TF-IDF, sem embeddings) -------------------------------
@lru_cache(maxsize=1)
def carregar_kb() -> list[dict]:
    """Cada seção `## id` dos .md da KB vira um trecho com url, benefícios, níveis e resumo. LACUNAS.md fica fora."""
    trechos = []
    for arq in sorted(KB_DIR.glob("*.md")):
        if arq.name == "LACUNAS.md":
            continue
        for bloco in re.split(r"^## ", arq.read_text(encoding="utf-8"), flags=re.M)[1:]:
            linhas = bloco.splitlines()
            campos = dict(re.match(r"- (\w+): (.*)", l).groups() for l in linhas[1:] if re.match(r"- \w+: ", l))
            trechos.append({
                "id": linhas[0].strip(), "arquivo": arq.name, "url": campos["url"], "trecho": campos["trecho"],
                "fonte": campos["fonte"], "status": campos["status"], "coletado_em": campos["coletado_em"],
                "beneficios": {b.strip() for b in campos["beneficios"].split(",")} - {"nenhum"},
                "niveis": {n.strip() for n in campos["niveis"].split(",")},
            })
    return trechos


@lru_cache(maxsize=1)
def _indice():
    kb = carregar_kb()
    vet = TfidfVectorizer(strip_accents="unicode", lowercase=True)
    return vet, vet.fit_transform([f"{t['id'].replace('_', ' ')} {t['trecho']}" for t in kb])


def buscar_kb(consulta: str, k: int = 3, filtro=None) -> list[dict]:
    """Top-k trechos por similaridade TF-IDF (cosseno; vetores já normalizados), com filtro opcional."""
    kb = carregar_kb()
    vet, mat = _indice()
    sims = (mat @ vet.transform([consulta]).T).toarray().ravel()
    ordem = [i for i in sims.argsort()[::-1] if filtro is None or filtro(kb[i])]
    return [{**kb[i], "similaridade": round(float(sims[i]), 3)} for i in ordem[:k]]
