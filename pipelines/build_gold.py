"""Silver (Parquet) -> gold: executa pipelines/sql/*.sql em DuckDB e grava data/gold/<tabela>/data.parquet.

Uso: python -I pipelines/build_gold.py
O SQL e padrao ANSI (roda igual no Snowflake); so este runner e especifico de DuckDB.
"""
import os
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
SILVER = ROOT / os.environ.get("SILVER_DIR", "data/silver")
GOLD = ROOT / os.environ.get("GOLD_DIR", "data/gold")
TABELAS = ["route_disruptions", "route_exits", "route_competition"]


def checks(con):
    def q(s):
        return con.execute(s).fetchone()[0]

    dup = "SELECT COUNT(*) FROM (SELECT 1 FROM gold.{t} GROUP BY {k} HAVING COUNT(*) > 1)"
    assert q("SELECT COUNT(*) FROM gold.route_disruptions WHERE voos_realizados + voos_cancelados <> voos_previstos") == 0
    assert q(dup.format(t="route_disruptions", k="ano_mes, origem_icao, destino_icao, empresa_icao")) == 0
    assert q(dup.format(t="route_exits", k="ano_mes, origem_icao, destino_icao")) == 0
    assert q(dup.format(t="route_competition", k="ano_mes, origem_icao, destino_icao, empresa_icao")) == 0
    assert q("SELECT COUNT(*) FROM gold.route_exits WHERE saida_total AND reducao") == 0
    # shares de cada rota/mes fecham em 100 (tolerancia de arredondamento por companhia)
    assert q("SELECT COUNT(*) FROM (SELECT SUM(participacao_assentos_pct) s FROM gold.route_competition "
             "GROUP BY ano_mes, origem_icao, destino_icao) WHERE ABS(s - 100) > 0.5") == 0


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
    for t in TABELAS:
        out = GOLD / t / "data.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp")
        con.execute(f"COPY gold.{t} TO '{tmp.as_posix()}' (FORMAT parquet, COMPRESSION zstd)")
        os.replace(tmp, out)
        n = con.execute(f"SELECT COUNT(*) FROM gold.{t}").fetchone()[0]
        print(f"gold.{t}: {n} linhas -> {out.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
