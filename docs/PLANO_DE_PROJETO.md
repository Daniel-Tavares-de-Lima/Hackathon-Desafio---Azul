# Plano de Projeto · ÓRBITA (08/10 a 26/10/2026)

## Tese em uma frase
Descobrir quem são os clientes que sustentam a margem da Azul, prever quem está prestes a sair,
e agir antes da reclamação, com um agente que só oferece o que as regras do Azul Fidelidade permitem.

## Decisão (08/10): ÓRBITA · Radar de Ameaças

## Diferenciais (o que a banca vai lembrar)
1. Radar de três ameaças em dados públicos: atraso (VRA), rota órfã (saída/redução da Azul) e concorrente na rota (tarifas ANAC).
2. Nível em risco: quem está perto de cair de Diamante/Safira recebe desafio de manutenção personalizado.
3. Troca sintético -> real sem reconstrução: contratos de dados + dbt com adapter DuckDB hoje, Snowflake amanhã.
4. IA transparente: toda recomendação mostra os 3 motivos (SHAP) e a regra do programa citada.

## Cronograma
| Sprint | Datas | Meta de saída | Subagentes |
|---|---|---|---|
| 0 Setup | 08 a 10/10 | Repo privado, `make` vazio rodando, fontes ANAC baixadas, contratos v1 | engenheiro-dados |
| 1 Dados | 11 a 14/10 | Base sintética 50k validada contra ANAC, camada gold pronta | gerador-sintetico, engenheiro-dados, analista-sentimento |
| 2 Modelos | 15 a 17/10 | CLV, evasão, personas, SHAP, fairness com métricas | cientista-ml |
| 3 Produto | 17 a 20/10 | Agente NBA + painel ponta a ponta. CONGELA ESCOPO 20/10 | engenheiro-agente-llm, dev-prototipo |
| Mentoria | 21 a 23/10 | Levar demo + 3 perguntas à Avanade, ajustar | todos + auditor-ia-responsavel |
| 4 Pitch | 23 a 25/10 | Business case, roteiro, gravação do vídeo | estrategista-pitch |
| Entrega | 25/10 noite | Submeter com 1 dia de folga (prazo oficial 26/10) | orquestrador |

## Riscos
| Risco | Mitigação |
|---|---|
| Arquivos ANAC grandes/lentos | Recorte 24 meses, só rotas domésticas, cache Parquet |
| "Modelo só reaprende o gerador" | Arquétipo latente oculto, ruído, declarar no model card |
| Agente alucinar benefício | Catálogo fechado + RAG com citação + guardrail que bloqueia |
| Coleta de reviews violar termos | Usar fonte que permite; registrar decisão |
| Escopo crescer | Congelamento 20/10; ideia nova vai para "próximos passos" do pitch |
| Vazamento de confidencialidade | Repo privado, sem prints públicos, sem logotipo oficial |
