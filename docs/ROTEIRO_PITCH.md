# Roteiro do pitch · 5 minutos

Ritmo de ~140 palavras por minuto; total falado 620 palavras (~4 min 26 s), o resto é clique e pausa. Contagem de palavras do texto falado entre colchetes. Sem logotipo da Azul, sem
print do site, sem trecho do briefing. Toda vez que aparecer número de cliente, a tela mostra "base sintética".

**Frase-chave (números atuais da gold, conferidos em 2026-10-21):** "Entre set/2025 e ago/2026, só com dados públicos, o
radar detectou **17** pares em que a Azul saiu e **82** em que reduziu a oferta."
- 17 = pares (não direcionais) com `saida_total` e `mes_saida` entre 2025-09 e 2026-08 em `data/gold/route_exits`.
  **Bate com o handoff.**
- 82 = pares com `reducao` em algum mês de 2025-09 a 2026-08, **excluindo os 53 pares com saída total em qualquer mês
  da janela**. **Bate com o handoff** nessa definição. Excluindo só os 17 pares acima, seriam 84. A redução não tem
  piso de volume (P-05); com piso de 30 voos no trimestre do ano anterior, 80.

---

## 0:00 – 0:40 · O problema [100 palavras, ~43 s]
**Tela:** fundo neutro, três números grandes, cada um com a fonte no rodapé.
- "−10,6% de capacidade · +12,4% de receita premium" (release 2T26 da Azul, 13/08/2026)
- "53 rotas: corte anunciado na reestruturação" (imprensa: Suno, 11/08/2025; mostrar "fonte: imprensa" na tela)
- "26,6% das reclamações da Azul no Consumidor.gov.br são atraso ou cancelamento" (ANAC/Senacon, set/2024–dez/2025)

**Fala:**
> No segundo trimestre de 2026, a Azul voou com dez vírgula seis por cento menos capacidade. Mesmo assim, a receita
> premium cresceu doze vírgula quatro por cento. Com menos assentos, cada cliente de alto valor pesa mais. E é
> justamente esse cliente que sente primeiro quando algo dá errado. A Azul anunciou o corte de cinquenta e três rotas na
> reestruturação. E uma em cada quatro reclamações da Azul no Consumidor.gov.br é atraso ou cancelamento. O cliente
> bom não vai embora do nada. Ele vai embora depois de uma ameaça concreta. Hoje essa ameaça aparece no dado público
> antes de aparecer no CRM.

## 0:40 – 1:00 · A ideia em uma frase [39 palavras, ~17 s]
**Tela:** "ÓRBITA: vigia três ameaças em dado público e propõe a próxima melhor ação, com aprovação humana." Três ícones
genéricos: A atraso, B rota órfã, C tarifa do concorrente.

**Fala:**
> O ÓRBITA vigia três ameaças em dado público: atraso grave, rota que a Azul deixou e tarifa do concorrente em queda.
> Quando uma delas atinge um cliente de alto valor, o agente propõe a ação certa. Uma pessoa aprova.

## 1:00 – 3:00 · Demo ao vivo [230 palavras, ~99 s de fala + ~20 s de cliques]
**Tela 1 (1:00–1:35) · Radar de ameaças.** Contadores A, B, C até 28/02/2026, gráfico valor × risco, lista por receita
em risco. Selo "base sintética" visível.
> Este é o Radar. Os dados de voo, atraso, rota e tarifa são públicos, da ANAC. Os clientes são sintéticos: cinquenta
> mil clientes fictícios, nenhum dado real. Entre setembro de 2025 e agosto de 2026, só com dados públicos, o radar
> detectou dezessete pares em que a Azul saiu e oitenta e dois em que reduziu a oferta. No gráfico, o eixo vertical é
> valor e o horizontal é risco. O canto de cima à direita é onde agir primeiro.

**Tela 2 (1:35–2:15) · Agir, caso `9132e89e` (A grave).** Busca o id, clica Agir. Mostra ação recuperação de serviço,
custo R$ 182,91, ROI estimado R$ 460,25, regras citadas com selo "a conferir por negócios", edita o texto, clica
Aprovar.
> Este cliente sofreu dois atrasos graves em noventa dias. Está no decil mais alto de valor, com quarenta e sete por
> cento de risco. O agente propõe recuperação de serviço. Mostra o custo, o retorno esperado e cita a regra da ANAC
> que sustenta a assistência. Repare no selo: a conferir por negócios. Eu edito o tom, mas a oferta não muda. Aprovo.
> Nada foi enviado ao cliente: fica registrado para o time de CRM.

**Tela 3 (2:15–2:40) · Cliente 360, caso `85e407cb` (perto de cair de nível).** Três motivos do modelo, viagens, botão
Gerar próxima melhor ação → desafio de manutenção.
> Agora um Diamante perto de cair de nível. O modelo explica o porquê em português: a frequência caiu setenta e três
> por cento em seis meses. O agente propõe um desafio de manutenção, mostrando só o que falta para manter a categoria.

**Tela 4 (2:40–3:00) · Simulador de ROI.** Arrasta a verba; mostra clientes acionados, salvos e receita protegida.
> No simulador, a diretoria escolhe a verba e vê quantos clientes protege. Os efeitos aqui são supostos, e a tela diz
> isso. Por isso o próximo passo é medir com grupo de controle.

## 3:00 – 3:40 · Como pluga no Snowflake real [80 palavras, ~34 s]
**Tela:** diagrama bronze → silver → gold; ao lado, um contrato YAML e um trecho de SQL. Seta "sintético → real" na
camada silver.

**Fala:**
> Como isso entra na Azul? Cada tabela tem um contrato em YAML: colunas, tipos e regras. São dezenove contratos. A lógica
> das ameaças é SQL padrão ANSI, sem nada exclusivo do banco local. Hoje roda em DuckDB, no notebook, de graça. Na
> Azul, o mesmo SQL vai para o Snowflake. A troca é na camada de clientes: sai a tabela sintética, entra a tabela real
> com a mesma estrutura. Modelos, agente e painel não mudam. O que muda é a fonte.

## 3:40 – 4:20 · IA responsável [85 palavras, ~36 s]
**Tela:** sete selos em lista: aprovação humana · abstenção · catálogo fechado · LLM só escolhe o tom · fairness por
região · circularidade declarada · custo zero.

**Fala:**
> Nenhuma ação sai sem aprovação humana. Quando falta regra, consentimento ou retorno, o agente se abstém. As ações vêm
> de um catálogo fechado: o sistema não inventa benefício. Se houver modelo de linguagem, ele só escolhe o tom entre
> textos já aprovados, e nenhum número passa por ele. Medimos justiça por região: a taxa de oferta varia cerca de
> quinze por cento. E declaramos a circularidade: na base sintética o modelo recupera regras que nós mesmos criamos.
> Tudo roda com custo zero, sem modelo pago.

## 4:20 – 5:00 · Impacto e próximos passos [86 palavras, ~37 s]
**Tela:** tabela dos três cenários (business case, seção 4) com o selo "piloto sintético · efeitos supostos"; abaixo,
três próximos passos.

**Fala:**
> No piloto sintético, o cenário base aciona três mil e quatrocentos clientes. Custa cento e oitenta e quatro mil reais
> e protege trezentos e noventa e sete mil em seis meses. São dois reais e dezesseis por real investido. No
> cenário conservador, não se paga. Por isso pedimos três coisas: um piloto de noventa dias com grupo de controle,
> acesso às tabelas reais no Snowflake e a validação dos benefícios pelo time do Azul Fidelidade. O radar já
> funciona com dado público. Falta provar o efeito.

---

## Números ditos no palco e de onde vêm
| Número | Tipo | Fonte |
|---|---|---|
| −10,6% capacidade; +12,4% receita premium | público | Release 2T26, 13/08/2026, https://api.mziq.com/mzfilemanager/v2/d/ed78542a-4e01-429a-8926-03d69ccfa307/51192f68-386a-a700-cbae-fba020b58c7b?origin=2 (acesso 2026-10-21) |
| 53 rotas | público (imprensa) | https://www.suno.com.br/noticias/?p=618985 (11/08/2025; acesso 2026-10-21) |
| 26,6% das reclamações da Azul são atraso/cancelamento (12.977 de 48.743) | público | Consumidor.gov.br via ANAC, cc-by (P-18), `data/gold/friction_themes`, set/2024–dez/2025 |
| 17 e 82 pares | público, processado pelo ÓRBITA | ANAC VRA, `data/gold/route_exits` |
| 47% de risco, decil 1, R$ 182,91, R$ 460,25 | sintético | `app/.cache/nba_lote.parquet`, cliente `9132e89e` |
| Frequência −73% | sintético | `gold.customer_scores`, motivo 1 do cliente `85e407cb` |
| Oferta varia cerca de 15% por região | sintético | razão 1,154, `ml/resultados/fairness_disparidade.csv` |
| 3.408 acionados; R$ 184 mil; R$ 397 mil; R$ 2,16; conservador ROI −0,06 | sintético + premissa | `docs/BUSINESS_CASE.md`, cenário base |

## Dado do Consumidor.gov.br (usar se sobrar segundo, ou na pergunta da banca)
Set/2024 a dez/2025 (2026 ainda não publicado): a Azul tem a **melhor nota média** entre as três grandes (3,87 contra
3,82 da LATAM e 3,81 da Gol; diferença pequena) e a **maior taxa de reclamação de atraso/cancelamento por voo**: 321,5
por 10 mil voos previstos, contra 266,2 da LATAM e 212,7 da Gol. Ressalva: o denominador é voo doméstico e as
reclamações incluem voo internacional (P-18). Narrativa: o atendimento é bem avaliado; o atrito vem da operação, que é
exatamente a ameaça A.

## Não citar no palco
- **Relatório Amadeus + Microsoft:** existe ("Airlines in the agentic age: use cases and ideas for getting started with
  AI", Amadeus com apoio da Microsoft, 04/06/2026, entrevistas com Azul, Icelandair e Southwest;
  https://www.amadeus.com/en/newsroom/press-releases/agentic-ai-airlines-amadeus, acesso 2026-10-21). O comunicado
  **não fala em supervisão humana**; fala em "governança forte". Se citar, só nesses termos.
- Não dizer que a receita recorde veio de "clientes de alto valor". A formulação do release é "captura da demanda
  premium"; é a única usada no roteiro.
