"""Gemeo digital da base de clientes: 50 mil clientes ficticios, viagens, nivel de fidelidade, ameacas e rotulos.

Uso: python -I -X utf8 pipelines/synthetic/generate.py
Entradas : data/silver/anac_{tarifas,vra} e data/gold/route_{disruptions,exits,competition} (so leitura).
Saidas   : data/silver/synthetic_*/data.parquet e docs/VALIDACAO_SINTETICO.md.
Premissas: docs/PREMISSAS.md (P-06 em diante). Tudo e sintetico por construcao: o gerador devolve as regras
que ele mesmo usa (circularidade, ver P-06).
Janela: indice de mes 0 = 2024-09 ... 17 = 2026-02 (historico, 18 meses); 18 = 2026-03 ... 23 = 2026-08 (rotulo).
"""
import math
import os
import sys
import time
import uuid
import warnings
from pathlib import Path
from statistics import NormalDist

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SILVER = ROOT / os.environ.get("SILVER_DIR", "data/silver")
GOLD = ROOT / os.environ.get("GOLD_DIR", "data/gold")

SEED = 20261017
N = 50_000
NM = 24                      # meses da janela ANAC
T_HIST = 18                  # meses 0..17 = historico; 18..23 = rotulo
CORTE = np.datetime64("2026-02-28")
MESES = [f"{2024 + (8 + i) // 12}-{(8 + i) % 12 + 1:02d}" for i in range(NM)]
INICIO_MES = np.array([np.datetime64(m + "-01") for m in MESES], dtype="datetime64[D]")
DIAS_MES = np.append(np.diff(INICIO_MES).astype(int), 31)
FIM_JANELA = np.datetime64("2026-08-31")

# ---- premissas (cada uma documentada em docs/PREMISSAS.md, P-06 a P-14) ----
ARQ = ["corporativo_frequente", "lazer_premium", "regional_dependente", "em_ascensao", "ocasional"]
MIX = np.array([0.08, 0.10, 0.18, 0.15, 0.49])
LAMBDA_MEDIA = np.array([1.0, 0.30, 0.50, 0.30, 0.12])   # eventos (ida e volta) por mes
GAMMA_FORMA = 1.5                                         # heterogeneidade: taxa individual ~ Gamma(forma, media/forma)
WARM = 4                                                  # meses de compra anteriores a 2024-09 (aquecimento)
SAZ_MAX = 3.0                                             # teto do indice sazonal da rota
RAMPA_ASCENSAO = (0.5, 0.08)                              # multiplicador da taxa: 0,5 + 0,08 * mes
PROB_IDA_VOLTA = 0.90
ESTADIA = [(1, 1.5), (3, 5.0), (2, 3.0), (2, 3.0), (2, 4.0)]  # dias: minimo + Poisson(media)
ANTEC_MEDIANA = np.array([7, 45, 14, 20, 25])             # dias de antecedencia (lognormal)
ANTEC_SIGMA = np.array([0.7, 0.6, 0.7, 0.7, 0.8])
RHO_ANTEC_PRECO = -0.30                                   # correlacao gaussiana antecedencia x quantil da tarifa
K_FAV_PROB = [np.array(p) for p in ([.6, .3, .1], [.2, .3, .5], [1, 0, 0], [.4, .4, .2], [.6, .3, .1])]  # n de rotas favoritas (1..3) por arquetipo
PESO_FAV = np.array([0.6, 0.3, 0.1])
EXPOENTE_TARIFA_FAV = np.array([0.0, 1.0, 0.0, 0.0, 0.0])  # lazer premium prefere rotas de tarifa mais alta
PROB_REACOMODA = 0.60                                     # favorita indisponivel: remarca para outro destino
P_CONSENTIMENTO = 0.70
TAXA_PONTOS = 0.5                                         # pontos qualificaveis por R$ de gasto aereo
SIGMA_PONTOS_CLIENTE, SIGMA_PONTOS_ANO = 0.10, 0.08
# evasao: logit(p) = intercepto do arquetipo + efeitos + ruido (P-12)
INTERCEPTO = np.array([-2.6, -2.0, -2.3, -2.8, -1.3])
EF = dict(atraso=0.20, cancelamento=0.35, saida=0.60, reducao=0.25, queda=0.45, nivel=0.35, volume=0.10, ruido=0.6)
VOLUME_REF = 8.0                                          # trechos em 12 meses que zeram o efeito de volume
FOLGA_PERTO = 0.25                                        # folga < 25% acima do limite = perto de perder o nivel

NIVEIS = ["Sem nível", "Topázio", "Safira", "Diamante", "Diamante Unique"]
# caminhos alternativos (OU); dentro do caminho, todos os requisitos (E): (trechos, pontos, gasto R$)
REGRAS = {1: [(6, None, None), (None, 6000, None)], 2: [(10, None, None), (None, 10000, None)],
          3: [(12, 12000, None), (None, None, 25000)], 4: [(26, 26000, None), (None, None, 50000)]}
ANOS = [(2024, 0, 3, "2024-12-31", False), (2025, 4, 15, "2025-12-31", True), (2026, 16, 17, "2026-02-28", False)]


def uuids(rng, n):
    return [str(uuid.UUID(bytes=rng.bytes(16), version=4)) for _ in range(n)]


def carrega(con):
    """Le fontes em DuckDB e devolve estruturas numpy."""
    for t in ("anac_vra", "anac_tarifas"):
        p = (SILVER / t / "*" / "data.parquet").as_posix()
        con.execute(f"CREATE VIEW {t} AS SELECT * FROM read_parquet('{p}', hive_partitioning=true)")
    for t in ("route_disruptions", "route_exits", "route_competition"):
        p = (GOLD / t / "data.parquet").as_posix()
        con.execute(f"CREATE VIEW {t} AS SELECT * FROM read_parquet('{p}')")
    mi = "(CAST(substr(ano_mes,1,4) AS INT)-2024)*12 + CAST(substr(ano_mes,6,2) AS INT) - 9"
    par = "CASE WHEN origem_icao<destino_icao THEN origem_icao||'-'||destino_icao ELSE destino_icao||'-'||origem_icao END"
    f = {}
    # distribuicao empirica de tarifa da Azul por par x mes (chave = id do grupo + CDF acumulada por assentos)
    g = con.execute(f"""
        WITH b AS (SELECT {par} par, {mi} t, tarifa::DOUBLE tarifa, SUM(assentos) a FROM anac_tarifas
                   WHERE empresa_icao='AZU' GROUP BY ALL)
        SELECT dense_rank() OVER (ORDER BY par)-1 pid, t, tarifa,
               SUM(a) OVER (PARTITION BY par, t ORDER BY tarifa) * 1.0 / SUM(a) OVER (PARTITION BY par, t) cdf, par
        FROM b ORDER BY pid, t, tarifa""").df()
    f["par_nomes"] = g.drop_duplicates("pid").sort_values("pid")["par"].to_numpy()
    f["pid_de"] = {p: i for i, p in enumerate(f["par_nomes"])}
    gid = g["pid"].to_numpy() * NM + g["t"].to_numpy()
    ult = np.append(gid[1:] != gid[:-1], True)
    cdf = np.where(ult, 1.0, g["cdf"].to_numpy())
    f["chave"] = g["pid"].to_numpy() * NM + g["t"].to_numpy() + cdf
    f["tarifa"] = g["tarifa"].to_numpy()
    P = len(f["par_nomes"])
    tem = np.zeros((P, NM), bool)
    tem[g["pid"].to_numpy(), g["t"].to_numpy()] = True
    f["tem"] = tem
    # saida total por par: mes da saida (indice), a partir daqui a Azul nao voa mais
    ex = con.execute(f"SELECT par_rota, {mi.replace('ano_mes', 'mes_saida')} ms FROM route_exits WHERE saida_total AND mes_saida IS NOT NULL GROUP BY ALL").df()
    ex["pid"] = ex["par_rota"].map(f["pid_de"])
    f["saidas"] = ex.dropna(subset=["pid"]).astype({"pid": int})[["pid", "ms"]]
    saida_t = np.full(P, 99)
    for p_, m_ in f["saidas"].itertuples(index=False):
        saida_t[p_] = min(saida_t[p_], m_)
    f["saida_t"] = saida_t
    f["avail"] = tem & (np.arange(NM)[None, :] < saida_t[:, None])
    for nome, tab, col in (("reducao", "route_exits", "reducao"), ("queda", "route_competition", "queda_tarifa")):
        d = con.execute(f"SELECT par_rota, {mi} m FROM {tab} WHERE {col} GROUP BY ALL").df()
        d["pid"] = d["par_rota"].map(f["pid_de"])
        f[nome] = d.dropna(subset=["pid"]).astype({"pid": int})[["pid", "m"]]
    # pesos de destino por origem x mes (assentos da Azul por rota direcional)
    dr = con.execute(f"""SELECT origem_icao o, destino_icao d, {par} par, {mi} t, SUM(assentos)::DOUBLE s, SUM(assentos*tarifa)::DOUBLE fs
                         FROM anac_tarifas WHERE empresa_icao='AZU' GROUP BY ALL""").df()
    aer = sorted(set(dr["o"]) | set(dr["d"]))
    f["aer"] = np.array(aer)
    aidx = {a: i for i, a in enumerate(aer)}
    homes = sorted(set(dr["o"]))
    hidx = {a: i for i, a in enumerate(homes)}
    pares = dr[["o", "d"]].drop_duplicates().sort_values(["o", "d"])
    pares["slot"] = pares.groupby("o").cumcount()
    dr = dr.merge(pares, on=["o", "d"])
    H, D = len(homes), int(pares["slot"].max()) + 1
    h = dr["o"].map(hidx).to_numpy(); sl = dr["slot"].to_numpy(); t = dr["t"].to_numpy()
    W = np.zeros((H, NM, D)); W[h, t, sl] = dr["s"].to_numpy()
    ftot = np.zeros((H, D)); stot = np.zeros((H, D))
    np.add.at(ftot, (h, sl), dr["fs"].to_numpy()); np.add.at(stot, (h, sl), dr["s"].to_numpy())
    dest_pid = np.zeros((H, D), int); dest_air = np.zeros((H, D), int)
    pp = dr.drop_duplicates(["o", "d"])
    dest_pid[pp["o"].map(hidx), pp["slot"]] = pp["par"].map(f["pid_de"])
    dest_air[pp["o"].map(hidx), pp["slot"]] = pp["d"].map(aidx)
    W *= (np.arange(NM)[None, :, None] < saida_t[dest_pid][:, None, :])       # par sem Azul apos a saida total
    f.update(homes=np.array(homes), home_air=np.array([aidx[a] for a in homes]), W=W, dest_pid=dest_pid,
             dest_air=dest_air, tarifa_media_slot=np.where(stot > 0, ftot / np.maximum(stot, 1), 0.0))
    vo = con.execute("""SELECT origem_icao, COUNT(*) FROM anac_vra WHERE empresa_icao='AZU' AND tipo_linha='N' AND codigo_di='0'
                        AND situacao_voo IN ('REALIZADO','CANCELADO') AND ano_mes <= '2026-02' GROUP BY 1""").df()
    vo = vo.set_index("origem_icao")["count_star()"]
    f["voos_origem"] = vo
    f["peso_home"] = np.array([float(vo.get(a, 0)) for a in homes])
    # taxas de cancelamento e atraso > 30 por rota direcional x mes (Azul)
    A = len(aer)
    rc = np.full((A, A, NM), np.nan, np.float32); rl = rc.copy()
    d = con.execute(f"SELECT origem_icao o, destino_icao d, {mi} t, pct_cancelado/100 c, pct_atraso_30/100 l FROM route_disruptions WHERE empresa_icao='AZU'").df()
    d = d[d["o"].isin(aidx) & d["d"].isin(aidx)]
    io, idd, it = d["o"].map(aidx).to_numpy(), d["d"].map(aidx).to_numpy(), d["t"].to_numpy()
    rc[io, idd, it] = d["c"].astype(float).to_numpy(); rl[io, idd, it] = d["l"].astype(float).to_numpy()
    glob = con.execute(f"""SELECT {mi} t, SUM(voos_cancelados)*1.0/SUM(voos_previstos) c, SUM(voos_atraso_30)*1.0/SUM(voos_realizados) l
                           FROM route_disruptions WHERE empresa_icao='AZU' GROUP BY 1 ORDER BY 1""").df()
    for arr, col in ((rc, "c"), (rl, "l")):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            media_rota = np.nanmean(arr, axis=2)
        arr[:] = np.where(np.isnan(arr), media_rota[:, :, None], arr)
        arr[:] = np.where(np.isnan(arr), glob[col].to_numpy()[None, None, :], arr)
    f["rc"], f["rl"] = rc, rl
    q = np.linspace(0.0025, 0.9975, 200)
    for nome, cond in (("atraso_tarde", "> 30"), ("atraso_ok", "<= 30")):
        r = con.execute(f"""SELECT quantile_cont(atraso_partida_min, {q.tolist()}) FROM anac_vra WHERE empresa_icao='AZU'
                            AND tipo_linha='N' AND codigo_di='0' AND situacao_voo='REALIZADO' AND atraso_partida_min {cond}""").fetchone()[0]
        f[nome] = np.array(r, float)
    f["q"] = q
    return f


def sorteia_cdf(cdf_flat, grupo, u):
    """Sorteia indice de coluna em linhas com CDF normalizada (ultima coluna = 1) via chave grupo+cdf."""
    return np.searchsorted(cdf_flat, grupo + u)


def gera_viagens(f, rng, arq, home, lam):
    """Eventos de COMPRA (ida e volta) por Poisson; destino por favoritas x sazonalidade de vendas da Azul;
    tarifa pela CDF empirica do par no MES DA COMPRA (a ANAC publica por mes de venda); voo = compra + antecedencia."""
    W = f["W"]; H, _, D = W.shape
    tp = np.arange(-WARM, NM); tpe = np.maximum(tp, 0)           # meses de compra; aquecimento usa os dados do mes 0
    ini_c = (np.datetime64("2024-09", "M") + tp).astype("datetime64[D]")
    dias_c = ((np.datetime64("2024-09", "M") + (tp + 1)).astype("datetime64[D]") - ini_c).astype(int)
    sea = W.sum((0, 2)); sea = sea / sea.mean()                  # sazonalidade da rede (usada so se nenhuma favorita vende no mes)
    # favoritas: ate 3 destinos da casa, sorteados pelo total de assentos (com vies de tarifa p/ lazer premium)
    wtot = W.sum(1)
    favs = np.zeros((N, 3), int)
    for a in range(len(ARQ)):
        w = wtot * np.where(f["tarifa_media_slot"] > 0, (f["tarifa_media_slot"] / 694.4) ** EXPOENTE_TARIFA_FAV[a], 0.0)
        cdf = np.cumsum(w, 1); cdf = cdf / cdf[:, -1:]
        flat = (np.arange(H)[:, None] + cdf).ravel()
        m = np.where(arq == a)[0]
        favs[m] = sorteia_cdf(flat, home[m, None], rng.random((len(m), 3))) - home[m, None] * D
    kfav = np.zeros(N, int)
    for a in range(len(ARQ)):
        m = np.where(arq == a)[0]
        kfav[m] = rng.choice(3, len(m), p=K_FAV_PROB[a]) + 1
    # sazonalidade por rota favorita: assentos da Azul vendidos no mes da compra / media mensal da rota (teto SAZ_MAX);
    # a taxa de compra do cliente no mes e a media das favoritas ponderada por PESO_FAV
    media = W.mean(1)
    pf = PESO_FAV[None, :] * (np.arange(3)[None, :] < kfav[:, None]); pf = pf / pf.sum(1, keepdims=True)
    S = np.minimum(W[home[:, None, None], tpe[None, None, :], favs[:, :, None]] / np.maximum(media[home[:, None], favs], 1e-9)[:, :, None], SAZ_MAX)
    s_ef = (pf[:, :, None] * S).sum(1)
    r = np.where(s_ef > 0, s_ef, sea[tpe][None, :])               # sem favorita vendendo: demanda segue a rede (remarcacao/perda abaixo)
    r[arq == 3] *= np.maximum(RAMPA_ASCENSAO[0] + RAMPA_ASCENSAO[1] * tp, 0.1)
    cont = rng.poisson(lam[:, None] * r)
    ev_c = np.repeat(np.arange(N), cont.sum(1))
    ev_i = np.repeat(np.tile(np.arange(len(tp)), N), cont.ravel())   # indice do mes de compra (0 = WARM meses antes de 2024-09)
    ev_tpe = tpe[ev_i]
    E = len(ev_c)
    e_h = home[ev_c]
    pj = PESO_FAV[None, :] * (np.arange(3)[None, :] < kfav[ev_c][:, None]) * S[ev_c, :, ev_i]
    tot = pj.sum(1)
    jsel = np.minimum((rng.random(E)[:, None] * tot[:, None] > np.cumsum(pj, 1)).sum(1), 2)
    slot = favs[ev_c, jsel]
    ok = tot > 0
    # favorita indisponivel (ex.: Azul saiu do par): remarca com prob. PROB_REACOMODA, senao viagem perdida
    cdfm = np.cumsum(W, 2); soma = cdfm[:, :, -1]
    cdfm = np.where(soma[:, :, None] > 0, cdfm / np.where(soma > 0, soma, 1)[:, :, None], 1.0)
    flatm = (np.arange(H * NM).reshape(H, NM)[:, :, None] + cdfm).ravel()
    reac = ~ok & (rng.random(E) < PROB_REACOMODA)
    g_ = (e_h * NM + ev_tpe)[reac]
    slot[reac] = np.minimum(sorteia_cdf(flatm, g_, rng.random(reac.sum())) - g_ * D, D - 1)
    ok = W[e_h, ev_tpe, slot] > 0
    perdidas = int((~ok).sum())
    ev_c, ev_i, ev_tpe, e_h, slot = ev_c[ok], ev_i[ok], ev_tpe[ok], e_h[ok], slot[ok]
    E = len(ev_c); a_ev = arq[ev_c]
    antec = np.clip(np.floor(ANTEC_MEDIANA[a_ev] * np.exp(ANTEC_SIGMA[a_ev] * rng.standard_normal(E))), 0, 330).astype(int)
    estadia = np.array([ESTADIA[a][0] for a in range(5)])[a_ev] + rng.poisson(np.array([ESTADIA[a][1] for a in range(5)])[a_ev])
    data_compra = ini_c[ev_i] + (rng.random(E) * dias_c[ev_i]).astype(int)
    data_ida = data_compra + antec
    data_volta = data_ida + estadia
    pid = f["dest_pid"][e_h, slot]
    o_air, d_air = f["home_air"][e_h], f["dest_air"][e_h, slot]
    mes_voo = lambda d: (d.astype("datetime64[M]") - np.datetime64("2024-09")).astype(int)
    t_ida, t_volta = mes_voo(data_ida), mes_voo(data_volta)
    dentro = (data_ida >= INICIO_MES[0]) & (data_ida <= FIM_JANELA) & (t_ida < f["saida_t"][pid])   # voo fora da janela ou depois da saida da Azul
    fora_janela = int((~dentro).sum())
    tem_volta = dentro & (rng.random(E) < PROB_IDA_VOLTA) & (data_volta <= FIM_JANELA) & (t_volta < f["saida_t"][pid])
    pernas = []
    for sentido, m, dt, tt, o_, d_, ant in (
            (0, dentro, data_ida, t_ida, o_air, d_air, antec),
            (1, tem_volta, data_volta, t_volta, d_air, o_air, antec + estadia)):
        pernas.append(pd.DataFrame(dict(c=ev_c[m], sentido=sentido, data=dt[m], t=tt[m], tpe=ev_tpe[m], o=o_[m], d=d_[m], pid=pid[m], antec=ant[m])))
    L = pd.concat(pernas, ignore_index=True)
    n = len(L)
    # tarifa: quantil da CDF empirica do par no mes da compra; antecedencia longa => quantil menor (copula gaussiana, marginal uniforme)
    nd = NormalDist()
    rk = np.empty(n); rk[np.argsort(np.log1p(L["antec"].to_numpy()) + 1e-6 * rng.random(n), kind="stable")] = (np.arange(n) + 0.5) / n
    z = np.array([nd.inv_cdf(x) for x in rk])
    x = RHO_ANTEC_PRECO * z + math.sqrt(1 - RHO_ANTEC_PRECO ** 2) * rng.standard_normal(n)
    u = np.clip(0.5 * np.array([math.erfc(-v / math.sqrt(2)) for v in x]), 1e-9, 1 - 1e-9)
    pidv, tv_ = L["pid"].to_numpy(), L["t"].to_numpy()
    L["tarifa"] = np.round(f["tarifa"][np.minimum(np.searchsorted(f["chave"], pidv * NM + L["tpe"].to_numpy() + u), len(f["tarifa"]) - 1)], 2)
    # atrito: cancelamento e atraso > 30 sorteados da taxa real da rota no mes do voo (VRA)
    o_, d_ = L["o"].to_numpy(), L["d"].to_numpy()
    canc = rng.random(n) < f["rc"][o_, d_, tv_]
    tarde = ~canc & (rng.random(n) < f["rl"][o_, d_, tv_])
    uu = rng.random(n)
    atraso = np.where(tarde, np.interp(uu, f["q"], f["atraso_tarde"]), np.interp(uu, f["q"], f["atraso_ok"]))
    L["cancelado"] = canc
    L["atraso"] = np.where(canc, np.nan, np.round(atraso))
    return L, perdidas, E, fora_janela


def nivel_e_distancias(trechos, pontos, gasto):
    """Nivel (0-4) pelas regras publicas, folga sobre o limite do nivel e falta para o proximo (caminho mais proximo)."""
    n = len(trechos)
    val = (trechos.astype(float), pontos.astype(float), gasto.astype(float))

    def razao(caminho):   # menor razao valor/limite entre os requisitos do caminho
        r = [val[i] / lim for i, lim in enumerate(caminho) if lim is not None]
        return np.minimum.reduce(r)

    nivel = np.zeros(n, int)
    for lv, caminhos in REGRAS.items():
        nivel = np.where(np.maximum.reduce([razao(c) for c in caminhos]) >= 1, lv, nivel)
    folga = np.full(n, np.nan)
    falta = np.full(n, np.nan); ft = folga.copy(); fp = folga.copy(); fg = folga.copy()
    for lv in range(0, 5):
        m = nivel == lv
        if lv >= 1:
            folga[m] = np.maximum.reduce([razao(c)[m] for c in REGRAS[lv]]) - 1
        if lv < 4:
            cam = REGRAS[lv + 1]
            sf = [1 - np.minimum(razao(c), 1) for c in cam]       # falta normalizada por caminho
            melhor = np.argmin(np.stack(sf), 0)
            falta[m] = np.min(np.stack(sf), 0)[m]
            for k, c in enumerate(cam):
                mk = m & (melhor == k)
                for arr, i in ((ft, 0), (fp, 1), (fg, 2)):
                    if c[i] is not None:
                        arr[mk] = np.maximum(c[i] - val[i][mk], 0)
    return nivel, folga, falta, ft, fp, fg


def fidelidade(Lh, cliente_ids, rng):
    """Uma linha por cliente x ano (calendario) com trechos, gasto, pontos derivados do gasto e nivel."""
    voadas = Lh[~Lh["cancelado"]]
    mult = np.exp(SIGMA_PONTOS_CLIENTE * rng.standard_normal(N))
    linhas, alc_ant = [], None
    for ano, t0, t1, ref, completo in ANOS:
        v = voadas[(voadas["t"] >= t0) & (voadas["t"] <= t1)]
        trechos = np.bincount(v["c"], minlength=N)
        gasto = np.bincount(v["c"], weights=v["tarifa"], minlength=N)
        pontos = np.round(gasto * TAXA_PONTOS * mult * np.exp(SIGMA_PONTOS_ANO * rng.standard_normal(N))).astype(int)
        niv, folga, falta, ft, fp, fg = nivel_e_distancias(trechos, pontos, gasto)
        vig = niv if alc_ant is None else np.maximum(niv, alc_ant)   # P-11: nivel ganho vale ate o fim do ano seguinte
        alc_ant = niv
        linhas.append(pd.DataFrame(dict(
            cliente_id=cliente_ids, ano=ano, referencia_ate=np.datetime64(ref), ano_completo=completo, trechos=trechos,
            gasto_aereo_brl=np.round(gasto, 2), pontos_qualificaveis=pontos, nivel_alcancado=np.array(NIVEIS)[niv],
            nivel_vigente=np.array(NIVEIS)[vig], folga_pct_nivel_alcancado=np.round(folga, 4),
            falta_pct_proximo_nivel=np.round(falta, 4), faltam_trechos_proximo=ft, faltam_pontos_proximo=fp,
            faltam_gasto_proximo_brl=np.round(fg, 2), _niv=niv, _folga=folga)))
    return pd.concat(linhas, ignore_index=True)


def ameacas_bc(lp, f):
    """Ameacas B e C: cliente voou o par nos 12 meses ate o mes da ameaca. Uma linha por cliente x par x episodio."""
    saida = []
    for det, fm in (("reducao", f["reducao"]), ("queda_tarifa", f["queda"])):
        fm = fm.drop_duplicates().sort_values(["pid", "m"]).copy()
        fm["run"] = fm["m"] - fm.groupby("pid").cumcount()
        x = lp[lp["pid"].isin(fm["pid"].unique())].merge(fm, on="pid")
        x = x[(x["m"] - x["t"] >= 0) & (x["m"] - x["t"] <= 11)]
        g = x.groupby(["c", "pid", "run"], as_index=False)["m"].min()
        saida.append(g.assign(tipo="C" if det == "queda_tarifa" else "B", detalhe=det)[["c", "pid", "m", "tipo", "detalhe"]])
    ex = f["saidas"].drop_duplicates()
    x = lp[lp["pid"].isin(ex["pid"].unique())].merge(ex, on="pid")
    x = x[(x["ms"] - x["t"] >= 1) & (x["ms"] - x["t"] <= 12)]
    g = x.groupby(["c", "pid", "ms"], as_index=False).size().rename(columns={"ms": "m"})
    saida.append(g.assign(tipo="B", detalhe="saida_total")[["c", "pid", "m", "tipo", "detalhe"]])
    return pd.concat(saida, ignore_index=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")   # make roda sem -X utf8
    t0 = time.perf_counter()
    rng = np.random.default_rng(SEED)
    con = duckdb.connect()
    f = carrega(con)
    print(f"fontes carregadas em {time.perf_counter() - t0:.1f}s", flush=True)

    # ---- clientes e arquetipos latentes ----
    ids = np.array(uuids(np.random.default_rng([SEED, 1]), N))
    arq = rng.choice(len(ARQ), N, p=MIX)
    home = rng.choice(len(f["homes"]), N, p=f["peso_home"] / f["peso_home"].sum())
    lam = rng.gamma(GAMMA_FORMA, LAMBDA_MEDIA[arq] / GAMMA_FORMA)
    consent = rng.random(N) < P_CONSENTIMENTO

    L, perdidas, n_eventos, fora_janela = gera_viagens(f, rng, arq, home, lam)
    L["tipo_hist"] = L["t"] < T_HIST
    Lh = L[L["tipo_hist"]]
    fid = fidelidade(Lh, ids, rng)

    # ---- evasao: features do historico, ameacas B/C e A nos ultimos 6 meses do historico ----
    voadas_h = Lh[~Lh["cancelado"]]
    viajou = np.bincount(voadas_h["c"], minlength=N) > 0
    legs12 = np.bincount(voadas_h[voadas_h["t"] >= 6]["c"], minlength=N)
    u6 = Lh[Lh["t"] >= 12]
    n_atraso = np.bincount(u6[u6["atraso"] > 30]["c"], minlength=N)
    n_canc = np.bincount(u6[u6["cancelado"]]["c"], minlength=N)
    cp = voadas_h.groupby(["c", "pid"]).size().reset_index(name="n").sort_values(["c", "n", "pid"], ascending=[True, False, True])
    fav = np.full(N, -1); cpu = cp.drop_duplicates("c"); fav[cpu["c"].to_numpy()] = cpu["pid"].to_numpy()
    bc_h = ameacas_bc(voadas_h[["c", "pid", "t"]].drop_duplicates(), f)
    bc_h = bc_h[(bc_h["m"] >= 12) & (bc_h["m"] < T_HIST)]
    bc_h = bc_h[bc_h["pid"].to_numpy() == fav[bc_h["c"].to_numpy()]]
    flag = {d: np.zeros(N, bool) for d in ("saida_total", "reducao", "queda_tarifa")}
    for d in flag:
        flag[d][bc_h[bc_h["detalhe"] == d]["c"].to_numpy()] = True
    f25 = fid[fid["ano"] == 2025]
    perto = ((f25["_niv"].to_numpy() >= 1) & (f25["_folga"].to_numpy() < FOLGA_PERTO))
    logit = (INTERCEPTO[arq] + EF["atraso"] * np.minimum(n_atraso, 3) + EF["cancelamento"] * (n_canc > 0)
             + EF["saida"] * flag["saida_total"] + EF["reducao"] * flag["reducao"] + EF["queda"] * flag["queda_tarifa"]
             + EF["nivel"] * perto + EF["volume"] * (np.log1p(legs12) - math.log1p(VOLUME_REF))
             + EF["ruido"] * rng.standard_normal(N))
    parou = viajou & (rng.random(N) < 1 / (1 + np.exp(-logit)))
    L = L[~(L["c"].isin(np.where(parou)[0]) & (L["t"] >= T_HIST))].reset_index(drop=True)

    # ---- tabelas finais ----
    L = L.sort_values(["c", "data", "sentido"], kind="stable").reset_index(drop=True)
    L["viagem_id"] = uuids(np.random.default_rng([SEED, 2]), len(L))
    L["cliente_id"] = ids[L["c"].to_numpy()]
    L["par_rota"] = f["par_nomes"][L["pid"].to_numpy()]
    L["origem_icao"], L["destino_icao"] = f["aer"][L["o"].to_numpy()], f["aer"][L["d"].to_numpy()]
    L["ano_mes"] = np.array(MESES)[L["t"].to_numpy()]
    L["data_voo"] = L["data"]
    L["sentido"] = np.where(L["sentido"] == 0, "ida", "volta")
    L["tarifa_brl"] = L["tarifa"]
    L["antecedencia_dias"] = L["antec"].astype("int16")
    L["atraso_partida_min"] = L["atraso"].astype("Int32")
    cols = ["viagem_id", "cliente_id", "data_voo", "ano_mes", "sentido", "origem_icao", "destino_icao", "par_rota",
            "tarifa_brl", "antecedencia_dias", "atraso_partida_min", "cancelado"]
    hist, fut = L[L["t"] < T_HIST], L[L["t"] >= T_HIST]
    voadas = L[~L["cancelado"]]
    vf = voadas[voadas["t"] >= T_HIST]
    viajou_f = np.bincount(vf["c"], minlength=N)
    clv = np.bincount(vf["c"], weights=vf["tarifa"], minlength=N)
    rot = pd.DataFrame(dict(
        cliente_id=ids, data_corte=CORTE, viajou_no_historico=viajou,
        evasao=pd.array(np.where(viajou, (viajou_f == 0).astype(int), np.nan), dtype="Int8"),
        trechos_futuros_6m=viajou_f, clv_futuro_6m_brl=np.round(clv, 2)))
    clientes = pd.DataFrame(dict(cliente_id=ids, aeroporto_casa=f["homes"][home], consentimento_marketing=consent))
    arqt = pd.DataFrame(dict(cliente_id=ids, arquetipo=np.array(ARQ)[arq]))

    # ameacas finais: A por viagem (sorteio), B e C por par e mes
    a = L[L["cancelado"] | (L["atraso"] > 30)]
    ta = pd.DataFrame(dict(
        cliente_id=a["cliente_id"], tipo_ameaca="A", ano_mes=a["ano_mes"], data_ameaca=a["data"],
        par_rota=a["par_rota"], origem_icao=a["origem_icao"], destino_icao=a["destino_icao"],
        detalhe=np.where(a["cancelado"], "cancelamento", "atraso_30"), viagem_id=a["viagem_id"], _t=a["t"]))
    bc = ameacas_bc(voadas[["c", "pid", "t"]].drop_duplicates(), f)
    tb = pd.DataFrame(dict(
        cliente_id=ids[bc["c"].to_numpy()], tipo_ameaca=bc["tipo"], ano_mes=np.array(MESES)[bc["m"].to_numpy()],
        data_ameaca=INICIO_MES[bc["m"].to_numpy()], par_rota=f["par_nomes"][bc["pid"].to_numpy()],
        origem_icao=None, destino_icao=None, detalhe=bc["detalhe"], viagem_id=None, _t=bc["m"]))
    amea = pd.concat([ta, tb], ignore_index=True)
    amea["periodo"] = np.where(amea["_t"] < T_HIST, "historico", "rotulo")
    amea = amea.drop(columns="_t").sort_values(["cliente_id", "data_ameaca", "tipo_ameaca"], kind="stable").reset_index(drop=True)

    fid_out = fid.drop(columns=["_niv", "_folga"])
    saidas = {"clientes": clientes, "viagens": hist[cols], "viagens_futuro": fut[cols], "fidelidade": fid_out,
              "rotulos": rot, "customer_threats": amea, "archetypes_validacao": arqt}
    assert clientes["cliente_id"].is_unique and L["viagem_id"].is_unique and rot["cliente_id"].is_unique
    assert not any("arquetipo" in c for n_, d_ in saidas.items() if n_ != "archetypes_validacao" for c in d_.columns)
    assert hist["data"].max() <= CORTE and fut["data"].min() > CORTE and (L["tarifa"] > 0).all()
    assert set(amea["tipo_ameaca"]) <= {"A", "B", "C"} and fid_out.groupby("cliente_id").size().eq(3).all()
    for nome, df in saidas.items():
        out = SILVER / f"synthetic_{nome}" / "data.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp")
        df = df.assign(**{c: pd.to_datetime(df[c]).dt.date for c in ("data_voo", "data_ameaca", "data_corte", "referencia_ate") if c in df})   # DATE no Parquet
        df.to_parquet(tmp, compression="zstd", index=False)
        os.replace(tmp, out)
        print(f"synthetic_{nome}: {len(df)} linhas -> {out.relative_to(ROOT).as_posix()}", flush=True)

    # diagnostico: os efeitos documentados aparecem na taxa de evasao (entre quem viajou no historico; sem controle de confundidores)
    ev = rot["evasao"].to_numpy(dtype=float, na_value=np.nan)
    diag = {}
    for nome, m in (("saída total na rota favorita", flag["saida_total"]), ("redução na rota favorita", flag["reducao"]),
                    ("queda de tarifa na rota favorita", flag["queda_tarifa"]), ("perto de perder o nível", perto),
                    ("cancelamento nos últimos 6 meses", n_canc > 0), ("atraso > 30 min nos últimos 6 meses", n_atraso > 0)):
        d = viajou & m
        diag[nome] = (int(d.sum()), float(np.nanmean(ev[d])), float(np.nanmean(ev[viajou & ~m])))
    relatorio(f, L, fid, rot, amea, clientes, arqt, ids, perdidas, n_eventos, fora_janela, parou, viajou, diag, time.perf_counter() - t0)


def pct_err(s, p):
    return 100 * (s - p) / p


def relatorio(f, L, fid, rot, amea, clientes, arqt, ids, perdidas, n_eventos, fora_janela, parou, viajou, diag, seg):
    """Validacao sintetico x publico + cobertura das ameacas + numeros do relatorio; grava docs/VALIDACAO_SINTETICO.md."""
    con = duckdb.connect()
    mi = "(CAST(substr(ano_mes,1,4) AS INT)-2024)*12 + CAST(substr(ano_mes,6,2) AS INT) - 9"
    for t in ("anac_tarifas",):
        p = (SILVER / t / "*" / "data.parquet").as_posix()
        con.execute(f"CREATE VIEW {t} AS SELECT * FROM read_parquet('{p}', hive_partitioning=true)")
    for t in ("route_disruptions", "route_competition"):
        con.execute(f"CREATE VIEW {t} AS SELECT * FROM read_parquet('{(GOLD / t / 'data.parquet').as_posix()}')")
    top = con.execute("""
        WITH b AS (SELECT CASE WHEN origem_icao<destino_icao THEN origem_icao||'-'||destino_icao ELSE destino_icao||'-'||origem_icao END par,
                          SUM(assentos)::DOUBLE s, SUM(assentos*tarifa)::DOUBLE fs FROM anac_tarifas WHERE empresa_icao='AZU' GROUP BY 1)
        SELECT par, s, fs/s tarifa, s/SUM(s) OVER () part FROM b ORDER BY s DESC LIMIT 10""").df()
    dis = con.execute("""SELECT CASE WHEN origem_icao<destino_icao THEN origem_icao||'-'||destino_icao ELSE destino_icao||'-'||origem_icao END par,
                                SUM(voos_atraso_30)*1.0/SUM(voos_realizados) l FROM route_disruptions WHERE empresa_icao='AZU' GROUP BY 1""").df().set_index("par")["l"]
    mkt = con.execute("""SELECT par_rota par, SUM(CASE WHEN empresa_icao='AZU' THEN assentos_vendidos END)*1.0/SUM(assentos_vendidos) s
                         FROM route_competition GROUP BY 1""").df().set_index("par")["s"]
    pub_total_voos_l = con.execute("SELECT SUM(voos_atraso_30)*1.0/SUM(voos_realizados), SUM(voos_cancelados)*1.0/SUM(voos_previstos) FROM route_disruptions WHERE empresa_icao='AZU'").fetchone()
    pub_tarifa_g = con.execute("SELECT SUM(assentos*tarifa)/SUM(assentos) FROM anac_tarifas WHERE empresa_icao='AZU'").fetchone()[0]
    voadas = L[~L["cancelado"]]
    lin = []
    for _, r in top.iterrows():
        s = L[L["par_rota"] == r["par"]]
        sv = voadas[voadas["par_rota"] == r["par"]]
        sint_t, sint_sh = s["tarifa"].mean(), len(s) / len(L)
        sint_l = (sv["atraso"] > 30).mean()
        pub_l = float(dis.get(r["par"], np.nan))
        ok_ = ~s["cancelado"].to_numpy()
        esp_l = float(f["rl"][s["o"].to_numpy()[ok_], s["d"].to_numpy()[ok_], s["t"].to_numpy()[ok_]].mean())   # esperado com o mix rota-mes do sintetico
        lin.append((r["par"], r["tarifa"], sint_t, pct_err(sint_t, r["tarifa"]), r["part"], sint_sh, pct_err(sint_sh, r["part"]),
                    float(mkt.get(r["par"], np.nan)), pub_l, sint_l, pct_err(sint_l, pub_l), len(s), esp_l, pct_err(sint_l, esp_l)))
    v = pd.DataFrame(lin, columns=["par", "t_pub", "t_sint", "t_err", "sh_pub", "sh_sint", "sh_err", "azul_no_par", "l_pub", "l_sint", "l_err", "n", "l_esp", "l_err_esp"])
    glob_l = (voadas["atraso"] > 30).mean(); glob_c = L["cancelado"].mean()
    hubs = f["voos_origem"].sort_values(ascending=False).head(5)
    hs = clientes["aeroporto_casa"].value_counts(normalize=True)
    nivel_ano = fid.pivot_table(index="nivel_vigente", columns="ano", values="cliente_id", aggfunc="count").reindex(NIVEIS)
    f26 = fid[fid["ano"] == 2026].set_index("cliente_id")
    f25 = fid[fid["ano"] == 2025].set_index("cliente_id")
    nv = f26["nivel_vigente"]
    base = rot["evasao"].notna()
    evas = rot.loc[base, "evasao"].astype(float).mean()
    # cobertura de ameacas por nivel
    am = amea.merge(nv.rename("nivel").reset_index(), on="cliente_id")
    cob = {}
    for nivel in ("Diamante Unique", "Diamante", "Safira"):
        tot = (nv == nivel).sum()
        row = {"clientes": int(tot)}
        for per, filtro in (("todos", am["periodo"].notna()), ("historico", am["periodo"] == "historico")):
            sub = am[(am["nivel"] == nivel) & filtro]
            for tp in "ABC":
                row[f"{tp}_{per}"] = int(sub[sub["tipo_ameaca"] == tp]["cliente_id"].nunique())
        cob[nivel] = row
    tot_cli = {tp: int(amea[amea["tipo_ameaca"] == tp]["cliente_id"].nunique()) for tp in "ABC"}
    det = amea.groupby(["tipo_ameaca", "detalhe", "periodo"]).agg(eventos=("cliente_id", "size"), clientes=("cliente_id", "nunique")).reset_index()
    # proxy do arquetipo em colunas de entrada: pureza do arquetipo dado o valor da coluna (modelo ve so isso)
    ac = clientes.merge(arqt, on="cliente_id")
    pureza = {}
    dist = arqt["arquetipo"].value_counts(normalize=True)
    for col in ("aeroporto_casa", "consentimento_marketing"):   # distancia de variacao total entre P(arquetipo | valor) e P(arquetipo)
        tab = pd.crosstab(ac[col], ac["arquetipo"], normalize="index")
        w = ac[col].value_counts(normalize=True).reindex(tab.index)
        pureza[col] = float((w * 0.5 * (tab - dist.reindex(tab.columns)).abs().sum(axis=1)).sum())
    base_arq = float(dist.iloc[0])
    arq_evas = rot.merge(arqt, on="cliente_id").groupby("arquetipo").agg(clientes=("cliente_id", "size"), evasao=("evasao", lambda s: s.dropna().astype(float).mean()),
                                                                          viajou=("viajou_no_historico", "mean"))
    sem_viagem_hist = int((~rot["viajou_no_historico"]).sum())
    ids_ativos = set(voadas[(voadas["t"] >= 12) & (voadas["t"] < T_HIST)]["cliente_id"])
    m_at = rot["cliente_id"].isin(ids_ativos)
    evas_ativos = rot.loc[m_at, "evasao"].astype(float).mean()
    evas_nivel = rot.assign(nivel=rot["cliente_id"].map(nv)).groupby("nivel")["evasao"].apply(lambda s: s.dropna().astype(float).mean()).reindex(NIVEIS)

    md = ["# Validação do sintético contra fontes públicas",
          "",
          f"Gerado por `pipelines/synthetic/generate.py` (seed {SEED}). Erro % = 100 × (sintético − público) / público.",
          "Comparação sobre os 10 maiores pares (`par_rota`, dois sentidos somados) por assentos vendidos pela Azul (silver.anac_tarifas, AZU), janela 2024-09 a 2026-08.",
          "O sintético usa 50.000 clientes e todas as viagens geradas (histórico + rótulo). Ver premissas P-06 a P-14 e a circularidade (P-06).",
          "",
          "| Par | Tarifa pública (R$) | Tarifa sint. (R$) | Erro % | Share do par no total Azul (pub.) | Share sint. | Erro % | Azul no par (assentos Azul / mercado, pub.) | Atraso>30 pub. | Atraso>30 sint. | Erro % | Trechos sint. | Atraso esperado no mix sint. | Erro % vs esperado (ruído amostral) |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in v.itertuples():
        md.append(f"| {r.par} | {r.t_pub:,.2f} | {r.t_sint:,.2f} | {r.t_err:+.1f}% | {100*r.sh_pub:.2f}% | {100*r.sh_sint:.2f}% | {r.sh_err:+.1f}% | {100*r.azul_no_par:.1f}% | {100*r.l_pub:.2f}% | {100*r.l_sint:.2f}% | {r.l_err:+.1f}% | {r.n} | {100*r.l_esp:.2f}% | {r.l_err_esp:+.1f}% |")
    md += ["",
           f"- Tarifa média global: público R$ {pub_tarifa_g:,.2f}; sintético R$ {L['tarifa'].mean():,.2f} ({pct_err(L['tarifa'].mean(), pub_tarifa_g):+.1f}%).",
           f"- Atraso > 30 min global (voos realizados): público {100*pub_total_voos_l[0]:.2f}%; sintético {100*glob_l:.2f}% ({pct_err(glob_l, pub_total_voos_l[0]):+.1f}%).",
           f"- Cancelamento global: público {100*pub_total_voos_l[1]:.2f}%; sintético {100*glob_c:.2f}% ({pct_err(glob_c, pub_total_voos_l[1]):+.1f}%).",
           "",
           "**Erros acima de 5% e causas:** (1) *Share do par* (-46% a +17%): casa sorteada por voos do VRA e destino por assentos de tarifas; a razão voos/assentos por aeroporto (tabela abaixo) "
           "faz hubs (SBKP, SBCF) pesarem mais e SBSP, SBGR, SBBR, SBGL e SBPA menos que no público. Efeito pedido (hubs aparecem mais), não corrigido. "
           "(2) *Atraso > 30 min* (até ±8,6%): mistura de dois efeitos medidos nas duas últimas colunas; o mix rota-mês do sintético segue as vendas (mês da compra), não os voos, "
           "e o sorteio tem ruído binomial (cerca de 2,5% a 3,6% relativo, 1 desvio-padrão, nos pares com 7 a 16 mil trechos). O erro contra o esperado no mix fica em ±4,8%. "
           "(3) *Cancelamento global* (-12,8%): a taxa pública é ponderada por voos; o sintético pondera por passageiros, que se concentram em rotas de maior frequência e menor cancelamento. "
           "A tarifa média dos 10 pares fica dentro de ±5% (maior erro -4,1%).",
           "",
           "**Sobre a coluna 'Azul no par':** é a participação da Azul entre as companhias do par (público). O sintético tem só clientes da Azul e nenhum "
           "concorrente, então ela não é reproduzível por construção e vai apenas como contexto. O que o sintético reproduz é o peso do par no total de trechos da "
           "Azul, comparado ao peso do par no total de assentos da Azul (coluna 'Share do par').",
           "",
           "## Aeroporto de casa x voos da Azul no VRA (histórico)",
           "",
           "| Aeroporto | Share de voos Azul (VRA, tipo N, DI 0, 2024-09 a 2026-02) | Share de clientes (casa) |", "|---|---|---|"]
    vo = f["voos_origem"]; vo = vo / vo[[a for a in vo.index if a in set(f["homes"])]].sum()
    for a_ in hubs.index:
        md.append(f"| {a_} | {100*vo[a_]:.2f}% | {100*hs.get(a_, 0):.2f}% |")
    aer10 = sorted({a_ for p_ in top["par"] for a_ in p_.split("-")})
    md += ["", "Aeroportos dos 10 pares: peso na casa dos clientes x peso nos assentos da Azul com origem no aeroporto (silver.anac_tarifas, só entre aeroportos-casa). "
           "A razão voos/assentos explica por que o share do par no sintético difere do público (ver 'Share' acima): os pares com SBSP, SBGR e SBPA têm menos voos Azul no VRA do que assentos vendidos em tarifas.", "",
           "| Aeroporto | Share de voos Azul (VRA) | Share de assentos de origem (tarifas) | Razão voos/assentos |", "|---|---|---|---|"]
    ass = con.execute("SELECT origem_icao, SUM(assentos)::DOUBLE s FROM anac_tarifas WHERE empresa_icao='AZU' GROUP BY 1").df().set_index("origem_icao")["s"]
    ass = ass[[a_ for a_ in ass.index if a_ in set(f["homes"])]]; ass = ass / ass.sum()
    for a_ in aer10:
        md.append(f"| {a_} | {100*vo.get(a_, 0):.2f}% | {100*ass.get(a_, 0):.2f}% | {vo.get(a_, 0)/ass.get(a_, np.nan):.2f} |")
    md += ["", "## Cobertura das ameaças (clientes distintos)", "",
           "Eventos por tipo e período (A = sorteado por viagem; B e C = pares reais de `gold.route_exits` e `gold.route_competition` em que o cliente voou nos 12 meses até o mês da ameaça):",
           "", "| Tipo | Detalhe | Período | Eventos | Clientes |", "|---|---|---|---|---|"]
    for r in det.itertuples():
        md.append(f"| {r.tipo_ameaca} | {r.detalhe} | {r.periodo} | {r.eventos} | {r.clientes} |")
    md += ["", f"Clientes distintos atingidos (qualquer período): A {tot_cli['A']}, B {tot_cli['B']}, C {tot_cli['C']} de {N}.", "",
           "Por nível vigente em 28/02/2026 (histórico = ameaças até 2026-02; todos = inclui mar-ago/2026):", "",
           "| Nível | Clientes | A hist. | B hist. | C hist. | A todos | B todos | C todos |", "|---|---|---|---|---|---|---|---|"]
    for k, r in cob.items():
        md.append(f"| {k} | {r['clientes']} | {r['A_historico']} | {r['B_historico']} | {r['C_historico']} | {r['A_todos']} | {r['B_todos']} | {r['C_todos']} |")
    md += ["", "## Efeitos da evasão recuperáveis nos dados (diagnóstico bruto, sem controle de confundidores)", "",
           "| Condição (histórico, entre quem viajou) | Clientes | Evasão com a condição | Evasão sem a condição |", "|---|---|---|---|"]
    for k_, (n_, a1, a0) in diag.items():
        md.append(f"| {k_} | {n_} | {100*a1:.1f}% | {100*a0:.1f}% |")
    md += ["", "As diferenças brutas misturam o efeito injetado com confundidores (ex.: quem tem atraso viaja mais; quem perde nível viaja menos).",
           "", "## Proxy do arquétipo nas tabelas de entrada", "",
           "Distância de variação total média entre P(arquétipo | valor da coluna) e P(arquétipo) (0 = a coluna não informa nada sobre o arquétipo; 1 = proxy perfeito): "
           f"aeroporto_casa {pureza['aeroporto_casa']:.4f}, consentimento_marketing {pureza['consentimento_marketing']:.4f}. "
           "As colunas de comportamento (frequência, antecedência, tarifa) são correlacionadas ao arquétipo por construção, mas as classes se sobrepõem (Gamma, ruído) e nenhuma coluna o identifica sozinha.",
           "", f"Tempo total de execução: {seg:.0f} s."]
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "VALIDACAO_SINTETICO.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print("\n===== RESUMO =====")
    print("clientes por nivel vigente (ano):\n", nivel_ano.to_string())
    print("nivel vigente ao fim do historico (2026-02-28):\n", nv.value_counts().reindex(NIVEIS).to_string())
    print(f"evasao: base={int(base.sum())} (viajaram no historico), evadiram={int(rot.loc[base,'evasao'].astype(float).sum())}, taxa={100*evas:.2f}%; sem viagem no historico={sem_viagem_hist}")
    print(f"evasao entre ativos nos ultimos 6m do historico: {100*evas_ativos:.2f}% (n={int(m_at.sum())})")
    print("evasao por nivel:\n", evas_nivel.to_string())
    print("evasao/viajou por arquetipo (validacao):\n", arq_evas.to_string())
    print("S (parou) total:", int(parou.sum()), "| eventos de compra:", n_eventos, "| perdidos (sem rota):", perdidas, "| fora da janela/pos-saida:", fora_janela)
    print("diag:", diag)
    print("ameacas por nivel:", cob)
    print("clientes atingidos por tipo:", tot_cli)
    print(det.to_string())
    print(v.round(4).to_string())
    print("global tarifa", L["tarifa"].mean(), pub_tarifa_g, "atraso", glob_l, pub_total_voos_l, "cancel", glob_c)
    print("pureza proxy", pureza, base_arq)
    print(f"tempo total {seg:.1f}s")


if __name__ == "__main__":
    main()
