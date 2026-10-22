# Estratégia de CRM · ÓRBITA

**Regra de ouro:** o cliente não vai embora do nada. Vai por uma ameaça concreta (A atraso, B rota órfã, C tarifa do
concorrente) ou porque está perto de cair de nível. Agimos no gatilho, com uma ação de catálogo fechado, e sempre
com aprovação humana.

Todos os números de cliente são da **base sintética** (50.000 clientes fictícios, nenhum cliente real), medidos em
2026-10-21 em `data/gold/customer_scores` e `app/.cache/nba_lote.parquet`. Custos e efeitos são premissas (P-17).
Todo benefício citado está em `agent/kb/` e herda a marca **"a conferir por negócios"** (fontes secundárias; a
página oficial do Azul Fidelidade devolveu HTTP 403).

## 1. Dois eixos: valor × risco
- **Valor** = decil do score (alto 1–2, médio 3–5, baixo 6–10).
- **Risco** = probabilidade de evasão em 6 meses (alto ≥ 0,35, médio ≥ 0,20, baixo < 0,20).

Clientes do lote do agente (elegíveis, decis 1–5):

| Valor \ Risco | Alto | Médio | Baixo |
|---|---|---|---|
| **Alto** | 441 clientes, 245 acionados · **agir já** | 3.315, 1.401 acionados · agir no gatilho | 5.110, 149 acionados · só recuperação de serviço (A) |
| **Médio** | 2.642, 1.144 acionados · agir se ROI > 0 | 1.204, 469 acionados · agir no gatilho | 22, 0 acionados · monitorar |
| **Baixo** (decil 6–10) | fora do lote: sem ação com custo | | |

Leitura: alto valor com risco baixo concentra R$ 4,26 mi de receita em risco, mas o risco individual é baixo. Ali só
gastamos quando a Azul falhou (atraso grave). O resto vai para o gatilho.

## 2. Gatilho → ação (catálogo fechado)
| Gatilho | Ação | Benefício citado (KB) | Canal | Custo (P-17) | KPI |
|---|---|---|---|---|---|
| **A** · 2 atrasos > 60 min ou cancelamentos em 90 dias | Recuperação de serviço | Assistência material e reacomodação (regra ANAC, notícia do MPor de 23/09/2026); pontos são creditados na conta (pontos por nível). O crédito de cortesia é **decisão comercial sem regra pública** | Atendimento humano | 3% do CLV em pontos + R$ 20 | Evasão 6 m vs controle; tempo do gatilho ao contato |
| **B** · Azul saiu ou reduziu a rota favorita, com alternativa na malha | Oferta na rota favorita (conexão via SBKP, SBCF ou SBRF) | Pontos do nível | App (humano se alto valor) | 2% do CLV + R$ 1 (R$ 20 se alto valor) | % que voa a alternativa em 90 dias |
| **B** sem alternativa, ou sem consentimento de marketing | Contato humano | Nenhum: não promete benefício. Para Diamante, atendimento prioritário na central (KB) | Atendimento humano | R$ 20 | % contatado; evasão 6 m |
| **C** · concorrente derrubou a tarifa no par | Bônus de pontos (Diamante Unique: upgrade) | Pontos do nível; 40% de desconto no upgrade de cabine com pontos, só Unique | App (humano se alto valor) | 1,5% do CLV (upgrade 2%) + R$ 1 (R$ 20 se alto valor) | Share de voos no par; aceite |
| **Nível** · folga < 25% no nível de 2025 e meta de 2026 não cumprida | Desafio de manutenção de nível | Critérios do nível 2026 (6/10/12/26 trechos e pontos qualificáveis) | App (humano se alto valor) | 2% do CLV + R$ 1 (R$ 20 se alto valor) | % que bate a meta até 31/12 |
| Nenhum, não elegível, benefício sem regra, sem ROI ou guardrail violado | Abstenção (`sem_acao_automatica`) | — | — | R$ 0 | % de abstenção revisada pelo humano |

Teto de custo por cliente: mín(5% do CLV de 6 meses; R$ 500) + R$ 20. O custo do contato segue o canal: R$ 20 quando a ação exige atendimento humano ou o cliente é de alto valor. Sem consentimento de marketing, só recuperação
de serviço ou contato humano.

## 3. Por persona
As 6 personas vêm de `ml/resultados/personas*.csv` (k-means; separação fraca, silhueta 0,24: são faixas de um contínuo,
boas para comunicar). Custo médio por ação e contagens medidos no lote do agente.

| Persona | Clientes · alto valor | p evasão média · CLV 6 m médio | Gatilho mais comum → ação | Canal | Custo médio por ação | Receita protegida (100% aceite) | KPI principal |
|---|---|---|---|---|---|---|---|
| **Frequente de negócios** (2,1 trechos/mês, compra 7 dias antes) | 3.715 · 3.612 | 0,16 · R$ 9.486 | A → recuperação de serviço (339); nível → desafio (118); B → oferta (83) | Atendimento humano (quase todos alto valor) | recuperação R$ 343,90; desafio R$ 148,52 | R$ 319 mil (621 acionados) | Evasão 6 m vs controle no decil 1 |
| **Em ascensão** (frequência recente 2,7× a anterior) | 7.818 · 3.354 | 0,22 · R$ 2.284 | Nível → desafio (510); A → recuperação (163) | App; humano se alto valor | desafio R$ 66,61; recuperação R$ 125,60 | R$ 133 mil (824) | % que sobe ou mantém nível |
| **Multirrota** (60% dos voos na favorita) | 6.605 · 1.935 | 0,31 · R$ 2.163 | Nível → desafio (457); B → oferta (121); A (106) | App | desafio R$ 60,68; oferta R$ 62,74 | R$ 146 mil (832) | Share de voos na Azul nos pares do cliente |
| **Ocasional** (0,3 trecho/mês, tarifa R$ 877) | 11.621 · 1.005 | 0,41 · R$ 1.370 | Nível → desafio (668); B → oferta (84) | App | desafio R$ 61,08 | R$ 164 mil (867) | % que faz o próximo voo em 90 dias |
| **Caçador de tarifa** (R$ 416, compra 33 dias antes) | 10.352 · 94 | 0,42 · R$ 789 | Nível → desafio (193); B → oferta (37) | App | desafio R$ 37,30 | R$ 33 mil (264) | Custo por cliente salvo (valor baixo: só ROI positivo) |
| **Sem voo no histórico** | 9.889 · 0 | não elegível · R$ 478 | Nenhum: sem `p_evasao`, sem ROI estimável | — | R$ 0 | — | % que faz o 1º voo (só medir) |

O que fazer com cada uma:
- **Frequente de negócios:** é onde está o dinheiro (82,6% no top decil). Prioridade máxima para atraso grave. Contato
  humano, rápido. Nada de desconto amplo: o risco médio é baixo.
- **Em ascensão:** proteger a trajetória. O desafio de nível mostra só o que falta para manter a categoria.
- **Multirrota:** compara companhias por rota. B e C pesam mais. Oferta na rota e bônus de pontos, sempre com ROI.
- **Ocasional:** risco alto, valor médio. Ação digital barata; o desafio só quando a meta é alcançável.
- **Caçador de tarifa:** valor baixo. A maioria fica em abstenção (496 de 760 no lote). Não entrar em guerra de preço.
- **Sem voo no histórico:** sem ação automática. Fica fora do agente até ter histórico. Não há benefício de boas-vindas
  na KB, então não prometemos nenhum.

## 4. Como medir (o que falta para virar prova)
1. **Grupo de controle** sorteado (ex.: 10% de cada célula valor × risco sem ação). Sem ele, não há como separar o
   efeito da ação da evasão natural.
2. KPI de topo: evasão em 6 meses (mesma regra de P-13: voar ≤ 30% do esperado) e receita retida, tratado vs controle.
3. KPI de operação: % de propostas aprovadas, editadas ou descartadas pelo aprovador; tempo do gatilho ao contato;
   custo por cliente salvo.
4. KPI de justiça: taxa de oferta por região (hoje razão máx/mín 1,15, `ml/resultados/fairness_disparidade.csv`).
5. Depois de 2 ciclos: modelo de uplift para escolher quem muda de ideia com a oferta, não só quem tem risco.
