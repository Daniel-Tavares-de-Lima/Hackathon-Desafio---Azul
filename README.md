# ÓRBITA · Radar de Ameaças

Cliente de alto valor não vai embora do nada. Ele sai por uma ameaça concreta, que aparece em dados públicos. O ÓRBITA
vigia três ameaças e propõe a próxima melhor ação antes da evasão, sempre com aprovação humana.

| Ameaça | Sinal público | Fonte |
|---|---|---|
| A · Atraso grave | ≥ 2 voos com atraso > 60 min ou cancelados em 90 dias | ANAC VRA |
| B · Rota órfã | a Azul saiu do par ou reduziu a oferta ≥ 30% (contra o mesmo trimestre do ano anterior) | ANAC VRA |
| C · Escudo de rota | concorrente baixou a tarifa ≥ 15 pp abaixo da Azul no par, por 2 meses | ANAC tarifas |

Entre set/2025 e ago/2026, só com dados públicos, o radar detectou **17 pares em que a Azul saiu** e **82 em que
reduziu a oferta**.

> **Dados:** tudo vem de fontes públicas (ANAC, Consumidor.gov.br, RI da Azul) e de uma **base sintética** de 50 mil
> clientes. Não há nenhum dado real de cliente. A base sintética foi calibrada nos dados públicos e pode ser trocada
> pela base real sem reconstruir nada (ver "Do sintético ao real").

## Onde olhar primeiro

| Para | Abra |
|---|---|
| Entender o negócio | [docs/BUSINESS_CASE.md](docs/BUSINESS_CASE.md), [docs/ESTRATEGIA_CRM.md](docs/ESTRATEGIA_CRM.md) |
| Ver o demo | [app/README.md](app/README.md) (roteiro de cliques) e [docs/ROTEIRO_PITCH.md](docs/ROTEIRO_PITCH.md) |
| Conferir o rigor | [ml/model_card.md](ml/model_card.md), [docs/LIMITACOES.md](docs/LIMITACOES.md), [docs/PREMISSAS.md](docs/PREMISSAS.md) |
| Entender as decisões | [docs/ADR/](docs/ADR/) |
| Ver os dados | [docs/DICIONARIO_DADOS.md](docs/DICIONARIO_DADOS.md) e [contracts/](contracts/) |

## Como funciona

```
ANAC (VRA, tarifas)       ─┐
Consumidor.gov.br (ANAC)  ─┼─> bronze (CSV) -> silver (Parquet) -> gold (ameaças por rota, atrito)
                           │                                          │
base sintética de clientes ┘                                          v
                                       ml/: evasão, CLV, score, personas, motivos (SHAP)
                                                                      │
                                                                      v
                                       agent/: próxima melhor ação (catálogo fechado, regra citada,
                                               consentimento, teto de custo, aprovação humana)
                                                                      │
                                                                      v
                                       app/ (Streamlit: Radar de Ameaças)  ·  api/ (FastAPI)
```

- **Modelos** ([ml/model_card.md](ml/model_card.md)): LightGBM com validação temporal (treino até ago/2025, teste em
  fev/2026). A métrica é a AUC-PR, que chega a 0,415 contra uma base de 0,278. Os motivos de cada cliente vêm do SHAP,
  em português.
- **Agente** ([agent/](agent/)): a decisão é determinística, sem LLM e sem custo. Quando nenhuma regra pública sustenta
  uma ação, o agente se abstém. Um LLM local (Ollama) é opcional e só escolhe o tom da mensagem entre textos já aprovados.
- **IA responsável:** aprovação humana em toda ação, LGPD (consentimento de marketing), fairness por região reportada,
  circularidade do sintético declarada e auditoria independente em cada entrega.

## Rodar

Pré-requisitos: Python 3.12+ e GNU make (no Windows: `winget install ezwinports.make`).

```bash
make all        # ingest -> gold -> sintético -> ml -> atrito -> testes
make app        # painel em http://localhost:8501
make api        # API em http://localhost:8000/docs
```

- **Download da ANAC:** baixar a ANAC do zero leva cerca de 45 minutos, porque o servidor do VRA é lento. A ingestão
  é idempotente: com `data/bronze/` já presente, ela não baixa de novo. O time tem uma cópia do bronze.
- **Custo:** nada chama API paga. O `.env` vem de [.env.example](.env.example) e não guarda chave nenhuma.

## Do sintético ao real

O ponto de troca são os contratos de dados em [contracts/](contracts/): um YAML por tabela, com nomes, tipos e
nulidade.

- O SQL de [pipelines/sql/](pipelines/sql/) é ANSI. Roda em DuckDB aqui e no Snowflake da Azul sem reescrita.
- Para ligar dado real, basta preencher as tabelas `synthetic_*` com dados que obedeçam aos mesmos contratos. O teste
  [tests/test_contratos.py](tests/test_contratos.py) confere tipos e nulos.
- Detalhes em [docs/ADR/002-sql-ansi-duckdb-snowflake.md](docs/ADR/002-sql-ansi-duckdb-snowflake.md).

## Limitações

Estão listadas com franqueza em [docs/LIMITACOES.md](docs/LIMITACOES.md). As principais:

- os efeitos das ações são supostos;
- as regras do programa vêm de fontes secundárias e ainda serão conferidas por negócios;
- no cenário conservador, o programa não se paga.
