"""21 clientes golden REAIS da base sintética (gold.customer_scores no corte 2026-02-28) com a saída esperada.

Uso: python -I agent/tests/test_golden.py   (também roda com pytest, se instalado)
Se a base for regenerada com outra seed, os ids mudam e este arquivo precisa ser refeito.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -I tira o diretório do script do sys.path
import nba_agent  # noqa: E402

SEM = "sem_acao_automatica"
# (caso, cliente_id, acao esperada, trecho esperado na justificativa)
GOLDEN = [
    ("DEMO 1 · A grave, alto valor, risco alto", "9132e89e-9a62-4c3a-8cb0-51f621090395", "recuperacao_servico", "grave"),
    ("A grave, alto valor, sem consentimento", "f1c16e56-0ad2-412c-9280-c31a55953619", "recuperacao_servico", "grave"),
    ("A grave, alto valor, risco baixo", "c173cf37-20c1-44f0-ba41-f780775eef0e", "recuperacao_servico", "risco baixo"),
    ("A grave, Diamante Unique", "606c726e-1ce1-427d-8a4a-82eb038396bf", "recuperacao_servico", "grave"),
    ("A grave, ROI não positivo", "b6376493-0535-4443-b458-e547d78753e0", SEM, "ROI estimado"),
    ("A grave, baixo valor", "4ddd0765-8c0a-4461-8cb3-6973e7463ab2", SEM, "valor baixo"),
    ("B saída total, conexão via hub", "eb32ac39-7de1-47e0-a57c-973391115a45", "oferta_rota_favorita", "saida_total"),
    ("B saída total, sem alternativa na malha", "00a484c4-16d5-4bfc-8453-c9e3551c0428", "contato_humano", "saida_total"),
    ("B redução", "9d0d79e3-5c53-43a3-b37f-e486b0e000ed", "oferta_rota_favorita", "reducao"),
    ("B redução, sem consentimento", "ee118246-7d20-46ce-828b-23d7a97126c8", "contato_humano", "reducao"),
    ("C queda de tarifa", "82e7f61d-87c1-4cc7-b2ec-c70a1203a29d", "bonus_pontos", "queda_tarifa"),
    ("C queda de tarifa, Diamante Unique", "9c08991e-ecde-4705-ab98-69700a1757b5", "upgrade", "queda_tarifa"),
    ("C sem consentimento", "0f856591-68cf-42b6-98a5-5cecabfe986b", SEM, "consentimento"),
    ("C risco baixo", "3c5f372f-7c1d-4c7d-acb1-75cce3d4f3cd", SEM, "risco baixo"),
    ("DEMO 2 · perto de cair de nível", "85e407cb-e65a-4be9-a5ab-eb6b99cbecd0", "desafio_manutencao_nivel", "perto_de_cair"),
    ("perto de cair, sem consentimento", "38d8fdeb-0635-4de3-8b6d-912e44d501a8", SEM, "consentimento"),
    ("sem regra aplicável, alto valor", "b8421447-a1be-4aa4-a5c5-b495127c8590", SEM, "nenhuma regra"),
    ("sem regra aplicável, baixo valor", "c4e6a4ea-e454-45a0-b398-19ea578ea861", SEM, "nenhuma regra"),
    ("não elegível, alto valor", "7af5666f-ed50-4933-8f55-2917ed21d699", SEM, "não elegível"),
    ("não elegível com A grave", "679c193e-66cd-4adb-bca2-f37f34a223d1", SEM, "não elegível"),
    # Topázio de 2025 com folga < 25% que já voou os 6 trechos em 2026 (meta OU cumprida): não há desafio.
    ("Topázio perto de cair, 0 trechos faltando", "63fa1170-b42d-401e-bdef-932f28c7f16a", SEM, "nenhuma regra"),
]


def checar(caso, cid, acao, trecho):
    out = nba_agent.decidir(cid)
    assert out["acao"] == acao, f"{caso}: esperado {acao}, veio {out['acao']} ({out['justificativa']})"
    assert out["requer_aprovacao_humana"] is True, caso
    assert trecho in out["justificativa"], f"{caso}: '{trecho}' fora da justificativa: {out['justificativa']}"
    if acao == SEM:
        assert not out["regras_citadas"] and out["mensagem"] is None, caso
    else:
        # Contato humano não promete benefício, então pode não citar regra; as demais ações sempre citam.
        assert (out["regras_citadas"] or acao == "contato_humano") and all(
            r["url"].startswith("https://") and r["trecho"] for r in out["regras_citadas"]), caso
        assert out["custo_estimado"] > 0 and out["roi_estimado"] > 0 and out["mensagem"], caso
    return out


def test_golden():
    for g in GOLDEN:
        checar(*g)
    # Gatilhos mínimos do demo citam a regra certa.
    a = nba_agent.decidir(GOLDEN[0][1])
    assert any(r["id"] == "anac_assistencia_material" for r in a["regras_citadas"]), a["regras_citadas"]
    assert a["decisao_comercial"]["base"] == "decisão comercial (sem regra pública)", a
    n = nba_agent.decidir(GOLDEN[14][1])
    assert any(r["id"] == "criterios_niveis_2026" for r in n["regras_citadas"]), n["regras_citadas"]
    assert "em 2027" in n["mensagem"] and "faltam 0" not in n["mensagem"].lower(), n["mensagem"]
    # Contato humano de rota órfã não cita a regra ANAC de atraso.
    h = nba_agent.decidir(GOLDEN[7][1])
    assert all(r["id"] != "anac_informacao_reacomodacao" for r in h["regras_citadas"]), h["regras_citadas"]
    test_contextos_fixos()
    test_llm_adversarial()


class _RespostaFalsa:
    def __init__(self, texto):
        self.corpo = json.dumps({"response": texto}).encode()

    def read(self):
        return self.corpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_contextos_fixos():
    """Todo contexto fixo aprovado é limpo: sem dígito, valor, benefício, termo do catálogo nem promessa."""
    for acao, opcoes in nba_agent.CONTEXTOS.items():
        assert 3 <= len(opcoes) <= 9, acao  # o índice do LLM é um único dígito
        for c in opcoes:
            assert not nba_agent.guardrails.checar_contexto(c, c), (acao, c)
            assert not nba_agent.guardrails.checar_texto(c, set()), (acao, c)


def test_llm_adversarial():
    """Ollama falso: o LLM só escolhe o índice do contexto. Qualquer resposta que não seja exatamente um dígito
    válido cai no contexto padrão; nenhum texto do LLM chega à mensagem. "2" escolhe o contexto 2."""
    demo2 = GOLDEN[14][1]
    base = nba_agent.decidir(demo2)  # sem LLM: contexto padrão
    oferta, opcoes = base["mensagem_oferta"], nba_agent.CONTEXTOS["desafio_manutencao_nivel"]
    assert base["mensagem"] == f"{opcoes[0]} {oferta}" and base["contexto_indice"] == 1
    original, env = nba_agent.urllib.request.urlopen, os.environ.get("LLM_PROVIDER")
    os.environ["LLM_PROVIDER"] = "ollama"
    try:
        for ruim in ("Acesso VIP para você", "2 e passagem por nossa conta", "3.", "7", "0", "12", "١"):
            nba_agent.urllib.request.urlopen = lambda req, timeout=None, t=ruim: _RespostaFalsa(t)
            d = nba_agent.decidir(demo2)
            assert d["mensagem"] == base["mensagem"] and d["contexto_indice"] == 1, (ruim, d["mensagem"])
        nba_agent.urllib.request.urlopen = lambda req, timeout=None: _RespostaFalsa(" 2\n")
        d = nba_agent.decidir(demo2)
        assert d["contexto_indice"] == 2 and d["mensagem"] == f"{opcoes[1]} {oferta}", d["mensagem"]
    finally:
        nba_agent.urllib.request.urlopen = original
        if env is None:
            os.environ.pop("LLM_PROVIDER")
        else:
            os.environ["LLM_PROVIDER"] = env


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    falhas = 0
    for g in GOLDEN:
        try:
            out = checar(*g)
            print(f"ok    {g[0]:<45} {out['acao']}")
        except AssertionError as e:
            falhas += 1
            print(f"FALHA {e}")
    assert not falhas, f"{falhas} golden falharam"
    test_golden()
    print(f"golden ok ({len(GOLDEN)}/{len(GOLDEN)})")
