"""Guardrails do agente NBA. Valem para a decisão e para qualquer texto (template ou edição no app).

Regras: benefício só se houver trecho na KB válido para o nível do cliente; ação com benefício cita regra; sem
consentimento de marketing só recuperação de serviço ou contato humano; custo dentro do teto proporcional ao valor;
nunca atributo sensível; nunca guerra de preço nem promessa de dinheiro; custo > 0 ou abstenção => aprovação humana.

Mensagem = `contexto` + " " + `oferta`. O contexto é um dos textos fixos aprovados da ação (o LLM opcional só
escolhe o índice, nunca escreve); a `oferta` (números, pontos, R$, prazos, condições) sai do texto-modelo e nunca muda.
A lista de termos abaixo (`checar_contexto`) serve só à edição manual no app, feita pelo próprio aprovador e gravada no
log; é conservadora e não pretende ser completa (residual aceito pela auditoria, P-17).
"""
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I tira o diretório do script do sys.path
from tools import BENEFICIOS_ACAO, SENSIVEIS, beneficios_texto, teto_custo  # noqa: E402

ACOES_SEM_CONSENTIMENTO = {"recuperacao_servico", "contato_humano", "sem_acao_automatica"}
LIMITE_CONTEXTO = 1.5  # na edição manual, o contexto pode ter até 1,5x o tamanho do contexto original

# Termo no texto -> benefício que ele promete (texto sem acento, minúsculo). Vale para a mensagem inteira.
TERMO_BENEFICIO = {
    "upgrade": "upgrade_desconto", "desconto": "upgrade_desconto",
    "bagagem": "bagagem_gratis", "prioritari": "atendimento_prioritario", "prioridade": "atendimento_prioritario",
    "alimentacao": "assistencia_material", "hospedagem": "assistencia_material", "hotel": "assistencia_material",
    "reacomoda": "reacomodacao", "pontos": "credito_pontos",
}
# Nunca aparecem na mensagem (início de palavra): dinheiro, compensação sem regra, guerra de preço, benefício que
# nenhuma ação do catálogo oferece, atributo sensível.
PROIBIDOS = ["reembolso", "indeniza", "dinheiro", "cashback", "compensac", "preco", "tarifa", "mais barat",
             "sala vip", "lounge", "acompanhante", "garantimos", "voucher", "milha", "assento", "gratis",
             "gratuit", "embarque", "antecipad", "cortesia",
             "regiao", "nordeste", "sudeste", r"norte\b", "centro-oeste", r"sul\b", "genero", r"idade\b", r"raca\b"]

# Só para o contexto EDITADO À MÃO no app: quantidade, benefício, termo do catálogo ou promessa bloqueiam a
# aprovação (lista ampla e conservadora; não é a defesa principal, que é a oferta fixa + aprovação humana).
_EXTENSO = (r"um|uma|dois|duas|tres|quatro|cinco|seis|sete|oito|nove|dez|onze|doze|treze|quatorze|catorze|quinze|"
            r"dezesseis|dezessete|dezoito|dezenove|vinte|trinta|quarenta|cinquenta|sessenta|setenta|oitenta|noventa|"
            r"cem|cento|duzent\w*|trezent\w*|quatrocent\w*|quinhent\w*|seiscent\w*|setecent\w*|oitocent\w*|"
            r"novecent\w*|mil|milhao|milhoes|bilh\w*|reais|real|centavo\w*|por cento|porcento|dobr\w*|tripl\w*|"
            r"quadrupl\w*|metade|dezena\w*|centena\w*|primeir\w*|segund\w*|terceir\w*")
_CATALOGO = (r"ponto\w*|bonus|bonific\w*|upgrade\w*|desconto\w*|credit\w*|voucher\w*|vale\w*|cupo\w*|sala\w*|"
             r"lounge|isenc\w*|isent\w*|taxa\w*|cortesia\w*|brinde\w*|presente\w*|premi\w*|gratis|gratuit\w*|"
             r"benefici\w*|vantage\w*|oferta\w*|cashback|milha\w*|assento\w*|bagage\w*|embarque\w*|prioridad\w*|"
             r"prioritari\w*|antecip\w*|reembols\w*|indeniz\w*|compens\w*|dinheiro|preco\w*|tarifa\w*|desafio\w*|"
             r"nive\w*|categori\w*|topazio|safira|diamante|unique|cabine|alimentac\w*|refeic\w*|hospedage\w*|"
             r"hote\w*|reacomod\w*|acompanhante\w*|exclusiv\w*|especia\w*|extra\w*|status|clube|cartao")
_PROMESSA = (r"vamos|vai|vao|iremos|ira|irao|garant\w*|promet\w*|assegur\w*|compromet\w*|daremos|dar|dara|ganh\w*|"
             r"receb\w*|liber\w*|ofere\w*|conced\w*|tera|terao|teremos|faremos|devolv\w*|pagar\w*|pagamos|"
             r"cobri\w*|sobe|subir\w*|subira|eleva\w*|presente\w*")
_RE_CONTEXTO = re.compile(rf"\b(?:{_EXTENSO}|{_CATALOGO}|{_PROMESSA})\b")


def _norm(txt: str) -> str:
    return unicodedata.normalize("NFKD", txt.lower()).encode("ascii", "ignore").decode()


def checar_texto(texto: str, beneficios_permitidos: set[str]) -> list[str]:
    """Erros da mensagem inteira: benefício fora da ação decidida ou termo proibido."""
    t = _norm(texto)
    erros = [f"termo proibido: '{p}'" for p in PROIBIDOS if re.search(r"\b" + p, t)]
    erros += [f"benefício '{b}' (termo '{k}') fora da ação decidida" for k, b in TERMO_BENEFICIO.items()
              if k in t and b not in beneficios_permitidos]
    return erros


def checar_contexto(contexto: str, original: str) -> list[str]:
    """Erros do contexto editado à mão: dígito, número por extenso, R$, %, benefício/catálogo, promessa ou tamanho
    acima de 1,5x o contexto original."""
    erros = []
    if re.search(r"\d", contexto):
        erros.append("dígito no contexto")
    if "R$" in contexto or "%" in contexto or "$" in contexto:
        erros.append("valor monetário ou percentual no contexto")
    achados = sorted({m.group(0) for m in _RE_CONTEXTO.finditer(_norm(contexto))})
    if achados:
        erros.append(f"termo de quantidade, benefício ou promessa no contexto: {', '.join(achados)}")
    if len(contexto) > LIMITE_CONTEXTO * len(original):
        erros.append(f"contexto com {len(contexto)} caracteres (limite {int(LIMITE_CONTEXTO * len(original))})")
    return erros


def checar_mensagem_editada(texto: str, contexto_original: str, oferta: str) -> list[str]:
    """Edição no app: a oferta original precisa estar intacta; o restante passa pela checagem do contexto."""
    if not oferta:
        return checar_contexto(texto, contexto_original)
    if oferta not in texto:
        return ["a oferta (números, pontos, prazos e condições) foi alterada: descarte e gere a ação de novo"]
    return checar_contexto(texto.replace(oferta, " ", 1).strip(), contexto_original)


def validar(decisao: dict, perfil: dict, entradas: dict, contextos_aprovados: list[str] = ()) -> list[str]:
    """Lista de violações (vazia = ok). `entradas` = tudo o que o agente recebeu para decidir; `contextos_aprovados`
    = textos fixos de contexto da ação (o contexto da mensagem precisa ser um deles, letra por letra)."""
    acao = decisao["acao"]
    erros = [f"atributo sensível nas entradas: {k}" for k in SENSIVEIS if k in entradas]
    if acao == "sem_acao_automatica":
        if not decisao["requer_aprovacao_humana"]:
            erros.append("abstenção sem aprovação humana")
        return erros
    if not perfil["consentimento_marketing"] and acao not in ACOES_SEM_CONSENTIMENTO:
        erros.append(f"sem consentimento de marketing: '{acao}' não permitido")
    regras = decisao["regras_citadas"]
    if BENEFICIOS_ACAO[acao] and not regras:
        erros.append("ação com benefício sem regra citada")
    nivel = perfil["nivel_vigente"]
    for b in BENEFICIOS_ACAO[acao]:
        if not any(b in r["beneficios"] and ("todos" in r["niveis"] or nivel in r["niveis"]) for r in regras):
            erros.append(f"benefício '{b}' sem regra da KB válida para o nível '{nivel}'")
    teto = teto_custo(entradas["clv_previsto_6m_brl"])
    if decisao["custo_estimado"] > teto + 1e-6:
        erros.append(f"custo {decisao['custo_estimado']:.2f} acima do teto {teto:.2f}")
    if decisao["custo_estimado"] > 0 and not decisao["requer_aprovacao_humana"]:
        erros.append("ação com custo sem aprovação humana")
    erros += checar_texto(decisao["mensagem"] or "", beneficios_texto(acao))
    if not decisao["mensagem"].endswith(decisao["mensagem_oferta"]):
        erros.append("mensagem não termina com a oferta do texto-modelo")
    elif decisao["mensagem"][: -len(decisao["mensagem_oferta"])].strip() not in contextos_aprovados:
        erros.append("contexto fora dos textos fixos aprovados da ação")
    return erros


if __name__ == "__main__":
    ctx = "Sabemos que suas últimas viagens com a Azul tiveram atraso ou cancelamento."
    assert checar_contexto(ctx, ctx) == []
    assert checar_contexto("Lamentamos os transtornos recentes nas suas viagens com a Azul.", ctx) == []
    for ruim in ("Sentimos muito, vamos creditar em dobro.", "Pedimos desculpas e oferecemos trezentos reais.",
                 "Pedimos desculpas, segue um vale-viagem.", "Faltam 23.750 pontos e R$ 7.300.",
                 "Prometemos que não vai se repetir.", "Pedimos desculpas, ganhe dez mil pontos.",
                 "Desculpe, há acesso à sala para você.", "Pedimos desculpas, isenção de taxa no próximo voo.",
                 "Pedimos desculpas, você sobe para Unique.", "Pedimos desculpas pelo triplo de espera.",
                 "Pedimos desculpas, 10% a mais.", ctx * 2):
        assert checar_contexto(ruim, ctx), ruim
    oferta = "Como reconhecimento, vamos creditar 1.200 pontos Azul Fidelidade na sua conta."
    assert checar_mensagem_editada(f"Lamentamos o ocorrido. {oferta}", ctx, oferta) == []
    assert checar_mensagem_editada(f"Lamentamos o ocorrido. {oferta.replace('1.200', '11.200')}", ctx, oferta)
    assert checar_mensagem_editada(f"Lamentamos, segue um voucher. {oferta}", ctx, oferta)
    assert checar_texto("Creditamos 500 pontos na sua conta.", {"credito_pontos"}) == []
    assert checar_texto("Ganhe upgrade e 500 pontos", {"credito_pontos"})  # upgrade fora da ação
    assert checar_texto("Cobrimos a tarifa do concorrente", {"credito_pontos"})  # guerra de preço
    assert checar_texto("pontos Azul Fidelidade", {"credito_pontos"}) == []  # 'idade' só como palavra
    assert checar_texto("clientes do Nordeste", {"credito_pontos"})
    print("guardrails ok")
