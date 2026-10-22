"""Copiloto de Relacionamento: Próxima Melhor Ação (NBA) por cliente, determinística e com custo zero.

Uso: python -I agent/nba_agent.py <cliente_id>   (imprime o JSON da decisão)

A DECISÃO é por regras + catálogo fechado + guardrails, sem LLM. A mensagem = contexto fixo aprovado + oferta do
texto-modelo, em PT-BR. Com LLM_PROVIDER=nenhum (padrão) usa o 1º contexto; com LLM_PROVIDER=ollama, um modelo local
só ESCOLHE o índice do contexto (tom) e nada do que ele escreve chega à mensagem. Premissas em docs/PREMISSAS.md (P-17).
"""
import json
import os
import re
import sys
import urllib.request
from functools import lru_cache
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I tira o diretório do script do sys.path
import guardrails  # noqa: E402
import tools  # noqa: E402

FOLGA_PERTO_DE_CAIR = 0.25  # P-11 / P-13
MARKETING = {"oferta_rota_favorita", "bonus_pontos", "upgrade", "desafio_manutencao_nivel"}


def _env(nome: str, padrao: str) -> str:
    """Variável de ambiente ou, na falta, linha do .env da raiz."""
    if nome in os.environ:
        return os.environ[nome]
    arq = tools.ROOT / ".env"
    if arq.exists():
        for linha in arq.read_text(encoding="utf-8").splitlines():
            if linha.startswith(f"{nome}="):
                return linha.split("=", 1)[1].strip()
    return padrao


def faixa_valor(decil: int) -> str:
    return "alto" if decil <= 2 else "medio" if decil <= 5 else "baixo"


def faixa_risco(p: float) -> str:
    return "alto" if p >= 0.35 else "medio" if p >= 0.20 else "baixo"


# --- Só redação: nomes legíveis e números no padrão brasileiro. Nada aqui entra na decisão. ---
NOME_GATILHO = {
    "grave_2_eventos_90d": "dois atrasos graves em 90 dias",
    "saida_total": "saída total da Azul na rota",
    "reducao": "redução de oferta da Azul na rota",
    "queda_tarifa": "queda de tarifa de concorrente na rota",
    "perto_de_cair_de_nivel": "perto de cair de nível",
}
NOME_ACAO = {
    "recuperacao_servico": "recuperação de serviço",
    "oferta_rota_favorita": "oferta na rota favorita",
    "bonus_pontos": "bônus de pontos",
    "upgrade": "upgrade com pontos",
    "desafio_manutencao_nivel": "desafio de manutenção de nível",
    "contato_humano": "contato humano",
}
NOME_FAIXA = {"alto": "alto", "medio": "médio", "baixo": "baixo"}
_MINUSCULAS = {"de", "da", "do", "das", "dos", "e"}


def br(v: float, casas: int = 0) -> str:
    """1234.5 -> '1.234,5' (milhar com ponto, decimal com vírgula)."""
    return f"{v:,.{casas}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def faixa_decil(d: int) -> str:
    """Decil do score em português: 1 = 'entre os 10% de maior valor'."""
    return "entre os 10% de maior valor" if d == 1 else f"na faixa de {10 * (d - 1)}% a {10 * d}% de maior valor"


@lru_cache(maxsize=1)
def _cidades() -> dict:
    """ICAO -> cidade, da descrição publicada no VRA da ANAC ('AEROPORTO - CIDADE - UF - BRASIL')."""
    try:
        v = pd.read_parquet(tools.SILVER / "anac_vra", columns=["origem_icao", "origem_descricao"])
    except Exception:  # sem silver do VRA: a mensagem fica com o código ICAO
        return {}
    v = v[v.origem_descricao.str.count(" - ") >= 3]
    cid = v.origem_descricao.str.rsplit(" - ", n=3).str[1].str.strip()
    nomes = cid.groupby(v.origem_icao).agg(lambda x: x.mode().iloc[0])
    return {k: " ".join(w.lower() if w.lower() in _MINUSCULAS else w.capitalize() for w in n.split())
            for k, n in nomes.items()}


def cidade(icao: str) -> str:
    """Nome da cidade do aeroporto; volta o código se faltar o nome ou se ele tropeçar no guardrail
    (ex.: 'Cruzeiro do Sul' casa com o termo de região 'sul')."""
    nome = _cidades().get(icao)
    return nome if nome and not guardrails.checar_texto(nome, set()) else icao


def rota(par_rota: str) -> str:
    a, b = par_rota.split("-")
    return f"{cidade(a)}–{cidade(b)}"


def abster(cliente_id: str, motivo: str, gatilho=None) -> dict:
    return {"cliente_id": cliente_id, "acao": "sem_acao_automatica", "gatilho": gatilho,
            "justificativa": f"Sem ação automática: {motivo}. Encaminhar para análise humana.",
            "regras_citadas": [], "decisao_comercial": None, "roi_estimado": None, "custo_estimado": 0.0,
            "mensagem": None, "mensagem_oferta": None, "contexto_indice": None,
            "canal": None, "requer_aprovacao_humana": True}


def escolher_gatilho(perfil: dict, ameacas: list[dict]) -> tuple[str, dict] | None:
    """Mapeamento ameaça -> ação (P-17). Prioridade: A > B saída > B redução > C > perto de cair de nível."""
    por_tipo = {}
    for a in ameacas:  # já vem da mais recente para a mais antiga
        por_tipo.setdefault(a["detalhe"], a)
    if "grave_2_eventos_90d" in por_tipo:
        return "recuperacao_servico", por_tipo["grave_2_eventos_90d"]
    for det in ("saida_total", "reducao"):
        if det in por_tipo:
            g = por_tipo[det]
            alt = tools.get_network_alternative(g["par_rota"], perfil["aeroporto_casa"])
            g = {**g, "alternativa": alt}
            tem_alt = alt["hub"] or (det == "reducao" and alt["voos_diretos_mes"] > 0)
            return ("oferta_rota_favorita" if tem_alt else "contato_humano"), g
    if "queda_tarifa" in por_tipo:
        g = por_tipo["queda_tarifa"]
        return ("upgrade" if perfil["nivel_vigente"] == "Diamante Unique" else "bonus_pontos"), g
    folga = perfil["folga_pct_2025"]
    if perfil["nivel_alcancado_2025"] in tools.LIMIARES and folga is not None and folga < FOLGA_PERTO_DE_CAIR:
        falta = tools.faltam_para_manter(perfil["nivel_alcancado_2025"], perfil["trechos_2026"],
                                         perfil["pontos_2026"], perfil["gasto_2026_brl"])
        if not falta["cumprido"]:  # OU: faltam trechos E pontos; E: faltam (trechos ou pontos) e o gasto
            return "desafio_manutencao_nivel", {"detalhe": "perto_de_cair_de_nivel", "folga_pct": folga, **falta}
    return None


def citar_regras(acao: str, nivel: str, consulta: str) -> tuple[list[dict], list[str]]:
    """RAG: para cada benefício da ação, o trecho da KB mais parecido com a consulta, válido para o nível."""
    regras, faltando = {}, []
    for b in tools.BENEFICIOS_ACAO[acao]:
        achado = tools.buscar_kb(consulta, k=1, filtro=lambda t: b in t["beneficios"]
                                 and ("todos" in t["niveis"] or nivel in t["niveis"]))
        if achado:
            regras.setdefault(achado[0]["id"], achado[0])
        else:
            faltando.append(b)
    return list(regras.values()), faltando


def _trajeto(g: dict) -> str:
    alt = g["alternativa"]
    partes = []
    if alt["voos_diretos_mes"]:
        partes.append(f"{alt['voos_diretos_mes']} opções de voo direto {cidade(alt['origem'])} → {cidade(alt['destino'])} no mês")
    if alt["hub"]:
        partes.append(f"conexão via {cidade(alt['hub'])} (até {alt['voos_conexao_mes']} voos por perna no mês)")
    return " e ".join(partes)


# Contextos fixos por ação (sem número, valor nem benefício), em tons diferentes. O 1º é o padrão
# (LLM_PROVIDER=nenhum ou qualquer falha). O LLM opcional só escolhe o índice; nenhum texto dele chega à mensagem.
CONTEXTOS = {
    "recuperacao_servico": [
        "Sabemos que suas últimas viagens com a Azul tiveram atraso ou cancelamento, e isso pesa na sua rotina.",
        "Suas últimas viagens com a Azul tiveram atraso ou cancelamento.",
        "Sentimos muito pelos contratempos nas suas últimas viagens com a Azul e agradecemos a sua paciência.",
        "Registramos atrasos ou cancelamentos nas suas viagens recentes com a Azul e pedimos desculpas pelo transtorno.",
    ],
    "oferta_rota_favorita": [
        "Sua rota mudou na nossa malha e queremos que você continue voando com a Azul.",
        "Houve mudança na malha da Azul na sua rota.",
        "Sabemos que essa rota faz parte da sua rotina e queremos continuar levando você aonde precisa.",
        "Informamos que houve alteração na malha da Azul na rota que você utiliza.",
    ],
    "bonus_pontos": [
        "Obrigado por voar com a Azul.",
        "Que bom ter você a bordo da Azul.",
        "Agradecemos a sua preferência pela Azul nas suas viagens.",
        "Agradecemos por escolher a Azul.",
    ],
    "upgrade": [
        "Obrigado por voar com a Azul.",
        "Que bom ter você a bordo da Azul.",
        "Agradecemos a sua preferência pela Azul nas suas viagens.",
    ],
    "desafio_manutencao_nivel": [
        "Você está perto da sua meta no Azul Fidelidade este ano.",
        "Sua meta no Azul Fidelidade está próxima.",
        "Falta pouco para a sua meta no Azul Fidelidade este ano.",
        "Informamos o andamento da sua meta no Azul Fidelidade este ano.",
    ],
    "contato_humano": [
        "Sua rota mudou na nossa malha.",
        "Houve mudança na malha da Azul na sua rota.",
        "Sabemos que essa rota é importante para você.",
        "Informamos que houve alteração na malha da Azul na rota que você utiliza.",
    ],
}


def texto_oferta(acao: str, g: dict, roi: dict) -> str:
    """Parte fixa da mensagem: números, pontos, R$, prazos e condições. Nunca passa pelo LLM nem muda depois."""
    pts = f"{roi['pontos']:,}".replace(",", ".")
    if acao == "recuperacao_servico":
        return (f"A mais recente foi no trecho {cidade(g['origem_icao'])} → {cidade(g['destino_icao'])}. Vamos acompanhar seus próximos "
                f"voos de perto: se houver nova espera, você terá a assistência prevista (alimentação e, com pernoite, "
                f"hospedagem) e as opções de reacomodação pelo canal digital. Como reconhecimento, vamos creditar "
                f"{pts} pontos Azul Fidelidade na sua conta.")
    if acao == "oferta_rota_favorita":
        return (f"Para a rota {rota(g['par_rota'])}, há {_trajeto(g)}. Na primeira viagem pelo novo trajeto, vamos creditar "
                f"{pts} pontos Azul Fidelidade, além dos pontos do seu nível.")
    if acao == "bonus_pontos":
        return (f"Nas suas próximas viagens na rota {rota(g['par_rota'])}, vamos creditar {pts} pontos Azul Fidelidade "
                f"extras, somados aos pontos do seu nível.")
    if acao == "upgrade":
        return (f"Como Diamante Unique, você tem 40% de desconto no upgrade de cabine com pontos. Para a sua próxima "
                f"viagem na rota {rota(g['par_rota'])}, vamos creditar {pts} pontos Azul Fidelidade para usar nesse upgrade.")
    if acao == "desafio_manutencao_nivel":
        # Só o que falta: caminho já cumprido não aparece e nunca sai "faltam 0" (escolher_gatilho garante algo > 0).
        # A validade do nível de 2025 até o fim de 2026 (P-11, sem fonte confirmada) fica só na justificativa.
        partes = [f"{g['faltam_trechos']} trechos"] if g["faltam_trechos"] else []
        partes += [f"{g['faltam_pontos']:,} pontos qualificáveis".replace(",", ".")] if g["faltam_pontos"] else []
        meta = (" e " if g["e"] else " ou ").join(partes)
        if g["faltam_gasto_brl"]:
            meta += f" (ou R$ {g['faltam_gasto_brl']:,.0f} em gastos aéreos)".replace(",", ".")
        return (f"Faltam {meta} até 31/12 para garantir o nível {g['nivel']} em 2027. Se cumprir esse desafio, vamos "
                f"creditar {pts} pontos Azul Fidelidade de bônus.")
    if acao == "contato_humano":
        return (f"Um especialista da Azul vai falar com você sobre a rota {rota(g['par_rota'])} para montar o melhor trajeto "
                f"para as suas próximas viagens.")
    raise ValueError(acao)


def escolher_contexto(acao: str, resumo: str) -> int:
    """Índice (0-based) do contexto fixo; padrão 0. Com LLM_PROVIDER=ollama, o modelo local só ESCOLHE o tom: a
    resposta é aceita apenas se, sem espaços, for exatamente um dígito de 1 a N; qualquer outra coisa ou falha = 0."""
    opcoes = CONTEXTOS[acao]
    if _env("LLM_PROVIDER", "nenhum").lower() != "ollama":
        return 0
    lista = "\n".join(f"{i}. {c}" for i, c in enumerate(opcoes, 1))
    prompt = (f"Cliente de companhia aérea: {resumo}. Escolha o tom mais adequado para abrir a mensagem entre as "
              f"frases numeradas abaixo. Responda somente com o número, sem nenhum outro caractere.\n\n{lista}")
    corpo = json.dumps({"model": _env("LLM_MODEL", "llama3.2"), "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(_env("OLLAMA_URL", "http://localhost:11434") + "/api/generate", data=corpo,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            resposta = re.sub(r"\s", "", str(json.loads(r.read())["response"]))
    except Exception:  # Ollama fora do ar ou resposta inválida: contexto padrão
        return 0
    return int(resposta) - 1 if re.fullmatch(rf"[1-{len(opcoes)}]", resposta) else 0


class ClienteInexistente(LookupError):
    """Cliente fora da base (a API devolve 404 só para este erro)."""


def decidir(cliente_id: str) -> dict:
    perfil = tools.get_customer_profile(cliente_id)
    scores = tools.get_scores_and_reasons(cliente_id)
    if perfil is None or scores is None:
        raise ClienteInexistente(f"cliente não encontrado: {cliente_id}")
    p, clv = scores["p_evasao"], scores["clv_previsto_6m_brl"]
    if p is None:
        return abster(cliente_id, "cliente não elegível à evasão (menos de 3 trechos esperados em 6 meses): "
                                  "sem risco de evasão estimado não há retorno calculável")
    valor, risco = faixa_valor(int(scores["decil_score"])), faixa_risco(p)
    ameacas = tools.get_threats(cliente_id)
    escolha = escolher_gatilho(perfil, ameacas)
    if escolha is None:
        return abster(cliente_id, "nenhuma regra aplicável (sem ameaça A nos últimos 90 dias, sem B/C nos últimos "
                                  "180 dias e nível sem risco de queda)")
    acao, g = escolha
    gatilho = g["detalhe"]
    nome_g = NOME_GATILHO.get(gatilho, gatilho)
    # Matriz valor x risco (P-17): valor baixo não recebe ação com custo; risco baixo só recebe recuperação de serviço.
    if valor == "baixo":
        return abster(cliente_id, f"valor baixo (fora dos 50% de maior valor): ação com custo não se justifica, "
                                  "fica a assistência regulatória padrão", gatilho)
    if risco == "baixo" and acao != "recuperacao_servico":
        return abster(cliente_id, f"risco baixo (risco de evasão {br(p, 2)}, abaixo de 0,20): {nome_g} não justifica ação "
                                  "com custo", gatilho)
    if not perfil["consentimento_marketing"] and acao in MARKETING:
        if gatilho in ("saida_total", "reducao"):
            acao = "contato_humano"  # mudança de rota é serviço: humano informa, sem oferta de marketing
        else:
            return abster(cliente_id, f"{nome_g} só admite ação de marketing e o cliente não deu "
                                      "consentimento de marketing (LGPD)", gatilho)
    roi = tools.estimate_offer_roi(acao, p, clv, tools.canal_humano(acao, valor))
    if roi["roi_estimado"] <= 0:
        return abster(cliente_id, f"ROI estimado de {NOME_ACAO[acao]} não é positivo (R$ {br(roi['roi_estimado'], 2)}; "
                                  f"valor {NOME_FAIXA[valor]}, risco {NOME_FAIXA[risco]}, valor previsto em 6 meses "
                                  f"R$ {br(clv)}, risco de evasão {br(p, 2)})", gatilho)
    consulta = f"{acao.replace('_', ' ')} {gatilho.replace('_', ' ')} {perfil['nivel_vigente']} " \
               f"{' '.join(tools.BENEFICIOS_ACAO[acao]).replace('_', ' ')}"
    regras, faltando = citar_regras(acao, perfil["nivel_vigente"], consulta)
    if faltando:
        return abster(cliente_id, f"benefício(s) {', '.join(faltando)} sem regra na KB para o nível "
                                  f"{perfil['nivel_vigente']}", gatilho)
    oferta = texto_oferta(acao, g, roi)
    indice = escolher_contexto(acao, f"ação {acao}, gatilho {gatilho}, nível {perfil['nivel_vigente']}, "
                                     f"valor {valor}, risco {risco}")
    mensagem = f"{CONTEXTOS[acao][indice]} {oferta}"
    extra = ""
    if acao == "recuperacao_servico":
        f = tools.get_route_friction(g["par_rota"])
        if f["pct_atraso_30"] is not None:
            extra = (f" Rota {rota(f['par_rota'])} nos 3 meses até o corte: {br(f['pct_atraso_30'], 1)}% dos voos "
                     f"Azul com atraso acima de 30 min e {br(f['pct_cancelado'], 1)}% cancelados (ANAC VRA).")
    if acao == "desafio_manutencao_nivel":
        extra += (f" Nível {g['nivel']} alcançado em 2025 com folga de {100 * g['folga_pct']:.0f}% (abaixo de 25%): "
                  f"vale até o fim de 2026; a meta de 2026 ({g['regra']}) garante o nível em 2027.")
    if "par_rota" in g:
        a, m, d = g["data_ameaca"].split("-")
        origem = f"{rota(g['par_rota'])}, {d}/{m}/{a}"
    else:
        origem = f"nível {g['nivel']}, meta de 2026"
    justificativa = (f"Gatilho: {nome_g} ({origem}). Ação: {NOME_ACAO[acao]}. Valor {NOME_FAIXA[valor]} "
                     f"({faixa_decil(int(scores['decil_score']))}; valor previsto em 6 meses R$ {br(clv)}), risco "
                     f"{NOME_FAIXA[risco]} (risco de evasão {br(p, 2)}). Retorno estimado: risco de evasão × valor "
                     f"previsto × efeito suposto de {br(100 * roi['efeito_suposto'])}% − custo = "
                     f"R$ {br(roi['roi_estimado'], 2)}. Motivos do modelo: "
                     f"{'; '.join(scores['motivos']) or 'nenhum'}." + extra)
    decisao = {
        "cliente_id": cliente_id, "acao": acao, "gatilho": gatilho, "justificativa": justificativa,
        "regras_citadas": [{"id": r["id"], "url": r["url"], "trecho": r["trecho"], "fonte": r["fonte"],
                            "status": r["status"], "beneficios": sorted(r["beneficios"]),
                            "niveis": sorted(r["niveis"])} for r in regras],
        # Crédito de pontos de cortesia: decisão comercial sem regra pública (LACUNAS.md), fora de regras_citadas.
        "decisao_comercial": ({"item": "crédito de pontos Azul Fidelidade", "pontos": roi["pontos"],
                               "custo_brl": roi["custo_pontos"], "base": "decisão comercial (sem regra pública)"}
                              if roi["pontos"] else None),
        "roi_estimado": roi["roi_estimado"], "custo_estimado": roi["custo_estimado"], "mensagem": mensagem,
        "mensagem_oferta": oferta,
        "contexto_indice": indice + 1,  # qual contexto fixo aprovado abriu a mensagem (1 = padrão)
        "canal": "atendimento_humano" if tools.canal_humano(acao, valor) else "app",
        "requer_aprovacao_humana": True,  # toda ação do catálogo gera custo
    }
    erros = guardrails.validar(decisao, perfil, scores, CONTEXTOS[acao])
    return abster(cliente_id, "guardrail bloqueou: " + "; ".join(erros), gatilho) if erros else decisao


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("uso: python -I agent/nba_agent.py <cliente_id>")
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(decidir(sys.argv[1]), ensure_ascii=False, indent=2))
