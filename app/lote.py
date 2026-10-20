"""Roda o agente NBA em lote e grava app/.cache/nba_lote.parquet (usado por Personas e Simulador de ROI).

Uso: python -I app/lote.py   (pula se o arquivo já for mais novo que gold.customer_scores e que agent/*.py e agent/kb/*.md)
Público: elegíveis à evasão com decil 1 a 5. Fora disso o próprio agente abstém (sem p_evasao ou valor baixo).
~13 ms por cliente; com 4 processos, ~1 minuto para ~12.700 clientes.
"""
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")  # 1 thread por processo: sem isso o OpenBLAS estoura a memória

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
SCORES = ROOT / "data" / "gold" / "customer_scores" / "data.parquet"
SAIDA = Path(__file__).resolve().parent / ".cache" / "nba_lote.parquet"
CAMPOS = ["cliente_id", "acao", "gatilho", "roi_estimado", "custo_estimado", "canal"]


def _decidir(ids: list[str]) -> list[dict]:
    import nba_agent
    return [{k: d[k] for k in CAMPOS} for d in map(nba_agent.decidir, ids)]


def _entradas_mtime() -> float:
    """Mais recente entre a gold de scores e o código/KB do agente: qualquer mudança refaz o lote."""
    agente = ROOT / "agent"
    arquivos = [SCORES, *agente.glob("*.py"), *(agente / "kb").glob("*.md")]
    return max(a.stat().st_mtime for a in arquivos)


def defasado() -> bool:
    """Cache ausente ou mais velho que o score, o código do agente ou a KB (mesmo critério no app)."""
    return not SAIDA.exists() or SAIDA.stat().st_mtime <= _entradas_mtime()


def gerar(forcar: bool = False) -> Path:
    if not forcar and not defasado():
        return SAIDA
    s = pd.read_parquet(SCORES, columns=["cliente_id", "elegivel_evasao", "decil_score"])
    ids = s.loc[s.elegivel_evasao & (s.decil_score <= 5), "cliente_id"].tolist()
    blocos = [ids[i:i + 500] for i in range(0, len(ids), 500)]
    with ProcessPoolExecutor(max_workers=min(4, os.cpu_count() or 1)) as ex:
        linhas = [d for parte in ex.map(_decidir, blocos) for d in parte]
    SAIDA.parent.mkdir(exist_ok=True)
    pd.DataFrame(linhas).to_parquet(SAIDA, index=False)
    return SAIDA


if __name__ == "__main__":
    print(gerar(forcar="--forcar" in sys.argv))
