"""Contratos x Parquet real: colunas iguais (mesma ordem), tipo compatível e zero NULL em coluna nullable: false.

Uso: python -I tests/test_contratos.py   (também roda com pytest, se instalado)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))  # -I tira o diretório do script do sys.path
from build_gold import checar_contrato  # noqa: E402

PADROES = ["silver_*.yaml", "gold_*.yaml", "synthetic_*.yaml"]


def test_contratos():
    contratos = sorted(p for padrao in PADROES for p in (ROOT / "contracts").glob(padrao))
    assert contratos, "nenhum contrato encontrado"
    falhas = {}
    for c in contratos:
        erros = checar_contrato(c)
        print(f"{'ok   ' if not erros else 'FALHA'} {c.name}")
        if erros:
            falhas[c.name] = erros
    assert not falhas, "\n".join(f"{k}:\n  " + "\n  ".join(v) for k, v in falhas.items())


if __name__ == "__main__":
    test_contratos()
    print("contratos ok")
