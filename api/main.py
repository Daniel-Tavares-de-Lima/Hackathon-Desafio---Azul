"""API de integração com CRM: score e próxima melhor ação por cliente. Uso: uvicorn api.main:app --port 8000"""
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
import nba_agent  # noqa: E402
import tools  # noqa: E402

app = FastAPI(title="ÓRBITA · API de score e próxima melhor ação",
              description="Base sintética, visão em 28/02/2026. Nenhum dado real de cliente.")


@app.get("/customers/{cliente_id}/score")
def score(cliente_id: str) -> dict:
    s = tools.get_scores_and_reasons(cliente_id)
    if s is None:
        raise HTTPException(404, "cliente não encontrado")
    return {"cliente_id": cliente_id, "data_corte": tools.DATA_CORTE.date().isoformat(),
            "score_valor_brl": float(s["score_valor_brl"]), "decil_score": int(s["decil_score"]),
            "elegivel_evasao": bool(s["elegivel_evasao"]), "p_evasao": s["p_evasao"],
            "clv_previsto_6m_brl": float(s["clv_previsto_6m_brl"]), "persona": s["persona"], "motivos": s["motivos"]}


@app.post("/customers/{cliente_id}/nba")
def nba(cliente_id: str) -> dict:
    """Decisão do agente. Sempre requer aprovação humana; a API não envia nada ao cliente."""
    try:
        return nba_agent.decidir(cliente_id)
    except nba_agent.ClienteInexistente:  # só cliente inexistente é 404; qualquer outro erro sobe como 500
        raise HTTPException(404, "cliente não encontrado")
