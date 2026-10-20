"""Teste da API com TestClient. Uso: python -I api/test_api.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -I tira a raiz do sys.path
from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402

DEMO_A = "9132e89e-9a62-4c3a-8cb0-51f621090395"

if __name__ == "__main__":
    c = TestClient(app)
    r = c.get(f"/customers/{DEMO_A}/score")
    assert r.status_code == 200, r.text
    s = r.json()
    assert 0 <= s["p_evasao"] <= 1 and s["clv_previsto_6m_brl"] > 0 and s["decil_score"] == 1
    assert s["persona"] and len(s["motivos"]) == 3 and "regiao_origem" not in s
    r = c.post(f"/customers/{DEMO_A}/nba")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["acao"] == "recuperacao_servico" and d["requer_aprovacao_humana"] and d["regras_citadas"], d
    assert d["roi_estimado"] > 0 and d["mensagem"]
    assert c.get("/customers/nao-existe/score").status_code == 404
    assert c.post("/customers/nao-existe/nba").status_code == 404
    print("api ok: score, nba e 404")
