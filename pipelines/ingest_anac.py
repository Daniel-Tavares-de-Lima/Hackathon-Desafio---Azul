"""Ingestao ANAC (fontes publicas oficiais) -> bronze CSV bruto -> silver Parquet tipado.

Fontes:
  tarifas : https://sas.anac.gov.br/sas/tarifadomestica/<ano>/<AAAAMM>.csv   (Tarifas Aereas Domesticas)
  vra     : https://siros.anac.gov.br/siros/registros/diversos/vra/<ano>/VRA_<ano>_<MM>.csv  (Voo Regular Ativo)

Uso:  python -I pipelines/ingest_anac.py [tarifas|vra|all|selftest] [--force]
Idempotente: pula download se o CSV ja existe no bronze; reconstroi a particao silver
so se ela faltar ou for mais velha que o CSV bronze (--force reconstroi tudo).
Arquivos baixados sao dados nao confiaveis: so sao lidos como CSV pelo duckdb, nunca executados.
"""
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env(path=ROOT / ".env"):
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


load_env()
BRONZE = ROOT / os.environ.get("BRONZE_DIR", "data/bronze")
SILVER = ROOT / os.environ.get("SILVER_DIR", "data/silver")
END_MONTH = os.environ.get("ANAC_END_MONTH", "2026-09")  # fim da janela alvo (AAAA-MM)
N_MONTHS = int(os.environ.get("ANAC_MONTHS", "24"))

# Prefixos ICAO de aerodromos brasileiros. Rota domestica = origem E destino com esses prefixos.
BR_ICAO = ("SB", "SD", "SI", "SJ", "SN", "SS", "SW")

SOURCES = {
    "tarifas": {
        "listing": "https://sas.anac.gov.br/sas/tarifadomestica/{y}/",
        "file_re": r'HREF="(/sas/tarifadomestica/{y}/({y}\d{{2}})[^"]*\.csv)"',
        "host": "https://sas.anac.gov.br",
        "bronze_name": "tarifas_{ym}.csv",
        "cols": {  # header normalizado -> nome silver
            "nr_ano_referencia": "ano", "nr_mes_referencia": "mes", "sg_empresa_icao": "empresa_icao",
            "sg_icao_origem": "origem_icao", "sg_icao_destino": "destino_icao",
            "nr_tarifa": "tarifa", "nr_assentos": "assentos",
            # layout alternativo publicado em 2024-10..2025-02
            "ano": "ano", "mes": "mes", "empresa": "empresa_icao", "origem": "origem_icao",
            "destino": "destino_icao", "tarifa": "tarifa", "assentos": "assentos",
        },
    },
    "vra": {
        "listing": "https://siros.anac.gov.br/siros/registros/diversos/vra/{y}/",
        "file_re": r'HREF="(/siros/registros/diversos/vra/{y}/VRA_{y}_(\d{{2}})\.csv)"',
        "host": "https://siros.anac.gov.br",
        "bronze_name": "VRA_{ym}.csv",
        "cols": {
            "sigla_icao_empresa_aerea": "empresa_icao", "empresa_aerea": "empresa_nome",
            "numero_voo": "numero_voo", "codigo_di": "codigo_di", "codigo_tipo_linha": "tipo_linha",
            "modelo_equipamento": "modelo_equipamento", "numero_de_assentos": "assentos",
            "sigla_icao_aeroporto_origem": "origem_icao", "descricao_aeroporto_origem": "origem_descricao",
            "partida_prevista": "partida_prevista", "partida_real": "partida_real",
            "sigla_icao_aeroporto_destino": "destino_icao", "descricao_aeroporto_destino": "destino_descricao",
            "chegada_prevista": "chegada_prevista", "chegada_real": "chegada_real",
            "situacao_voo": "situacao_voo", "justificativa": "justificativa", "referencia": "referencia",
            "situacao_partida": "situacao_partida", "situacao_chegada": "situacao_chegada",
            "codeshare": "codeshare",
        },
    },
}


def snake(s):
    s = unicodedata.normalize("NFKD", s.replace("﻿", "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def br_decimal(c):
    """'1.234,56' / '1234,5' / '1234.5' -> DECIMAL(12,2). Virgula presente => ponto e milhar."""
    return (f"TRY_CAST(CASE WHEN {c} LIKE '%,%' THEN replace(replace({c}, '.', ''), ',', '.') "
            f"ELSE {c} END AS DECIMAL(12,2))")


def txt(c):
    return f"NULLIF(TRIM({c}), '')"


def month_add(ym, k):
    y, m = map(int, ym.split("-"))
    t = y * 12 + (m - 1) + k
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def http_get(url, timeout=180, tries=5):
    """Servidores ANAC derrubam conexao com frequencia (WinError 10054): retry com backoff."""
    req = urllib.request.Request(url, headers={"User-Agent": "orbita-ingest/1.0"})
    for i in range(tries):
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError:
            raise
        except OSError as e:
            if i == tries - 1:
                raise
            print(f"  retry {i + 1}/{tries - 1} {url}: {e}")
            time.sleep(5 * 2 ** i)


def discover(src):
    """{AAAA-MM: url} a partir das listagens oficiais de diretorio (nome do arquivo varia, ex. '202605 (1).csv')."""
    cfg, found = SOURCES[src], {}
    end_y = int(END_MONTH[:4])
    for y in range(end_y - N_MONTHS // 12 - 1, end_y + 1):
        try:
            html = http_get(cfg["listing"].format(y=y), timeout=120).read().decode("utf-8", "replace")
        except Exception as e:  # ano ainda nao publicado / fora do ar: registra e segue
            print(f"[{src}] listagem {y} indisponivel: {e}")
            continue
        for href, tail in re.findall(cfg["file_re"].format(y=y), html, flags=re.I):
            ym = f"{y}-{tail[-2:]}"
            found.setdefault(ym, cfg["host"] + href.replace(" ", "%20"))
    return found


def window(found):
    published = sorted(m for m in found if m <= END_MONTH)
    if not published:
        sys.exit("nenhum mes publicado encontrado")
    last = published[-1]
    months = [month_add(last, -k) for k in range(N_MONTHS - 1, -1, -1)]
    return months, [m for m in months if m not in found]


def download(url, dest):
    if dest.exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    for i in range(5):
        try:
            with http_get(url) as r, open(tmp, "wb") as f:
                expected = int(r.headers.get("Content-Length") or -1)
                while chunk := r.read(1 << 20):
                    f.write(chunk)
            if expected >= 0 and tmp.stat().st_size != expected:
                raise IOError(f"download incompleto ({tmp.stat().st_size}/{expected} bytes)")
            os.replace(tmp, dest)
            return True
        except urllib.error.HTTPError:
            raise
        except OSError as e:  # conexao caiu no meio do corpo
            if i == 4:
                raise
            print(f"  retry download {i + 1}/4 {url}: {e}")
            time.sleep(5 * 2 ** i)


def detect_encoding(path):
    try:
        with open(path, encoding="utf-8") as f:
            while f.read(1 << 20):
                pass
        return "utf-8"
    except UnicodeDecodeError:
        return "latin-1"  # ANAC legado: cp1252/latin-1


def select_sql(src):
    dom = (f"substr(origem_icao, 1, 2) IN {BR_ICAO} AND substr(destino_icao, 1, 2) IN {BR_ICAO}")
    if src == "tarifas":
        return f"""
        SELECT CAST(ano AS SMALLINT) AS ano, CAST(mes AS SMALLINT) AS mes,
               make_date(CAST(ano AS INTEGER), CAST(mes AS INTEGER), 1) AS mes_referencia,
               {txt('empresa_icao')} AS empresa_icao, {txt('origem_icao')} AS origem_icao,
               {txt('destino_icao')} AS destino_icao, {br_decimal('tarifa')} AS tarifa,
               TRY_CAST(assentos AS INTEGER) AS assentos
        FROM raw WHERE {dom}"""
    ts = lambda c: f"try_strptime({txt(c)}, ['%d/%m/%Y %H:%M', '%d/%m/%Y %H:%M:%S'])"
    return f"""
        WITH t AS (
          SELECT {txt('empresa_icao')} AS empresa_icao, {txt('empresa_nome')} AS empresa_nome,
                 {txt('numero_voo')} AS numero_voo, {txt('codigo_di')} AS codigo_di,
                 {txt('tipo_linha')} AS tipo_linha, {txt('modelo_equipamento')} AS modelo_equipamento,
                 TRY_CAST(assentos AS INTEGER) AS assentos,
                 {txt('origem_icao')} AS origem_icao, {txt('origem_descricao')} AS origem_descricao,
                 {txt('destino_icao')} AS destino_icao, {txt('destino_descricao')} AS destino_descricao,
                 {ts('partida_prevista')} AS partida_prevista, {ts('partida_real')} AS partida_real,
                 {ts('chegada_prevista')} AS chegada_prevista, {ts('chegada_real')} AS chegada_real,
                 upper({txt('situacao_voo')}) AS situacao_voo, {txt('justificativa')} AS justificativa,
                 CAST({ts('referencia')} AS DATE) AS data_referencia,
                 {txt('situacao_partida')} AS situacao_partida, {txt('situacao_chegada')} AS situacao_chegada,
                 {txt('codeshare')} AS codeshare
          FROM raw)
        SELECT *, date_diff('minute', partida_prevista, partida_real) AS atraso_partida_min,
                  date_diff('minute', chegada_prevista, chegada_real) AS atraso_chegada_min
        FROM t WHERE {dom}"""


def to_silver(con, src, ym, csv, out):
    enc = detect_encoding(csv)
    with open(csv, encoding=enc) as f:
        header = [snake(h) for h in f.readline().rstrip("\r\n").split(";")]
    cmap = SOURCES[src]["cols"]  # alias de header -> nome silver
    names = [cmap.get(h, h) for h in header]
    missing = set(cmap.values()) - set(names)
    if missing or len(set(names)) != len(names):
        raise ValueError(f"{csv.name}: layout mudou, faltam colunas {sorted(missing)} (header={header})")
    p = str(csv).replace("'", "''")
    con.execute(f"""CREATE OR REPLACE TEMP VIEW raw AS SELECT * FROM read_csv('{p}', delim=';', header=true,
                    all_varchar=true, encoding='{enc}', names={names}, quote='"', null_padding=true)""")
    n_raw = con.execute("SELECT count(*) FROM raw").fetchone()[0]
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    con.execute(f"COPY ({select_sql(src)}) TO '{str(tmp).replace(chr(39), chr(39) * 2)}' "
                f"(FORMAT parquet, COMPRESSION zstd)")
    os.replace(tmp, out)
    n_out = con.execute(f"SELECT count(*) FROM read_parquet('{str(out).replace(chr(39), chr(39) * 2)}')").fetchone()[0]
    print(f"[{src}] {ym} enc={enc} bronze={n_raw} silver={n_out} recortadas_nao_domesticas={n_raw - n_out}")


def run(src, force=False):
    import duckdb
    found = discover(src)
    months, missing = window(found)
    print(f"[{src}] janela {months[0]}..{months[-1]} ({len(months)} meses); faltantes: {missing or 'nenhum'}")
    bdir, sdir = BRONZE / f"anac_{src}", SILVER / f"anac_{src}"
    con = duckdb.connect()
    for ym in months:
        if ym in missing:
            continue
        csv = bdir / SOURCES[src]["bronze_name"].format(ym=ym.replace("-", ""))
        if download(found[ym], csv):
            print(f"[{src}] baixado {csv.name} <- {found[ym]}")
        out = sdir / f"ano_mes={ym}" / "data.parquet"
        if force or not out.exists() or out.stat().st_mtime < csv.stat().st_mtime:
            to_silver(con, src, ym, csv, out)
    # silver e derivado: remove particoes que sairam da janela (bronze fica intocado)
    for part in sdir.glob("ano_mes=*"):
        if part.name.split("=", 1)[1] not in months:
            for f in part.iterdir():
                f.unlink()
            part.rmdir()
            print(f"[{src}] removida particao fora da janela: {part.name}")


def selftest():
    import duckdb
    assert snake("Descrição Aeroporto Origem") == "descricao_aeroporto_origem"
    assert snake("﻿Sigla ICAO Empresa Aérea") == "sigla_icao_empresa_aerea"
    assert month_add("2026-08", -23) == "2024-09" and month_add("2024-12", 1) == "2025-01"
    con = duckdb.connect()
    got = [con.execute(f"SELECT {br_decimal(repr(v))}").fetchone()[0] for v in ("1.234,56", "3651,1", "800.5")]
    assert [float(g) for g in got] == [1234.56, 3651.1, 800.5], got
    print("selftest ok")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    what = args[0] if args else "all"
    if what == "selftest":
        selftest()
    else:
        for s in (SOURCES if what == "all" else [what]):
            run(s, force="--force" in sys.argv)
