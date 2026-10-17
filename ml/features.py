"""Features observáveis por cliente num corte qualquer, só com dados até o corte.

Lê synthetic_clientes, synthetic_viagens, synthetic_customer_threats e gold.route_exits (observabilidade da
saída total). Features nunca leem alvos, viagens_futuro, ameaças de rótulo nem arquétipo; synthetic_alvos só é lido
como rótulo do corte de teste (alvos_oficiais, base).
Também monta o rótulo de um corte anterior a partir de synthetic_viagens (mesma definição de P-13).

Uso: python -I ml/features.py   (autoteste: corte 2026-02-28 bate com synthetic_elegibilidade)
"""
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SILVER = ROOT / "data" / "silver"
GOLD = ROOT / "data" / "gold"
INICIO = pd.Timestamp("2024-09-01")          # início do histórico sintético (P-06)
CORTE_TESTE = pd.Timestamp("2026-02-28")
CORTE_TREINO = pd.Timestamp("2025-08-31")
SEED = 20261017

# Regras de nível (P-11); pontos = 0,5 x gasto (taxa média do gerador, sem o ruído por cliente)
NIVEIS = ["Sem nível", "Topázio", "Safira", "Diamante", "Diamante Unique"]

# UF -> região (IBGE)
REGIAO_UF = {
    **dict.fromkeys(["AC", "AM", "AP", "PA", "RO", "RR", "TO"], "Norte"),
    **dict.fromkeys(["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"], "Nordeste"),
    **dict.fromkeys(["DF", "GO", "MS", "MT"], "Centro-Oeste"),
    **dict.fromkeys(["ES", "MG", "RJ", "SP"], "Sudeste"),
    **dict.fromkeys(["PR", "RS", "SC"], "Sul"),
}
UF_FALTANTE = {"SBFC": "SP"}  # Franca-SP: sem descrição no VRA da janela (P-16)

# Features que entram nos modelos. Contagens acumuladas (trechos_hist) ficam de fora porque o histórico tem 12 meses
# no corte de treino e 18 no de teste; tudo aqui é taxa ou janela fixa (6m, 12m, 90d).
# Região fica de fora de propósito: só para fairness (P-16).
MODELO = [
    "recencia_dias", "taxa_mensal", "trechos_6m", "trechos_12m", "razao_tendencia",
    "gasto_12m", "tarifa_media", "antecedencia_mediana", "n_pares", "share_rota_fav",
    "eventos_graves_90d", "cancelados_12m", "pct_atraso30_12m",
    "nivel_12m", "folga_pct_nivel", "falta_pct_proximo",
    "a_6m", "dias_desde_a", "b_saida_fav_6m", "b_reducao_fav_6m", "c_queda_fav_6m", "dias_desde_bc",
]


def _ler(nome):
    df = pd.read_parquet(SILVER / nome / "data.parquet")
    for c in ["data_voo", "data_ameaca"]:  # DATE do Parquet chega como datetime.date
        if c in df:
            df[c] = pd.to_datetime(df[c])
    return df


def meses_hist(corte):
    return (corte.year - INICIO.year) * 12 + corte.month - INICIO.month + 1


def regiao_por_aeroporto():
    """ICAO -> UF -> região, pela descrição do aeroporto publicada no VRA ('... - CIDADE - UF - BRASIL')."""
    src = (SILVER / "anac_vra").as_posix()
    df = duckdb.sql(f"""
        SELECT origem_icao AS icao, mode(split_part(origem_descricao, ' - ', -2)) AS uf
        FROM read_parquet('{src}/**/*.parquet', hive_partitioning=true)
        WHERE origem_descricao LIKE '% - BRASIL' GROUP BY 1""").df()
    uf = dict(zip(df.icao, df.uf)) | UF_FALTANTE
    return {k: REGIAO_UF.get(v) for k, v in uf.items()}


def _nivel(trechos, gasto):
    """Nível (0..4), folga sobre o limite do nível e falta para o próximo, no caminho mais favorável (P-11)."""
    t, g = np.asarray(trechos, float), np.asarray(gasto, float)
    p = 0.5 * g
    # razão valor/limite de cada caminho por nível (caminho E = mínimo das razões)
    caminhos = [
        np.maximum(t / 6, p / 6000),
        np.maximum(t / 10, p / 10000),
        np.maximum(np.minimum(t / 12, p / 12000), g / 25000),
        np.maximum(np.minimum(t / 26, p / 26000), g / 50000),
    ]
    r = np.column_stack(caminhos)
    nivel = ((r >= 1) * np.arange(1, 5)).max(axis=1)  # maior nível cujo limite foi atingido
    folga = np.where(nivel > 0, r[np.arange(len(t)), np.maximum(nivel - 1, 0)] - 1, np.nan)
    falta = np.where(nivel < 4, 1 - np.clip(r[np.arange(len(t)), np.minimum(nivel, 3)], 0, 1), np.nan)
    return nivel, folga, falta


def _primeiro_mes_saida():
    """par_rota, mes_saida -> 1º mês com saida_total marcada na gold (quando a ameaça fica observável)."""
    df = pd.read_parquet(GOLD / "route_exits" / "data.parquet", columns=["ano_mes", "par_rota", "saida_total", "mes_saida"])
    df = df[df.saida_total].groupby(["par_rota", "mes_saida"], as_index=False).ano_mes.min()
    return df.rename(columns={"ano_mes": "mes_flag"})


def montar_features(corte):
    """DataFrame indexado por cliente_id com as features no corte (todas as datas usadas <= corte)."""
    corte = pd.Timestamp(corte)
    cli = _ler("synthetic_clientes").set_index("cliente_id")
    v = _ler("synthetic_viagens")
    v = v[v.data_voo <= corte]
    assert v.data_voo.max() <= corte
    voado = v[~v.cancelado]
    n_meses = meses_hist(corte)
    d6, d12, d90 = corte - pd.DateOffset(months=6), corte - pd.DateOffset(months=12), corte - pd.Timedelta(days=90)

    f = pd.DataFrame(index=cli.index)
    g = voado.groupby("cliente_id")
    f["recencia_dias"] = (corte - g.data_voo.max()).dt.days
    f["trechos_hist"] = g.size()
    f["trechos_6m"] = voado[voado.data_voo > d6].groupby("cliente_id").size()
    f["trechos_12m"] = voado[voado.data_voo > d12].groupby("cliente_id").size()
    f["gasto_12m"] = voado[voado.data_voo > d12].groupby("cliente_id").tarifa_brl.sum()
    f["tarifa_media"] = g.tarifa_brl.mean()
    f["antecedencia_mediana"] = voado[voado.sentido == "ida"].groupby("cliente_id").antecedencia_dias.median()
    f["n_pares"] = voado[voado.data_voo > d12].groupby("cliente_id").par_rota.nunique()
    por_par = voado.groupby(["cliente_id", "par_rota"]).size().rename("n").reset_index()
    fav = por_par.sort_values(["cliente_id", "n", "par_rota"], ascending=[True, False, True]).drop_duplicates("cliente_id")
    fav = fav.set_index("cliente_id")
    for c in ["trechos_hist", "trechos_6m", "trechos_12m", "gasto_12m", "n_pares"]:
        f[c] = f[c].fillna(0)
    f["share_rota_fav"] = (fav.n / f.trechos_hist).reindex(f.index)
    f["taxa_mensal"] = f.trechos_hist / n_meses
    # Tendência: taxa/mês nos últimos 6 meses vs taxa/mês nos até 12 meses anteriores disponíveis
    # (12 no corte de teste, 6 no de treino). Sem trechos antes: razão 1 (neutro), como no gerador (P-13).
    taxa_ant = (f.trechos_hist - f.trechos_6m) / min(12, n_meses - 6)
    f["razao_tendencia"] = np.where(taxa_ant > 0, (f.trechos_6m / 6) / taxa_ant.where(taxa_ant > 0), 1.0)
    f["razao_tendencia"] = f.razao_tendencia.clip(upper=3)

    grave = v[v.cancelado | (v.atraso_partida_min > 60)]
    f["eventos_graves_90d"] = grave[grave.data_voo > d90].groupby("cliente_id").size()
    v12 = v[v.data_voo > d12]
    f["cancelados_12m"] = v12[v12.cancelado].groupby("cliente_id").size()
    f["pct_atraso30_12m"] = (v12.atraso_partida_min > 30).groupby(v12.cliente_id).mean()
    for c in ["eventos_graves_90d", "cancelados_12m"]:
        f[c] = f[c].fillna(0)

    f["nivel_12m"], f["folga_pct_nivel"], f["falta_pct_proximo"] = _nivel(f.trechos_12m, f.gasto_12m)

    # Ameaças observáveis até o corte; B e C contam só na rota favorita (par com mais trechos), últimos 6 meses
    a = _ler("synthetic_customer_threats")
    a = a[a.data_ameaca <= corte]
    obs = a.merge(_primeiro_mes_saida(), how="left", left_on=["par_rota", "ano_mes"], right_on=["par_rota", "mes_saida"])
    saida = obs.detalhe == "saida_total"
    assert obs.loc[saida, "mes_flag"].notna().all()
    a = obs[~saida | (obs.mes_flag <= corte.strftime("%Y-%m"))]
    assert a.data_ameaca.max() <= corte
    a = a.assign(fav=a.par_rota.values == fav.par_rota.reindex(a.cliente_id).values)
    a6 = a[a.data_ameaca > d6]
    f["a_6m"] = a6[a6.tipo_ameaca == "A"].groupby("cliente_id").size()
    a12 = a[a.data_ameaca > d12]  # recência só nos últimos 12 meses (janela comum aos dois cortes); vazio = sem ameaça
    f["dias_desde_a"] = (corte - a12[a12.tipo_ameaca == "A"].groupby("cliente_id").data_ameaca.max()).dt.days
    for col, det in [("b_saida_fav_6m", "saida_total"), ("b_reducao_fav_6m", "reducao"), ("c_queda_fav_6m", "queda_tarifa")]:
        f[col] = a6[a6.fav & (a6.detalhe == det)].groupby("cliente_id").size()
    bc = a12[a12.fav & a12.tipo_ameaca.isin(["B", "C"])]
    f["dias_desde_bc"] = (corte - bc.groupby("cliente_id").data_ameaca.max()).dt.days
    for c in ["a_6m", "b_saida_fav_6m", "b_reducao_fav_6m", "c_queda_fav_6m"]:
        f[c] = f[c].fillna(0)

    f["regiao_origem"] = cli.aeroporto_casa.map(regiao_por_aeroporto())
    assert f.regiao_origem.notna().all(), "aeroporto de casa sem região"
    f["trechos_esperados_6m"] = f.taxa_mensal * 6
    f["elegivel_evasao"] = f.trechos_esperados_6m >= 3
    return f


def rotulo_no_corte(corte):
    """Rótulo dos 6 meses após o corte, a partir de synthetic_viagens (só para cortes com 6 meses de histórico à frente).
    Mesma definição de P-13: evasão = trechos voados <= 30% do esperado; CLV = soma das tarifas voadas."""
    corte = pd.Timestamp(corte)
    fim = corte + pd.DateOffset(months=6)
    assert fim <= CORTE_TESTE, "o rótulo de treino não pode entrar no período de rótulo oficial"
    v = _ler("synthetic_viagens")
    v = v[(v.data_voo > corte) & (v.data_voo <= fim) & ~v.cancelado]
    g = v.groupby("cliente_id")
    return pd.DataFrame({"trechos_futuros_6m": g.size(), "clv_futuro_6m_brl": g.tarifa_brl.sum()})


def alvos_oficiais():
    return _ler("synthetic_alvos").set_index("cliente_id")


def base(corte):
    """Features + rótulo para o corte (treino: rótulo recalculado; teste: synthetic_alvos)."""
    f = montar_features(corte)
    if pd.Timestamp(corte) == CORTE_TESTE:
        y = alvos_oficiais()[["evasao", "clv_futuro_6m_brl"]]
    else:
        y = rotulo_no_corte(corte).reindex(f.index).fillna(0)
        y["evasao"] = np.where(f.elegivel_evasao, (y.trechos_futuros_6m <= 0.3 * f.trechos_esperados_6m).astype(float), np.nan)
    return f.join(y[["evasao", "clv_futuro_6m_brl"]])


if __name__ == "__main__":
    f = montar_features(CORTE_TESTE)
    el = _ler("synthetic_elegibilidade").set_index("cliente_id").reindex(f.index)
    assert (f.elegivel_evasao == el.elegivel_evasao).all()
    assert np.allclose(f.trechos_esperados_6m, el.trechos_esperados_6m, atol=0.005)  # tabela arredonda em 2 casas
    nivel, folga, falta = _nivel([6, 9, 12, 0], [1000, 30000, 30000, 0])
    assert list(nivel) == [1, 3, 3, 0] and folga[0] == 0 and np.isnan(folga[3])
    t = base(CORTE_TREINO)
    print(f"ok: {len(f)} clientes, {int(f.elegivel_evasao.sum())} elegíveis no teste; "
          f"treino {int(t.elegivel_evasao.sum())} elegíveis, evasão {t.evasao.mean():.4f}")
