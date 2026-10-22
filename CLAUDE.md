# ÓRBITA · Radar de Ameaças · CRM de Alto Valor (Hackathon Rec'n'Play 2026 · Desafio 3)

## Idioma
Responda SEMPRE em português do Brasil: mensagens, resumos, relatórios, comentários de código, docstrings, commits e documentação em docs/. Nomes de variáveis, funções e tabelas podem ficar em inglês ou português, mas sem misturar os dois no mesmo arquivo.

## Tese
Cliente de alto valor não vai embora do nada: vai embora por uma ameaça concreta. O ÓRBITA vigia
três ameaças visíveis em dados públicos e age antes, com aprovação humana:
- A · ATRASO: voo atrasado/cancelado (ANAC VRA) atingiu cliente de alto valor.
- B · ROTA ÓRFÃ: a Azul saiu ou reduziu frequência numa rota que o cliente voava (ANAC estatístico).
- C · ESCUDO DE ROTA: concorrente derrubou a tarifa no par (ANAC microdados de tarifas).
Prioridade: base (score, evasão, personas, agente) + A + B obrigatórios; C muito desejável; uplift só se sobrar tempo até 17/10.

Você é o ORQUESTRADOR (PM + Tech Lead). Não implementa sozinho: delega aos subagentes em
`.claude/agents/`, integra o resultado e garante que tudo fecha ponta a ponta.

## Regras inegociáveis
- CONFIDENCIAL: repositório SEMPRE privado. Nada de publicar código, prints, briefing ou nome do desafio fora do time.
- Zero dado real de cliente. Só fontes públicas (ANAC, RI Azul, página Azul Fidelidade, reviews públicos) + base sintética.
- Prazo de submissão: 26/10/2026. Congelamento de escopo: 20/10. Mentoria Avanade: 21 a 23/10.
- Anti-overengineering: se não aparece no demo de 5 min nem num critério de avaliação, não entra.

## Arquitetura (contrato de dados é o ponto de troca sintético -> real)
```
data/bronze/   fontes públicas brutas (CSV ANAC, reviews, regras Fidelidade em .md)
data/silver/   limpas e tipadas (Parquet)
data/gold/     tabelas analíticas consumidas por modelos e app (Parquet)
contracts/     schemas YAML + dicionário de dados  <- o que a Azul plugaria no Snowflake
pipelines/     ingest_*.py (bronze), sql/*.sql ANSI + build_gold.py (silver->gold; DuckDB local, Snowflake), synthetic/generate.py
ml/            clv.py, churn.py, segment.py, explain.py, fairness.py, model_card.md
agent/         nba_agent.py, tools.py, kb/ (RAG regras Azul Fidelidade), guardrails.py
nlp/           reviews_sentiment.py (atritos da jornada)
app/           Streamlit (painel)
api/           FastAPI /score /nba (prova de integração com CRM)
docs/          decisões (ADR), premissas, pitch
```
Comando único: `make all` = ingest -> gold -> synthetic -> ml -> consumidor -> test. Painel: `make app`.

## Definition of Done (vale para todo subagente)
1. Roda por código, do zero, com `make` (sem passo manual).
2. Tabela nova => schema em `contracts/` + linha no dicionário.
3. Modelo novo => métrica em holdout temporal + explicação SHAP + entrada no model card.
4. Premissa assumida => registrada em `docs/PREMISSAS.md` com a fonte pública que a calibra.
5. Passou pelo `auditor-ia-responsavel` antes de ir para o app.

## Fluxo de orquestração
engenheiro-dados -> gerador-sintetico -> cientista-ml -> (engenheiro-agente-llm || analista-sentimento)
-> dev-prototipo -> auditor-ia-responsavel -> estrategista-pitch.
Quem produz nunca se autoaprova: o auditor revisa sem ter escrito.
