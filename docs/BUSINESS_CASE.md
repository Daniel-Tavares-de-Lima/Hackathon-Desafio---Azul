# Business case · ÓRBITA

**Em uma frase:** no piloto sintético, cada R$ 1 gasto em retenção protege R$ 2,16 de receita em 6 meses no cenário
base. No conservador o programa não se paga. Esse número depende de efeitos **supostos**. Só um piloto real com grupo
de controle prova o efeito.

Toda conta abaixo foi conferida em 2026-10-21 lendo `data/gold/customer_scores` e `app/.cache/nba_lote.parquet`
(lote refeito depois da correção do custo do canal, `tools.canal_humano`). Premissas novas em `docs/PREMISSAS.md`, P-19.

## Legenda dos números
| Marca | Tipo | Exemplo |
|---|---|---|
| **(a)** | Número público, com fonte e data de acesso | receita do 2T26 no release da Azul |
| **(b)** | Medido na base **sintética** (50.000 clientes fictícios, nenhum cliente real) | 3.408 clientes acionados |
| **(c)** | Premissa própria, sem fonte nem experimento | efeito suposto de 25% da recuperação de serviço (P-17) |

## 1. Contexto público (a)
Fonte principal: release de resultados do 2T26 da Azul, 13/08/2026, link no site de RI
(https://ri.voeazul.com.br/ →
https://api.mziq.com/mzfilemanager/v2/d/ed78542a-4e01-429a-8926-03d69ccfa307/51192f68-386a-a700-cbae-fba020b58c7b?origin=2),
acesso em 2026-10-21.

| Indicador | 2T26 | 2T25 | Variação |
|---|---|---|---|
| Receita líquida total | R$ 4.978,7 mi | R$ 4.942,3 mi | +0,7% ("recorde para um segundo trimestre de R$ 5,0 bilhões") |
| Receita de transporte de passageiros | R$ 4.560,5 mi | R$ 4.578,9 mi | −0,4% |
| Capacidade (ASK) | 11.468 mi | 12.827 mi | −10,6% |
| Receita premium | | | +12,4% |
| Passageiros | 7.252 mil | 7.976 mil | −9,1% |
| Tarifa média | R$ 628,9 | R$ 574,1 | +9,5% |
| Receita de passageiros no 1S26 | R$ 9.609,3 mi | | base da escala (seção 5) |

- O release diz que a Azul "permaneceu focada na captura da demanda premium, por meio de uma estratégia voltada para
  esses clientes", e que a receita recorde foi impulsionada por tarifas mais altas. Usamos só "demanda premium", a
  formulação do release; ele não atribui a receita a "clientes de alto valor" e não informa o valor absoluto da
  receita premium. A tarifa média bate com a conta: R$ 4.560,5 mi ÷ 7.252 mil passageiros = R$ 628,86.
- Saída do Chapter 11 em 20/02/2026: Poder360, 21/02/2026,
  https://www.poder360.com.br/poder-economia/azul-conclui-recuperacao-judicial-nos-eua-e-sai-do-chapter-11/ (acesso
  2026-10-21). O release do 2T26 fala em "conclusão bem-sucedida de nossa reestruturação".
- Corte de 53 rotas de baixa rentabilidade em 13 cidades, dentro do plano de reestruturação: Suno, 11/08/2025,
  https://www.suno.com.br/noticias/?p=618985 (acesso 2026-10-21). Imprensa; o fato relevante original não foi lido.
- Azul Fidelidade com mais de 20 milhões de clientes **cadastrados** (não ativos): Brasilturis, 25/05/2026,
  https://brasilturis.com.br/2026/05/25/azul-fidelidade-supera-20-milhoes-de-clientes-e-dobrou-de-tamanho-em-cinco-anos/
  (acesso 2026-10-21).
- **Não encontrado em fonte pública (a confirmar):** quantos membros estão em cada nível; quanto da receita vem de
  membros de nível ou de clientes premium; taxa real de evasão de clientes de alto valor. Sem esses números, a
  escala da seção 5 é só ilustrativa.

## 2. A fórmula
```
receita protegida = Σ p_evasao × CLV 6 m × efeito suposto da ação × fator de efeito × aceitação
custo             = Σ contato (todo acionado) + aceitação × Σ pontos
ROI               = (receita protegida − custo) ÷ custo
```
- `p_evasao` e CLV de 6 meses (receita aérea bruta, não margem) vêm dos modelos (b).
- Efeito suposto por ação (c, P-17): recuperação de serviço 0,25; oferta na rota favorita 0,20; desafio de nível 0,20;
  upgrade 0,12; bônus de pontos 0,10; contato humano 0,10.
- Custo (c, P-17): pontos a R$ 0,02 cada, como % do CLV, com teto por cliente; contato digital R$ 1, humano R$ 20.
  O custo do contato segue o canal: R$ 20 quando a ação exige atendimento humano ou o cliente é de alto valor.
- Fator de efeito e aceitação (c, P-19): variam por cenário.

## 3. Piloto na base sintética (b)
Público do agente: elegíveis à evasão nos decis 1 a 5 do score = **12.734 clientes sintéticos**, com R$ 11,89 mi de
receita em risco (Σ p × CLV). O agente recomenda ação com custo para **3.408**; os outros 9.326 ficam em abstenção
(`sem_acao_automatica`).

| Ação | Clientes | Receita em risco (R$) | Protegida se 100% aceitam (R$) | Pontos (R$) | Contato (R$) | Custo total (R$) |
|---|---|---|---|---|---|---|
| Desafio de manutenção de nível | 1.946 | 1.745.322 | 349.064 | 108.560 | 18.666 | 127.226 |
| Recuperação de serviço (A) | 643 | 1.293.665 | 323.416 | 143.170 | 12.860 | 156.030 |
| Oferta na rota favorita (B) | 390 | 393.899 | 78.780 | 23.460 | 3.525 | 26.985 |
| Contato humano (B sem alternativa) | 229 | 240.646 | 24.065 | 0 | 4.580 | 4.580 |
| Bônus de pontos (C) | 199 | 189.903 | 18.990 | 8.857 | 2.004 | 10.861 |
| Upgrade (C, Diamante Unique) | 1 | 4.738 | 569 | 278 | 20 | 298 |
| **Total** | **3.408** | **3.868.173** | **794.884** | **284.325** | **41.655** | **325.980** |

Contato: 2.013 ações por atendimento humano (R$ 20) + 1.395 pelo app (R$ 1) = R$ 41.655. Conferência: Σ ROI do lote
(R$ 468.904) = protegida (R$ 794.884) − custo (R$ 325.980). O app mostra este caso (100% de aceitação) no Simulador.

**Clientes de alto valor ameaçados (b):** decil 1–2 com gatilho principal A, B ou C = **1.417 clientes**, R$ 2,14 mi de
receita em risco. O agente aciona 915 (551 recuperação, 165 oferta na rota, 103 contato humano, 95 bônus, 1 upgrade)
e se abstém em 502 (280 de B redução, 170 de C, 40 de A, 12 de B saída; motivo por cliente na justificativa do agente:
consentimento, benefício sem regra, ROI ou guardrail).

## 4. Três cenários (piloto, 6 meses)
| Cenário | Fator de efeito | Aceitação | Receita protegida (R$) | Custo (R$) | Líquido (R$) | ROI | Clientes salvos (esperado) |
|---|---|---|---|---|---|---|---|
| Conservador | 0,5 | 30% | 119.233 | 126.952 | −7.720 | −0,06 | 33 |
| **Base** | **1,0** | **50%** | **397.442** | **183.817** | **213.625** | **1,16** | **111** |
| Otimista | 1,5 | 70% | 834.628 | 240.682 | 593.946 | 2,47 | 233 |

Conta do cenário base, passo a passo:
1. Protegida com 100% de aceitação e efeito cheio: R$ 794.884 (tabela da seção 3).
2. × fator 1,0 × aceitação 0,5 = **R$ 397.442**.
3. Custo = contato R$ 41.655 + 0,5 × pontos R$ 284.325 = 41.655 + 142.162 = **R$ 183.817**.
4. Líquido = 397.442 − 183.817 = **R$ 213.625**. ROI = 213.625 ÷ 183.817 = **1,16** (R$ 2,16 de volta por R$ 1).

Conservador: 794.884 × 0,5 × 0,3 = 119.233; custo 41.655 + 0,3 × 284.325 = 126.952; líquido −7.720.
Otimista: 794.884 × 1,5 × 0,7 = 834.628; custo 41.655 + 0,7 × 284.325 = 240.682; líquido 593.946.

**No cenário conservador o programa não se paga:** o contato é pago para todo acionado, e metade do efeito com 30% de
aceitação não cobre esse custo fixo. Leitura prática: começar pelas ações de maior ROI (o Simulador ordena assim) e
medir antes de escalar.

## 5. Escala para a Azul real (ilustrativa, c)
A única entrada pública é a receita de passageiros do 1S26 (a). A razão vem do piloto sintético (b + c).

| Cenário | Protegida ÷ CLV 6 m da base (R$ 96,21 mi) | × R$ 9.609,3 mi (1S26) | Custo na mesma escala | Líquido |
|---|---|---|---|---|
| Conservador | 0,124% | R$ 11,9 mi | R$ 12,7 mi | −R$ 0,8 mi |
| Base | 0,413% | R$ 39,7 mi | R$ 18,4 mi | R$ 21,3 mi |
| Otimista | 0,868% | R$ 83,4 mi | R$ 24,0 mi | R$ 59,3 mi |

Leia como: **a cada R$ 1 bi de receita semestral de passageiros, cerca de R$ 4,1 mi protegidos no cenário base**, se a
Azul real se parecer com a base sintética. Não é previsão. O RI inclui voo internacional (18,8% do ASK no 2T26, calculado por nós: 2.154 ÷ 11.468 do release) e a
base sintética só tem tarifa doméstica sem taxas. Custo de implantação e operação (Snowflake, equipe) não tem número
público e não entra.

## 6. Sensibilidade (piloto, líquido em R$)
| Fator de efeito \ Aceitação | 10% | 30% | 50% | 70% | 100% |
|---|---|---|---|---|---|
| 0,5 | −30.343 | −7.720 | 14.904 | 37.527 | 71.462 |
| 1,0 | 9.401 | 111.513 | 213.625 | 315.736 | 468.904 |
| 1,5 | 49.145 | 230.745 | 412.346 | 593.946 | 866.346 |

Pontos de equilíbrio (líquido = 0):
- Com 50% de aceitação, o efeito real precisa ser **≥ 46%** do suposto em P-17.
- Com o efeito cheio, basta **8,2%** de aceitação. Com metade do efeito, **36,8%**.
- Se o ponto custar R$ 0,04 em vez de R$ 0,02, o custo do base vai a R$ 325.980 e o ROI cai para 0,22.

## 7. O que precisaria ser verdade
1. **O efeito existe.** A ação reduz a evasão em pelo menos ~46% do que P-17 supõe (com 50% de aceitação). Teste: piloto com grupo de controle
   (ex.: 10% dos elegíveis sem ação) por 6 meses.
2. **O risco está bem medido em dado real.** Na base sintética o `p_evasao` OOF é bem calibrado, mas o modelo temporal
   subestima o risco (model card). Recalibrar com histórico real da Azul.
3. **O ponto custa perto de R$ 0,02 para a Azul.** Premissa própria; o número real é interno.
4. **Os benefícios citados valem.** A KB vem de fontes secundárias, "a conferir por negócios" (`agent/kb/LACUNAS.md`).
5. **Há consentimento de marketing.** O sintético supõe 70% (P-14); sem consentimento só cabem recuperação e contato.
6. **A concentração de receita real se parece com a sintética**, para a escala da seção 5 fazer sentido.
