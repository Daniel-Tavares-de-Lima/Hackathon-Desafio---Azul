"""Silver (Parquet) -> gold: executa pipelines/sql/*.sql em DuckDB e grava data/gold/<tabela>/data.parquet.

Uso: python -I pipelines/build_gold.py
O SQL e padrao ANSI (roda igual no Snowflake); so este runner e especifico de DuckDB.
Depois do build valida cada Parquet contra contracts/gold_<tabela>.yaml (colunas, tipos, NULL) e a janela de meses;
so substitui a gold publicada se tudo passar.
"""
import os
import re
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
SILVER = ROOT / os.environ.get("SILVER_DIR", "data/silver")
GOLD = ROOT / os.environ.get("GOLD_DIR", "data/gold")
END_MONTH = os.environ.get("ANAC_END_MONTH", "2026-08")
N_MONTHS = int(os.environ.get("ANAC_MONTHS", "24"))
TABELAS = ["route_disruptions", "route_exits", "route_competition"]

# Tipo do contrato -> tipo que o DuckDB devolve ao ler o Parquet. VARCHAR(n) vira VARCHAR (Parquet nao guarda tamanho).
ALIAS = {"INT": "INTEGER", "INT4": "INTEGER", "INT8": "BIGINT", "TEXT": "VARCHAR", "STRING": "VARCHAR", "BOOL": "BOOLEAN"}


def ler_contrato(path):
    """Le o YAML do contrato sem PyYAML: storage.path, grain e columns (uma coluna por linha, estilo {name: ...})."""
    txt = Path(path).read_text(encoding="utf-8")
    cols = []
    for m in re.finditer(r'^\s*-\s*\{name:\s*(\w+),\s*type:\s*(?:"([^"]+)"|([^,}]+)),\s*nullable:\s*(true|false)',
                         txt, flags=re.M):
        cols.append((m[1], (m[2] or m[3]).strip(), m[4] == "true"))
    n_linhas = len(re.findall(r"^\s*-\s*\{name:", txt, flags=re.M))
    if n_linhas != len(cols):
        raise ValueError(f"{path}: {n_linhas - len(cols)} coluna(s) fora do formato '- {{name, type, nullable}}'")
    grain = re.search(r"^grain:\s*\[([^\]]*)\]", txt, flags=re.M)[1]
    return {
        "path": re.search(r"^\s+path:\s*(\S+)", txt, flags=re.M)[1],
        "grain": [g.strip() for g in grain.split(",")],
        "columns": cols,
    }


def tipo_norm(t):
    t = re.sub(r"\s+", "", t.upper())
    t = re.sub(r"^VARCHAR\(\d+\)$", "VARCHAR", t)
    return ALIAS.get(t, t)


def checar_contrato(contrato, parquet=None, con=None):
    """Lista de erros (vazia = ok): colunas na mesma ordem, tipo compativel e zero NULL nas colunas nullable: false.
    parquet: arquivo a checar; por padrao o storage.path do contrato (particao hive 'AAAA-MM' vira '*')."""
    c = ler_contrato(contrato)
    alvo = Path(parquet) if parquet else ROOT / c["path"].replace("AAAA-MM", "*")
    con = con or duckdb.connect()
    src = f"read_parquet('{alvo.as_posix().replace(chr(39), chr(39) * 2)}', hive_partitioning=true)"
    real = [(r[0], r[1]) for r in con.execute(f"DESCRIBE SELECT * FROM {src}").fetchall()]
    erros = []
    esperado = [n for n, _, _ in c["columns"]]
    if [n for n, _ in real] != esperado:
        erros.append(f"colunas: contrato={esperado} parquet={[n for n, _ in real]}")
    tipos = dict(real)
    for nome, tipo, nulo in c["columns"]:
        if nome not in tipos:
            continue
        if tipo_norm(tipo) != tipo_norm(tipos[nome]):
            erros.append(f"{nome}: tipo contrato={tipo} parquet={tipos[nome]}")
    obrig = [n for n, _, nulo in c["columns"] if not nulo and n in tipos]
    if obrig:
        nulos = con.execute("SELECT " + ", ".join(f'COUNT(*) - COUNT("{n}")' for n in obrig) + f" FROM {src}").fetchone()
        erros += [f"{n}: {k} NULL em coluna nullable: false" for n, k in zip(obrig, nulos) if k]
    return erros


def meses_esperados():
    y, m = map(int, END_MONTH.split("-"))
    fim = y * 12 + m - 1
    return [f"{i // 12:04d}-{i % 12 + 1:02d}" for i in range(fim - N_MONTHS + 1, fim + 1)]


def checks(con):
    def q(s):
        return con.execute(s).fetchone()[0]

    dup = "SELECT COUNT(*) FROM (SELECT 1 FROM gold.{t} GROUP BY {k} HAVING COUNT(*) > 1)"
    assert q("SELECT COUNT(*) FROM gold.route_disruptions WHERE voos_realizados + voos_cancelados <> voos_previstos") == 0
    assert q(dup.format(t="route_disruptions", k="ano_mes, origem_icao, destino_icao, empresa_icao")) == 0
    assert q(dup.format(t="route_exits", k="ano_mes, origem_icao, destino_icao")) == 0
    assert q(dup.format(t="route_competition", k="ano_mes, origem_icao, destino_icao, empresa_icao")) == 0
    assert q("SELECT COUNT(*) FROM gold.route_exits WHERE saida_total AND reducao") == 0
    # saida_total so a partir de mes_saida+2 (mes_saida..mes_saida+2 zerados) e mes_saida preenchido sempre que marca
    assert q("SELECT COUNT(*) FROM gold.route_exits WHERE saida_total AND mes_saida IS NULL") == 0
    assert q("""SELECT COUNT(*) FROM gold.route_exits WHERE saida_total AND
                CAST(SUBSTR(ano_mes, 1, 4) AS INTEGER) * 12 + CAST(SUBSTR(ano_mes, 6, 2) AS INTEGER)
                < CAST(SUBSTR(mes_saida, 1, 4) AS INTEGER) * 12 + CAST(SUBSTR(mes_saida, 6, 2) AS INTEGER) + 2""") == 0
    assert q("SELECT COUNT(*) FROM gold.route_competition WHERE queda_tarifa AND revisar_amostra") == 0
    assert q("""SELECT COUNT(*) FROM gold.route_competition WHERE empresa_icao IN ('AZU', 'ACN')
                AND (queda_tarifa OR revisar_amostra)""") == 0
    # shares de cada rota/mes fecham em 100 (tolerancia de arredondamento por companhia)
    assert q("SELECT COUNT(*) FROM (SELECT SUM(participacao_assentos_pct) s FROM gold.route_competition "
             "GROUP BY ano_mes, origem_icao, destino_icao) WHERE ABS(s - 100) > 0.5") == 0
    # janela: N_MONTHS meses contiguos terminando em END_MONTH, sem faltante, em todas as gold
    esperado = meses_esperados()
    for t in TABELAS:
        got = [r[0] for r in con.execute(f"SELECT DISTINCT ano_mes FROM gold.{t} ORDER BY 1").fetchall()]
        assert got == esperado, f"gold.{t}: meses {got[:1]}..{got[-1:]} ({len(got)}) != {esperado[0]}..{esperado[-1]}"


def main():
    con = duckdb.connect()
    con.execute("CREATE SCHEMA silver")
    con.execute("CREATE SCHEMA gold")
    for t in ("anac_vra", "anac_tarifas"):
        p = (SILVER / t / "*" / "data.parquet").as_posix().replace("'", "''")
        con.execute(f"CREATE VIEW silver.{t} AS SELECT * FROM read_parquet('{p}', hive_partitioning=true)")
    for t in TABELAS:
        con.execute((ROOT / "pipelines" / "sql" / f"{t}.sql").read_text(encoding="utf-8"))
    checks(con)
    tmps = {}
    for t in TABELAS:
        contrato = ROOT / "contracts" / f"gold_{t}.yaml"
        out = GOLD / t / "data.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp")
        ordem = ", ".join(ler_contrato(contrato)["grain"])
        con.execute(f"COPY (SELECT * FROM gold.{t} ORDER BY {ordem}) TO '{tmp.as_posix()}' "
                    f"(FORMAT parquet, COMPRESSION zstd)")
        erros = checar_contrato(contrato, tmp, con)
        assert not erros, f"gold.{t} fora do contrato:\n  " + "\n  ".join(erros)
        tmps[t] = (tmp, out)
    for t, (tmp, out) in tmps.items():
        os.replace(tmp, out)
        n = con.execute(f"SELECT COUNT(*) FROM gold.{t}").fetchone()[0]
        print(f"gold.{t}: {n} linhas -> {out.relative_to(ROOT).as_posix()} (contrato ok)")


if __name__ == "__main__":
    main()
