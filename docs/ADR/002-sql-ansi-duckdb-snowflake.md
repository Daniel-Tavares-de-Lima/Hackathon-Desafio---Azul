# ADR 002 · SQL ANSI + DuckDB local → Snowflake, sem dbt

**Status:** aceita. **Detalhes:** `pipelines/build_gold.py`, `pipelines/sql/`, `contracts/`.

## Contexto
A Azul usa Snowflake. Nós temos notebook e custo zero. A troca sintético → real não pode exigir reescrever o projeto.

## Decisão
- Silver e gold em Parquet, lidos por DuckDB (local, grátis, sem servidor).
- A lógica das ameaças fica em SQL padrão ANSI (`route_exits.sql`, `route_disruptions.sql`, `route_competition.sql`).
  Só o executor (`build_gold.py`) é específico de DuckDB.
- Cada tabela tem um contrato YAML (19 em `contracts/`): colunas, tipos, nulos, grão. O build valida a gold contra o
  contrato antes de publicar.
- **Sem dbt.** O plano original previa dbt; para três modelos SQL e um prazo curto, um executor de 1 arquivo com
  validação de contrato resolveu com menos peças.

## Por quê
O contrato é o ponto de troca: a Azul entrega tabelas reais com a mesma estrutura das `synthetic_*` e o resto do
pipeline não muda.

## Consequências
- O SQL **não foi executado no Snowflake** (sem conta). A portabilidade é por construção, a conferir no primeiro
  teste.
- Se o número de modelos SQL crescer, adotar dbt (adapter Snowflake) passa a valer a pena.
- Modelos e agente leem Parquet; no Snowflake, trocar a leitura pelo conector oficial.
