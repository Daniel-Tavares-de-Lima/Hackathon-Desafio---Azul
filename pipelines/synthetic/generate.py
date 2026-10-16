"""Gemeo digital da base de clientes: 50 mil clientes ficticios, viagens, nivel de fidelidade, ameacas (historico e rotulo separados), elegibilidade e alvos.

Uso: python -I -X utf8 pipelines/synthetic/generate.py
Entradas : data/silver/anac_{tarifas,vra} e data/gold/route_{disruptions,exits,competition} (so leitura).
Saidas   : data/silver/synthetic_*/data.parquet e docs/VALIDACAO_SINTETICO.md.
Premissas: docs/PREMISSAS.md (P-06 em diante). Tudo e sintetico por construcao: o gerador devolve as regras
que ele mesmo usa (circularidade, ver P-06).
Janela: derivada de ANAC_END_MONTH (padrao 2026-08) e ANAC_MONTHS (padrao 24), as mesmas variaveis das gold. Os ultimos
T_ROT = 6 meses sao o periodo de rotulo; os anteriores, o historico. Padrao: indice 0 = 2024-09 ... 17 = 2026-02
(historico, corte em 2026-02-28); 18 = 2026-03 ... 23 = 2026-08 (rotulo).
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
# ---- janela (P-06): mesmas variaveis de ambiente das gold (pipelines/build_gold.py) ----
END_MONTH = os.environ.get("ANAC_END_MONTH", "2026-08")   # ultimo mes da janela ANAC
NM = int(os.environ.get("ANAC_MONTHS", "24"))             # meses da janela
T_ROT = 6                                                 # ultimos 6 meses = periodo de rotulo
T_HIST = NM - T_ROT                                       # meses 0..T_HIST-1 = historico
MES0 = np.datetime64(END_MONTH, "M") - np.timedelta64(NM - 1, "M")   # indice de mes 0 (2024-09 no padrao)
fim_mes = lambda k: (MES0 + np.timedelta64(k + 1, "M")).astype("datetime64[D]") - np.timedelta64(1, "D")   # ultimo dia do mes de indice k
MESES = [str(MES0 + np.timedelta64(i, "M")) for i in range(NM)]
INICIO_MES = (MES0 + np.arange(NM)).astype("datetime64[D]")
CORTE = fim_mes(T_HIST - 1)                               # fim do historico (2026-02-28 no padrao)
FIM_JANELA = fim_mes(NM - 1)                              # fim do periodo de rotulo (2026-08-31 no padrao)

# ---- premissas (cada uma documentada em docs/PREMISSAS.md, P-06 a P-15) ----
ARQ = ["corporativo_frequente", "lazer_premium", "regional_dependente", "em_ascensao", "ocasional"]
MIX = np.array([0.08, 0.10, 0.18, 0.15, 0.49])
LAMBDA_MEDIA = np.array([0.9, 0.25, 0.28, 0.20, 0.12])   # eventos (ida e volta) por mes
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
# evasao (P-13): probabilidade de "parar" = sigmoid(base) + efeitos ADITIVOS em pontos percentuais (calibrados por faixa de frequencia)
INTERCEPTO = np.array([-3.0, -2.4, -2.6, -3.2, -2.0])
EF_FREQ_FAIXA = np.array([0.4, 0.0, -0.5])                # frequencia alta REDUZ a chance: degrau no logit por faixa (baixa, media, alta); sem efeito continuo dentro da faixa
EF_QUEDA = 1.5                                            # tendencia de queda: logit por unidade de (1 - razao), razao = (trechos/mes ultimos 6) / (trechos/mes dos 12 anteriores)
EF_RUIDO = 0.6                                            # desvio do ruido individual no logit
DELTA_PP = dict(a_grave=0.08, saida=0.20, reducao=0.08, queda=0.10, nivel=0.06)   # alvo da diferenca de evasao entre expostos e nao expostos, na mesma faixa
RUIDO_EFEITO = 0.30                                       # cada efeito individual ~ N(1; 0,30) clipado em 0,2..2 vezes o valor
ELEG_MIN = 3.0                                            # elegivel: trechos esperados em 6 meses (taxa mensal do historico x 6) >= 3
LIMITE_EVASAO = 0.30                                      # evasao = voar <= 30% do esperado no periodo de rotulo
PHI_ZERO, PHI_MAX = 0.6, 0.25                             # quem para: 60% zera o futuro; os demais mantem fracao U(0; 0,25) dos trechos
FOLGA_PERTO = 0.25                                        # folga < 25% acima do limite = perto de perder o nivel
ATRASO_GRAVE_MIN, JANELA_GRAVE_DIAS = 60, 90              # ameaca A grave: 2 eventos (atraso > 60 min ou cancelado) em 90 dias

NIVEIS = ["Sem nível", "Topázio", "Safira", "Diamante", "Diamante Unique"]
# caminhos alternativos (OU); dentro do caminho, todos os requisitos (E): (trechos, pontos, gasto R$)
REGRAS = {1: [(6, None, None), (None, 6000, None)], 2: [(10, None, None), (None, 10000, None)],
          3: [(12, 12000, None), (None, None, 25000)], 4: [(26, 26000, None), (None, None, 50000)]}
# anos calendario do historico: (ano, 1o indice, ultimo indice, referencia_ate, ano_completo); padrao 2024 (set-dez), 2025, 2026 (jan-fev)
ANOS = [(y, min(i), max(i), fim_mes(max(i)), len(i) == 12)
        for y in sorted({int(m[:4]) for m in MESES[:T_HIST]}) for i in [[k for k in range(T_HIST) if int(MESES[k][:4]) == y]]]
ANO_COMPLETO = max(a[0] for a in ANOS if a[4])           # ultimo ano completo do historico (2025): base do "perto de cair de nivel"


def mi(col="ano_mes"):
    """SQL: 'AAAA-MM' -> indice de mes da janela (0 = MES0)."""
    m0 = MES0.astype(int)   # meses desde 1970-01
    return f"((CAST(substr({col},1,4) AS INT)-1970)*12 + CAST(substr({col},6,2) AS INT) - 1 - {m0})"


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
    for t in ("route_exits", "route_competition", "route_disruptions"):
        got = con.execute(f"SELECT min(ano_mes), max(ano_mes) FROM {t}").fetchone()
        assert got == (MESES[0], MESES[-1]), f"gold.{t} cobre {got}, janela do gerador {MESES[0]}..{MESES[-1]}"
    par = "CASE WHEN origem_icao<destino_icao THEN origem_icao||'-'||destino_icao ELSE destino_icao||'-'||origem_icao END"
    f = {}
    # distribuicao empirica de tarifa da Azul por par x mes (chave = id do grupo + CDF acumulada por assentos)
    g = con.execute(f"""
        WITH b AS (SELECT {par} par, {mi()} t, tarifa::DOUBLE tarifa, SUM(assentos) a FROM anac_tarifas
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
    # saida total por par: de mes_saida ate o mes anterior ao retorno (1o mes seguinte com voo do grupo Azul em gold.route_exits)
    # a Azul nao vende nem voa no par; sem retorno na janela, fica fora ate o fim. Pares so da ACN (sem venda AZU na ANAC
    # Tarifas) nao tem pid e ficam fora do sintetico (P-08, P-15).
    ex = con.execute(f"SELECT DISTINCT par_rota, {mi('mes_saida')} ms FROM route_exits WHERE saida_total").df()
    vp = con.execute(f"SELECT par_rota, {mi()} t FROM route_exits GROUP BY ALL HAVING SUM(voos_azul) > 0").df()
    ex = ex.merge(vp, on="par_rota", how="left")
    ex["t"] = np.where(ex["t"] > ex["ms"], ex["t"], NM)
    ex = ex.groupby(["par_rota", "ms"], as_index=False)["t"].min().rename(columns={"t": "volta"})
    ex["pid"] = ex["par_rota"].map(f["pid_de"])
    f["saidas_gold"] = ex
    ex = ex.dropna(subset=["pid"]).astype({"pid": int, "ms": int, "volta": int}).sort_values(["pid", "ms"])
    f["saidas"] = ex[["pid", "ms"]].reset_index(drop=True)
    off = np.zeros((P, NM), bool)
    for p_, m_, v_ in ex[["pid", "ms", "volta"]].itertuples(index=False):
        off[p_, m_:v_] = True
    f["off"] = off
    for nome, tab, col in (("reducao", "route_exits", "reducao"), ("queda", "route_competition", "queda_tarifa")):
        d = con.execute(f"SELECT par_rota, {mi()} m FROM {tab} WHERE {col} GROUP BY ALL ORDER BY ALL").df()
        d["pid"] = d["par_rota"].map(f["pid_de"])
        f[nome] = d.dropna(subset=["pid"]).astype({"pid": int})[["pid", "m"]]
    # pesos de destino por origem x mes (assentos da Azul por rota direcional)
    dr = con.execute(f"""SELECT origem_icao o, destino_icao d, {par} par, {mi()} t, SUM(assentos)::DOUBLE s, SUM(assentos*tarifa)::DOUBLE fs
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
    W *= ~off[dest_pid].transpose(0, 2, 1)                                    # par sem Azul entre a saida total e o retorno
    f.update(homes=np.array(homes), home_air=np.array([aidx[a] for a in homes]), W=W, dest_pid=dest_pid,
             dest_air=dest_air, tarifa_media_slot=np.where(stot > 0, ftot / np.maximum(stot, 1), 0.0))
    vo = con.execute(f"""SELECT origem_icao, COUNT(*) FROM anac_vra WHERE empresa_icao='AZU' AND tipo_linha='N' AND codigo_di='0'
                        AND situacao_voo IN ('REALIZADO','CANCELADO') AND ano_mes <= '{MESES[T_HIST - 1]}' GROUP BY 1""").df()
    vo = vo.set_index("origem_icao")["count_star()"]
    f["voos_origem"] = vo
    f["peso_home"] = stot.sum(1)                                   # casa por assentos da Azul (tarifas), mesma fonte das rotas
    # taxas de cancelamento e atraso > 30 por rota direcional x mes (Azul)
    A = len(aer)
    rc = np.full((A, A, NM), np.nan, np.float32); rl = rc.copy()
    d = con.execute(f"SELECT origem_icao o, destino_icao d, {mi()} t, pct_cancelado::DOUBLE/100 c, pct_atraso_30::DOUBLE/100 l FROM route_disruptions WHERE empresa_icao='AZU'").df()
    d = d[d["o"].isin(aidx) & d["d"].isin(aidx)]
    io, idd, it = d["o"].map(aidx).to_numpy(), d["d"].map(aidx).to_numpy(), d["t"].to_numpy()
    rc[io, idd, it] = d["c"].astype(float).to_numpy(); rl[io, idd, it] = d["l"].astype(float).to_numpy()
    f["rc_obs"] = ~np.isnan(rc)
    glob = con.execute(f"""SELECT {mi()} t, SUM(voos_cancelados)::DOUBLE/SUM(voos_previstos) c, SUM(voos_atraso_30)::DOUBLE/SUM(voos_realizados) l
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
    ini_c = (MES0 + tp).astype("datetime64[D]")
    dias_c = ((MES0 + (tp + 1)).astype("datetime64[D]") - ini_c).astype(int)
    sea = W.sum((0, 2)); sea = sea / sea.mean()                  # sazonalidade da rede (usada so se nenhuma favorita vende no mes)
    # favoritas: ate 3 destinos da casa, sorteados pelo total de assentos (com vies de tarifa p/ lazer premium)
    wtot = W.sum(1)
    favs = np.zeros((N, 3), int)
    for a in range(len(ARQ)):
        w = wtot * np.where(f["tarifa_media_slot"] > 0, f["tarifa_media_slot"] ** EXPOENTE_TARIFA_FAV[a], 0.0)
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
    mes_voo = lambda d: (d.astype("datetime64[M]") - MES0).astype(int)
    t_ida, t_volta = mes_voo(data_ida), mes_voo(data_volta)
    sem_azul = lambda t: f["off"][pid, np.clip(t, 0, NM - 1)]                  # Azul fora do par no mes do voo (saida ate o retorno)
    dentro = (data_ida >= INICIO_MES[0]) & (data_ida <= FIM_JANELA) & ~sem_azul(t_ida)   # voo fora da janela ou com a Azul fora do par
    fora_janela = int((~dentro).sum())
    tem_volta = dentro & (rng.random(E) < PROB_IDA_VOLTA) & (data_volta <= FIM_JANELA) & ~sem_azul(t_volta)
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


def gatilhos_a(L):
    """Ameaca A grave: 2 eventos (atraso de partida > 60 min ou cancelado) em ate 90 dias. Devolve as linhas do 2o evento.
    Guloso por cliente: eventos ja usados num gatilho nao entram no proximo."""
    E = L[L["cancelado"] | (L["atraso"] > ATRASO_GRAVE_MIN)].sort_values(["c", "data", "sentido"], kind="stable")
    c = E["c"].to_numpy(); d = E["data"].to_numpy().astype("datetime64[D]").astype(int)
    trig = np.zeros(len(E), bool); ult = -1
    for i in range(len(E)):
        if ult >= 0 and c[ult] == c[i] and d[i] - d[ult] <= JANELA_GRAVE_DIAS:
            trig[i] = True; ult = -1
        else:
            ult = i
    return E[trig]


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

    # ---- evasao: features do historico (ate 2026-02), elegibilidade e efeitos ----
    voadas_h = Lh[~Lh["cancelado"]]
    legs_hist = np.bincount(voadas_h["c"], minlength=N)
    viajou = legs_hist > 0
    esperado6 = legs_hist / T_HIST * 6                       # trechos esperados em 6 meses = taxa mensal do historico x 6
    elegivel = esperado6 >= ELEG_MIN
    T6 = T_HIST - 6                                          # inicio dos ultimos 6 meses do historico (2025-09 no padrao)
    l6 = np.bincount(voadas_h[voadas_h["t"] >= T6]["c"], minlength=N)
    p12 = np.bincount(voadas_h[voadas_h["t"] < T6]["c"], minlength=N)
    razao = np.where(p12 > 0, (l6 / 6) / np.maximum(p12 / T6, 1e-9), 1.0)      # sem base nos meses anteriores: neutro
    queda = np.clip(1 - razao, -0.5, 1.0)
    gh = gatilhos_a(Lh); gh = gh[gh["t"] >= T6]
    a_grave = np.zeros(N, bool); a_grave[gh["c"].to_numpy()] = True
    cp = voadas_h.groupby(["c", "pid"]).size().reset_index(name="n").sort_values(["c", "n", "pid"], ascending=[True, False, True])
    fav = np.full(N, -1); cpu = cp.drop_duplicates("c"); fav[cpu["c"].to_numpy()] = cpu["pid"].to_numpy()
    bc_h = ameacas_bc(voadas_h[["c", "pid", "t"]].drop_duplicates(), f)
    bc_h = bc_h[(bc_h["m"] >= T6) & (bc_h["m"] < T_HIST)]
    bc_h = bc_h[bc_h["pid"].to_numpy() == fav[bc_h["c"].to_numpy()]]
    flag = {d: np.zeros(N, bool) for d in ("saida_total", "reducao", "queda_tarifa")}
    for d in flag:
        flag[d][bc_h[bc_h["detalhe"] == d]["c"].to_numpy()] = True
    f25 = fid[fid["ano"] == ANO_COMPLETO]
    perto = ((f25["_niv"].to_numpy() >= 1) & (f25["_folga"].to_numpy() < FOLGA_PERTO))
    # faixas de frequencia = tercis da taxa mensal entre elegiveis; q = evasao "natural" (so acaso) da faixa, para calibrar o delta
    taxa_mes = legs_hist / T_HIST
    cortes = np.quantile(taxa_mes[elegivel], [1 / 3, 2 / 3])
    faixa = np.where(elegivel, np.digitize(taxa_mes, cortes), -1)
    nat_cnt = np.bincount(L[(L["t"] >= T_HIST) & ~L["cancelado"]]["c"], minlength=N)
    nat = nat_cnt <= LIMITE_EVASAO * esperado6 + 1e-9
    q_faixa = np.array([nat[elegivel & (faixa == b)].mean() for b in range(3)])
    qc = q_faixa[np.maximum(faixa, 0)]
    eps = np.clip(1 + RUIDO_EFEITO * rng.standard_normal((N, 5)), 0.2, 2.0)
    expo = np.stack([a_grave, flag["saida_total"], flag["reducao"], flag["queda_tarifa"], perto], 1)
    fb = np.maximum(faixa, 0)
    p0 = 1 / (1 + np.exp(-(INTERCEPTO[arq] + EF_FREQ_FAIXA[fb] + EF_QUEDA * queda + EF_RUIDO * rng.standard_normal(N))))
    u_par = rng.random(N)
    alvo = np.array(list(DELTA_PP.values()))
    # calibracao por faixa: ajusta kappa[ameaca, faixa] (multiplicador do delta) ate a diferenca observada de evasao entre expostos e nao
    # expostos DA MESMA FAIXA ficar no alvo. Absorve confundidores (ex.: saida de rota reduz trechos e ja puxa a tendencia de queda).
    # Saida total tem poucos expostos: um kappa so para as tres faixas.
    kappa = np.ones((5, 3))
    for it in range(15):
        dlt = (alvo[:, None] * kappa[:, fb] / (1 - qc)[None, :]).T
        pp_ = np.clip(p0 + (expo * dlt * eps).sum(1), 0.005, 0.98)
        lab = elegivel & (((u_par < pp_) & viajou) | nat)
        for k_ in range(5):
            dif, nn = [], []
            for b_ in range(3):
                g = elegivel & (faixa == b_)
                e1 = g & expo[:, k_]
                dif.append(lab[e1].mean() - lab[g & ~expo[:, k_]].mean() if e1.sum() >= 8 else np.nan); nn.append(e1.sum())
            dif, nn = np.array(dif), np.array(nn)
            if k_ == 1:
                ok_ = ~np.isnan(dif)
                kappa[k_, :] = np.clip(kappa[k_, :] + 0.8 * (alvo[k_] - np.sum(dif[ok_] * nn[ok_]) / nn[ok_].sum()) / alvo[k_], 0, 8)
            else:
                for b_ in range(3):
                    if not np.isnan(dif[b_]):
                        kappa[k_, b_] = np.clip(kappa[k_, b_] + 0.8 * (alvo[k_] - dif[b_]) / alvo[k_], 0, 8)
    dlt = (alvo[:, None] * kappa[:, fb] / (1 - qc)[None, :]).T
    p = np.clip(p0 + (expo * dlt * eps).sum(1), 0.005, 0.98)
    parou = viajou & (u_par < p)
    # quem para voa <= 30% do esperado: mantem cada trecho do rotulo com prob. phi e depois corta ate o teto
    phi = np.where(rng.random(N) < PHI_ZERO, 0.0, rng.uniform(0, PHI_MAX, N))
    L = L[~((L["t"] >= T_HIST) & parou[L["c"].to_numpy()]) | (rng.random(len(L)) < phi[L["c"].to_numpy()])].reset_index(drop=True)
    cap = np.floor(LIMITE_EVASAO * esperado6 + 1e-9).astype(int)
    sub = L[(L["t"] >= T_HIST) & ~L["cancelado"] & parou[L["c"].to_numpy()]].assign(_k=lambda d: rng.random(len(d))).sort_values(["c", "_k"])
    ex = sub.index[sub.groupby("c").cumcount().to_numpy() >= cap[sub["c"].to_numpy()]]
    L = L.drop(index=ex).reset_index(drop=True)

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
        elegivel_evasao=elegivel, trechos_esperados_6m=np.round(esperado6, 2),
        evasao=pd.array(np.where(elegivel, (viajou_f <= LIMITE_EVASAO * esperado6 + 1e-9).astype(int), np.nan), dtype="Int8"),
        trechos_futuros_6m=viajou_f, clv_futuro_6m_brl=np.round(clv, 2)))
    clientes = pd.DataFrame(dict(cliente_id=ids, aeroporto_casa=f["homes"][home], consentimento_marketing=consent))
    arqt = pd.DataFrame(dict(cliente_id=ids, arquetipo=np.array(ARQ)[arq]))

    # ameacas finais: A por viagem (sorteio), B e C por par e mes
    a = gatilhos_a(L)
    ta = pd.DataFrame(dict(
        cliente_id=a["cliente_id"], tipo_ameaca="A", ano_mes=a["ano_mes"], data_ameaca=a["data"],
        par_rota=a["par_rota"], origem_icao=a["origem_icao"], destino_icao=a["destino_icao"],
        detalhe="grave_2_eventos_90d", viagem_id=a["viagem_id"], _t=a["t"]))
    bc = ameacas_bc(voadas[["c", "pid", "t"]].drop_duplicates(), f)
    tb = pd.DataFrame(dict(
        cliente_id=ids[bc["c"].to_numpy()], tipo_ameaca=bc["tipo"], ano_mes=np.array(MESES)[bc["m"].to_numpy()],
        data_ameaca=INICIO_MES[bc["m"].to_numpy()], par_rota=f["par_nomes"][bc["pid"].to_numpy()],
        origem_icao=None, destino_icao=None, detalhe=bc["detalhe"], viagem_id=None, _t=bc["m"]))
    amea = pd.concat([ta, tb], ignore_index=True)
    amea["periodo"] = np.where(amea["_t"] < T_HIST, "historico", "rotulo")   # so interno (relatorio); vira duas tabelas
    chave_amea = ["cliente_id", "data_ameaca", "tipo_ameaca", "detalhe", "par_rota", "viagem_id"]
    amea = amea.drop(columns="_t").sort_values(chave_amea, kind="stable", na_position="first").reset_index(drop=True)
    hist_amea = amea["periodo"] == "historico"

    fid_out = fid.drop(columns=["_niv", "_folga"])
    # sem nada do periodo de rotulo nas tabelas de entrada: elegibilidade so usa o historico; alvos e ameacas do rotulo ficam a parte
    eleg = rot[["cliente_id", "data_corte", "viajou_no_historico", "elegivel_evasao", "trechos_esperados_6m"]]
    alvos = rot[["cliente_id", "data_corte", "evasao", "trechos_futuros_6m", "clv_futuro_6m_brl"]]
    saidas = {"clientes": clientes, "viagens": hist[cols], "viagens_futuro": fut[cols], "fidelidade": fid_out,
              "elegibilidade": eleg, "alvos": alvos,
              "customer_threats": amea[hist_amea].drop(columns="periodo"), "customer_threats_rotulo": amea[~hist_amea].drop(columns="periodo"),
              "archetypes_validacao": arqt}
    assert clientes["cliente_id"].is_unique and L["viagem_id"].is_unique and rot["cliente_id"].is_unique
    assert not any("arquetipo" in c for n_, d_ in saidas.items() if n_ != "archetypes_validacao" for c in d_.columns)
    assert hist["data"].max() <= CORTE and fut["data"].min() > CORTE and (L["tarifa"] > 0).all()
    assert saidas["customer_threats"]["data_ameaca"].max() <= CORTE and saidas["customer_threats_rotulo"]["data_ameaca"].min() > CORTE
    assert set(amea["tipo_ameaca"]) <= {"A", "B", "C"} and fid_out.groupby("cliente_id").size().eq(len(ANOS)).all()
    for nome, df in saidas.items():
        out = SILVER / f"synthetic_{nome}" / "data.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp")
        df = df.reset_index(drop=True)   # ordem ja fixa (clientes por id gerado, viagens por cliente/data, ameacas pela chave): mesma seed, mesmos bytes
        df = df.assign(**{c: pd.to_datetime(df[c]).dt.date for c in ("data_voo", "data_ameaca", "data_corte", "referencia_ate") if c in df})   # DATE no Parquet
        df.to_parquet(tmp, compression="zstd", index=False)
        os.replace(tmp, out)
        print(f"synthetic_{nome}: {len(df)} linhas -> {out.relative_to(ROOT).as_posix()}", flush=True)

    # diagnostico por faixa de frequencia: taxa de evasao de expostos x nao expostos (entre elegiveis)
    ev = rot["evasao"].to_numpy(dtype=float, na_value=np.nan)
    diag = {}
    for k_, (nome, m) in enumerate((("A grave (2 eventos em 90 dias)", a_grave), ("B saída total na rota favorita", flag["saida_total"]),
                                    ("B redução na rota favorita", flag["reducao"]), ("C queda de tarifa na rota favorita", flag["queda_tarifa"]),
                                    ("Perto de cair de nível", perto))):
        linhas = []
        for b_ in range(3):
            g = elegivel & (faixa == b_)
            e1, e0 = g & m, g & ~m
            linhas.append((b_, int(e1.sum()), float(np.mean(ev[e1])) if e1.any() else np.nan, float(np.mean(ev[e0])),
                           100 * (float(np.mean(ev[e1])) - float(np.mean(ev[e0]))) if e1.any() else np.nan))
        bruto = 100 * (float(np.nanmean(ev[elegivel & m])) - float(np.nanmean(ev[elegivel & ~m]))) if (elegivel & m).any() else np.nan
        diag[nome] = (linhas, DELTA_PP[list(DELTA_PP)[k_]], bruto)
    diag["_cortes"] = (cortes, q_faixa)
    diag["_kappa"] = kappa
    relatorio(f, L, fid, rot, amea, clientes, arqt, ids, perdidas, n_eventos, fora_janela, parou, viajou, diag)
    print(f"tempo total {time.perf_counter() - t0:.1f}s")


def pct_err(s, p):
    return 100 * (s - p) / p


def relatorio(f, L, fid, rot, amea, clientes, arqt, ids, perdidas, n_eventos, fora_janela, parou, viajou, diag):
    """Validacao sintetico x publico + cobertura das ameacas + numeros do relatorio; grava docs/VALIDACAO_SINTETICO.md."""
    con = duckdb.connect()
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
                                SUM(voos_atraso_30)::DOUBLE/SUM(voos_realizados) l FROM route_disruptions WHERE empresa_icao='AZU' GROUP BY 1""").df().set_index("par")["l"]
    mkt = con.execute("""SELECT par_rota par, SUM(CASE WHEN empresa_icao='AZU' THEN assentos_vendidos END)::DOUBLE/SUM(assentos_vendidos) s
                         FROM route_competition GROUP BY 1""").df().set_index("par")["s"]
    pub_total_voos_l = con.execute("SELECT SUM(voos_atraso_30)::DOUBLE/SUM(voos_realizados), SUM(voos_cancelados)::DOUBLE/SUM(voos_previstos) FROM route_disruptions WHERE empresa_icao='AZU'").fetchone()
    pub_tarifa_g = con.execute("SELECT (SUM(assentos*tarifa)/SUM(assentos))::DOUBLE FROM anac_tarifas WHERE empresa_icao='AZU'").fetchone()[0]
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
        so, sd, st = s["o"].to_numpy(), s["d"].to_numpy(), s["t"].to_numpy()
        obs_ = f["rc_obs"][so, sd, st]
        esp_c = float(f["rc"][so, sd, st][obs_].mean()); sint_c = float(s["cancelado"].to_numpy()[obs_].mean())
        lin.append((r["par"], r["tarifa"], sint_t, pct_err(sint_t, r["tarifa"]), r["part"], sint_sh, pct_err(sint_sh, r["part"]),
                    float(mkt.get(r["par"], np.nan)), pub_l, sint_l, pct_err(sint_l, pub_l), len(s), esp_l, pct_err(sint_l, esp_l),
                    sint_c, esp_c, pct_err(sint_c, esp_c)))
    v = pd.DataFrame(lin, columns=["par", "t_pub", "t_sint", "t_err", "sh_pub", "sh_sint", "sh_err", "azul_no_par", "l_pub", "l_sint", "l_err", "n", "l_esp", "l_err_esp",
                                   "c_sint", "c_esp", "c_err"])
    glob_l = (voadas["atraso"] > 30).mean(); glob_c = L["cancelado"].mean()
    lo, ld, lt = L["o"].to_numpy(), L["d"].to_numpy(), L["t"].to_numpy()
    obs_g = f["rc_obs"][lo, ld, lt]
    esp_cg = float(f["rc"][lo, ld, lt][obs_g].mean()); sint_cg = float(L["cancelado"].to_numpy()[obs_g].mean())
    hs = clientes["aeroporto_casa"].value_counts(normalize=True)
    nivel_ano = fid.pivot_table(index="nivel_vigente", columns="ano", values="cliente_id", aggfunc="count").reindex(NIVEIS)
    nv = fid[fid["ano"] == ANOS[-1][0]].set_index("cliente_id")["nivel_vigente"]
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
    det = amea.groupby(["tipo_ameaca", "detalhe", "periodo"]).agg(eventos=("cliente_id", "size"), clientes=("cliente_id", "nunique"),
                                                                    ini=("ano_mes", "min"), fim=("ano_mes", "max")).reset_index()
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
    n_eleg = int(rot["elegivel_evasao"].sum())
    evas_nivel = rot.assign(nivel=rot["cliente_id"].map(nv)).groupby("nivel")["evasao"].apply(lambda s: s.dropna().astype(float).mean()).reindex(NIVEIS)

    md = ["# Validação do sintético contra fontes públicas",
          "",
          f"Gerado por `pipelines/synthetic/generate.py` (seed {SEED}). Erro % = 100 × (sintético − público) / público.",
          f"Comparação sobre os 10 maiores pares (`par_rota`, dois sentidos somados) por assentos vendidos pela Azul (silver.anac_tarifas, AZU), janela {MESES[0]} a {MESES[-1]}.",
          f"O sintético usa {N:,} clientes e todas as viagens geradas (histórico + rótulo). Ver premissas P-06 a P-15 e a circularidade (P-06).".replace(",", "."),
          "",
          "| Par | Tarifa pública (R$) | Tarifa sint. (R$) | Erro % | Share do par no total Azul (pub.) | Share sint. | Erro % | Azul no par (assentos Azul / mercado, pub.) | Atraso>30 pub. | Atraso>30 sint. | Erro % | Trechos sint. | Atraso esperado no mix sint. | Erro % vs esperado (ruído amostral) |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in v.itertuples():
        md.append(f"| {r.par} | {r.t_pub:,.2f} | {r.t_sint:,.2f} | {r.t_err:+.1f}% | {100*r.sh_pub:.2f}% | {100*r.sh_sint:.2f}% | {r.sh_err:+.1f}% | {100*r.azul_no_par:.1f}% | {100*r.l_pub:.2f}% | {100*r.l_sint:.2f}% | {r.l_err:+.1f}% | {r.n} | {100*r.l_esp:.2f}% | {r.l_err_esp:+.1f}% |")
    md += ["",
           f"- Tarifa média global: público R$ {pub_tarifa_g:,.2f}; sintético R$ {L['tarifa'].mean():,.2f} ({pct_err(L['tarifa'].mean(), pub_tarifa_g):+.1f}%).",
           f"- Atraso > 30 min global (voos realizados): público {100*pub_total_voos_l[0]:.2f}%; sintético {100*glob_l:.2f}% ({pct_err(glob_l, pub_total_voos_l[0]):+.1f}%).",
           f"- Share do par: erro absoluto máximo {v['sh_err'].abs().max():.1f}%, médio {v['sh_err'].abs().mean():.1f}% (versão anterior, casa por voos do VRA: de -46% a +17%).",
           "",
           "**Erros acima de 5% e causas prováveis (não isoladas por teste):** (1) *Share do par* (SBGR-SBPA, SBCF-SBSP): casa e destino já saem dos mesmos assentos de tarifas, "
           "mas o peso do par depende também da sazonalidade por rota (índice com teto 3), de cada cliente ter só 1 a 3 destinos favoritos e dos eventos perdidos onde a Azul saiu; "
           "com 50.000 clientes e poucos milhares de trechos por par, parte é ruído de composição. (2) *Atraso > 30 min*: o sorteio é binomial (desvio-padrão de 2,5% a 3,5% relativo "
           "nos pares) e o mix rota-mês do sintético segue as vendas, não os voos; compare as duas últimas colunas (erro contra o esperado no mix). (3) *Cancelamento por par*: evento de cerca de 0,5% a 2%, "
           "desvio-padrão do sorteio de 8% a 15% relativo por par; o teste relevante é o global.",
           "",
           "## Cancelamento com a mesma ponderação nos dois lados",
           "",
           "A taxa pública de cancelamento de `gold.route_disruptions` é por rota direcional e mês (cancelados / previstos). A comparação anterior (2,04% ponderada por voos x 1,78% do sintético ponderado por passageiros) "
           "misturava ponderações. Aqui o **público é reponderado pelo mix de trechos do sintético**: para cada trecho gerado, a taxa pública da sua rota direcional e mês do voo; a média é o cancelamento esperado "
           "no mix de passageiros. Só entram trechos de rota-mês com dado na gold (os demais usam média da rota ou da rede, que não é fonte direta).",
           "",
           f"- Global: público no mix do sintético {100*esp_cg:.2f}%; sintético {100*sint_cg:.2f}%; erro {pct_err(sint_cg, esp_cg):+.1f}%. Referência por voo (ponderação anterior): {100*pub_total_voos_l[1]:.2f}% público; sintético sem filtro {100*glob_c:.2f}% ({pct_err(glob_c, pub_total_voos_l[1]):+.1f}%).",
           f"- Fração dos trechos com rota-mês observada na gold: {100*obs_g.mean():.1f}%.",
           "", "| Par | Cancelamento público no mix sint. | Cancelamento sint. | Erro % |", "|---|---|---|---|"]
    for r in v.itertuples():
        md.append(f"| {r.par} | {100*r.c_esp:.2f}% | {100*r.c_sint:.2f}% | {r.c_err:+.1f}% |")
    md += ["", "Cancelamento é evento raro (cerca de 2%): nos pares com 6 a 15 mil trechos o desvio-padrão do sorteio é de 8% a 15% relativo, então erros desse tamanho nos pares são ruído amostral; o global (centenas de milhares de trechos) é o teste relevante.",
           "",
           "**Sobre a coluna 'Azul no par':** é a participação da Azul entre as companhias do par (público). O sintético tem só clientes da Azul e nenhum "
           "concorrente, então ela não é reproduzível por construção e vai apenas como contexto. O que o sintético reproduz é o peso do par no total de trechos da "
           "Azul, comparado ao peso do par no total de assentos da Azul (coluna 'Share do par').",
           "",
           "## Aeroporto de casa x assentos da Azul (tarifas)",
           "",
           f"Casa e pares saem da mesma fonte: assentos vendidos pela Azul em `silver.anac_tarifas` (AZU, {MESES[0]} a {MESES[-1]}): "
           f"{len(f['homes'])} aeroportos de origem candidatos, {clientes['aeroporto_casa'].nunique()} sorteados como casa de ao menos um cliente. Os voos do VRA vão só como referência.",
           "",
           "| Aeroporto | Share de assentos Azul com origem no aeroporto (tarifas) | Share de clientes (casa) | Share de voos Azul (VRA, só referência) |", "|---|---|---|---|"]
    vo = f["voos_origem"]; vo = vo / vo[[a for a in vo.index if a in set(f["homes"])]].sum()
    ass = con.execute("SELECT origem_icao, SUM(assentos)::DOUBLE s FROM anac_tarifas WHERE empresa_icao='AZU' GROUP BY 1").df().set_index("origem_icao")["s"]
    ass = ass[[a_ for a_ in ass.index if a_ in set(f["homes"])]]; ass = ass / ass.sum()
    for a_ in ass.sort_values(ascending=False).head(8).index:
        md.append(f"| {a_} | {100*ass[a_]:.2f}% | {100*hs.get(a_, 0):.2f}% | {100*vo.get(a_, 0):.2f}% |")
    sg = f["saidas_gold"]
    sg_v = sg[sg["volta"] < NM]
    md += ["", "## Saída total e retorno da Azul ao par", "",
           f"`gold.route_exits` marca {len(sg)} pares com saída total; {int(sg['pid'].notna().sum())} têm venda da Azul (AZU) na ANAC Tarifas e entram no sintético "
           f"(os demais são pares só da ACN ou sem venda AZU; P-15). A Azul fica fora do par de `mes_saida` até o mês anterior ao retorno (primeiro mês seguinte com voo do grupo Azul): "
           f"{len(sg_v)} pares voltam na janela ({int(sg_v['pid'].notna().sum())} deles no sintético): "
           + ", ".join(f"{r.par_rota} ({MESES[int(r.ms)]} → {MESES[int(r.volta)]})" for r in sg_v.sort_values("par_rota").itertuples()) + ".",
           "", "## Cobertura das ameaças (clientes distintos)", "",
           f"Duas tabelas: `synthetic_customer_threats` (histórico, mês <= {MESES[T_HIST - 1]}; entrada do modelo e do Radar) e `synthetic_customer_threats_rotulo` "
           f"(período de rótulo, {MESES[T_HIST]} a {MESES[-1]}; nunca entrada de modelo). A = ameaça A grave: 2 eventos de atraso de partida > 60 min ou cancelamento em até 90 dias, data do 2º evento; "
           "B e C = pares reais de `gold.route_exits` e `gold.route_competition` em que o cliente voou nos 12 meses até o mês da ameaça. C é só `queda_tarifa` (a entrada de concorrente saiu da gold, P-05).",
           "", "| Tipo | Detalhe | Tabela | Eventos | Clientes | Primeiro mês | Último mês |", "|---|---|---|---|---|---|---|"]
    for r in det.itertuples():
        md.append(f"| {r.tipo_ameaca} | {r.detalhe} | {'customer_threats' if r.periodo == 'historico' else 'customer_threats_rotulo'} | {r.eventos} | {r.clientes} | {r.ini} | {r.fim} |")
    md += ["", f"Clientes distintos atingidos (as duas tabelas): A {tot_cli['A']}, B {tot_cli['B']}, C {tot_cli['C']} de {N}.", "",
           f"Por nível vigente em {CORTE} (hist. = `synthetic_customer_threats`; todos = inclui `synthetic_customer_threats_rotulo`):", "",
           "| Nível | Clientes | A hist. | B hist. | C hist. | A todos | B todos | C todos |", "|---|---|---|---|---|---|---|---|"]
    for k, r in cob.items():
        md.append(f"| {k} | {r['clientes']} | {r['A_historico']} | {r['B_historico']} | {r['C_historico']} | {r['A_todos']} | {r['B_todos']} | {r['C_todos']} |")
    cortes_, q_ = diag.pop("_cortes"); kappa_ = diag.pop("_kappa")
    md += ["", "## Taxa de evasão por ameaça dentro de cada faixa de frequência (entre elegíveis)", "",
           f"Elegíveis: {n_eleg} (trechos esperados em 6 meses >= {ELEG_MIN:g}); não elegíveis (rótulo nulo): {N - n_eleg}. "
           f"Faixas = tercis da taxa mensal do histórico entre elegíveis: baixa < {cortes_[0]:.3f}, média até {cortes_[1]:.3f}, alta acima (trechos/mês). "
           f"Evasão 'natural' (só acaso) por faixa, usada na calibração: {', '.join(f'{100*x:.1f}%' for x in q_)}. "
           f"Expostos = ameaça no histórico (últimos 6 meses: {MESES[T_HIST - 6]} a {MESES[T_HIST - 1]}); não expostos = sem essa ameaça (podem ter outras). Diferença em pontos percentuais (pp); alvo entre parênteses.", "",
           "| Ameaça (alvo) | Faixa | Expostos | Evasão expostos | Evasão não expostos | Diferença (pp) |", "|---|---|---|---|---|---|"]
    efetivo = []
    for k_, (linhas, alvo, bruto) in diag.items():
        for b_, n_, r1, r0, df_ in linhas:
            md.append(f"| {k_} ({100*alvo:+.0f} pp) | {['baixa', 'média', 'alta'][b_]} | {n_} | {100*r1:.1f}% | {100*r0:.1f}% | {df_:+.1f} |")
        ok_ = [(n_, df_) for _, n_, _, _, df_ in linhas if n_ and not np.isnan(df_)]
        efetivo.append((k_, alvo, sum(n_ for n_, _ in ok_), sum(n_ * d_ for n_, d_ in ok_) / max(sum(n_ for n_, _ in ok_), 1), bruto))
    md += ["", "### Delta efetivo (medido) x nominal", "",
           "Delta efetivo = média das diferenças por faixa ponderada pelos expostos de cada faixa (o que a calibração mira). "
           "Bruto = diferença entre expostos e não expostos sem estratificar por faixa (mistura o efeito da frequência).", "",
           "| Ameaça | Nominal (pp) | Expostos | Delta efetivo (pp) | Bruto (pp) |", "|---|---|---|---|---|"]
    md += [f"| {k_} | {100*a_:+.0f} | {n_} | {d_:+.1f} | {b_:+.1f} |" for k_, a_, n_, d_, b_ in efetivo]
    md += ["", "Ameaças com poucos expostos por faixa (em especial saída total, dezenas de clientes) têm estimativa ruidosa: com n = 30 e taxa perto de 30%, o erro-padrão da diferença é de cerca de 8 pp.",
           "", "Multiplicadores de calibração do efeito (kappa, 1 = delta nominal; ameaça × faixa baixa/média/alta): " + "; ".join(f"{nm_} {np.round(kk_, 2).tolist()}" for nm_, kk_ in zip(diag, kappa_)) + ". Kappa acima de 1 compensa confundidores que reduzem a diferença; abaixo de 1 ou 0, confundidores que já a aumentam (saída de rota reduz trechos e aciona também a tendência de queda).",
           "", f"## Pirâmide de níveis (vigente em {CORTE})", "", "| Nível | Clientes |", "|---|---|"]
    md += [f"| {k_} | {int(c_)} |" for k_, c_ in nv.value_counts().reindex(NIVEIS).items()]
    md += ["", "## Proxy do arquétipo nas tabelas de entrada", "",
           "Distância de variação total média entre P(arquétipo | valor da coluna) e P(arquétipo) (0 = a coluna não informa nada sobre o arquétipo; 1 = proxy perfeito): "
           f"aeroporto_casa {pureza['aeroporto_casa']:.4f}, consentimento_marketing {pureza['consentimento_marketing']:.4f}. "
           "As colunas de comportamento (frequência, antecedência, tarifa) são correlacionadas ao arquétipo por construção, mas as classes se sobrepõem (Gamma, ruído) e nenhuma coluna o identifica sozinha.",
           ""]
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "VALIDACAO_SINTETICO.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print("\n===== RESUMO =====")
    print("clientes por nivel vigente (ano):\n", nivel_ano.to_string())
    print(f"nivel vigente ao fim do historico ({CORTE}):\n", nv.value_counts().reindex(NIVEIS).to_string())
    print(f"evasao: elegiveis={int(base.sum())}, evadiram={int(rot.loc[base,'evasao'].astype(float).sum())}, taxa={100*evas:.2f}%; nulos={N-int(base.sum())} (sem viagem no historico={sem_viagem_hist})")
    print("evasao por nivel:\n", evas_nivel.to_string())
    print("evasao/viajou por arquetipo (validacao):\n", arq_evas.to_string())
    print("S (parou) total:", int(parou.sum()), "| eventos de compra:", n_eventos, "| perdidos (sem rota):", perdidas, "| fora da janela/pos-saida:", fora_janela)
    for k_, v_ in diag.items():
        print("diag", k_, v_)
    print("ameacas por nivel:", cob)
    print("clientes atingidos por tipo:", tot_cli)
    print(det.to_string())
    print(v.round(4).to_string())
    print(v[["par", "c_sint", "c_esp", "c_err"]].round(4).to_string())
    print("cancel mesma ponderacao", sint_cg, esp_cg, pct_err(sint_cg, esp_cg), "frac obs", obs_g.mean())
    print("global tarifa", L["tarifa"].mean(), pub_tarifa_g, "atraso", glob_l, pub_total_voos_l, "cancel", glob_c)
    print("pureza proxy", pureza, base_arq)
    print("delta efetivo:", [(k_, round(d_, 2), round(b_, 2)) for k_, _, _, d_, b_ in efetivo])


if __name__ == "__main__":
    main()
