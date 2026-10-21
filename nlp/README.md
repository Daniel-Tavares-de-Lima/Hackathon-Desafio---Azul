# nlp/ · Reviews do app (plugue para o export oficial)

Situação em 2026-10-20: **sem dado real**. Google Play, App Store e Reclame Aqui proíbem coleta automatizada nos
termos de uso (P-18). O atrito público do painel vem do Consumidor.gov.br (`gold.friction_themes`, sem texto). Este
diretório fica pronto para quando a Azul entregar o export oficial dos reviews.

## Fluxo
1. Coloque os arquivos em `data/bronze/reviews_export/` (fora do git):
   - Google Play Console: `reviews_<pacote>_AAAAMM.csv` (relatório de avaliações, UTF-16);
   - App Store Connect: resposta JSON de `GET /v1/apps/{id}/customerReviews` salva como `.json` (a Apple não tem
     export CSV de reviews).
2. `make nlp` (ou `python -I pipelines/ingest_reviews_export.py` e depois `python -I nlp/reviews_sentiment.py`).
3. Saída: `data/silver/reviews/data.parquet` (contrato `contracts/export_reviews.yaml`) e
   `data/gold/review_themes/data.parquet` (contrato `contracts/export_review_themes.yaml`), tabela irmã de
   `gold.friction_themes` com grão fonte × tema × mês × sentimento. Escolhi tabela irmã em vez de juntar à
   `friction_themes` porque as medidas são outras (sentimento de review contra nota e resolução de reclamação).

## Anonimização (na ingestão)
Autor, apelido, aparelho, idioma, link, ids e a resposta da empresa (que pode ter nome de atendente) nunca são lidos.
No texto, regex troca e-mail, CPF, telefone, localizador (6 caracteres maiúsculos com letra e dígito) e nome próprio
logo depois de "atendente", "comissário(a)", "funcionário(a)", "piloto", "chamado(a)", "meu nome é", "sou o/a".
Nome solto no meio do texto **não** é detectado: conferir numa amostra do export real antes de publicar qualquer coisa.

## Regras
- **Tema (multirrótulo):** texto minúsculo e sem acento; recebe cada tema com algum padrão casando a partir do início
  de uma palavra (regex em `TEMAS`, `reviews_sentiment.py`; palavra curta com fronteira no fim, ex. `pontos?\b` não
  casa "pontual"). Nenhum → `outro`. Taxonomia igual à de `gold.friction_themes`: atraso/cancelamento, bagagem,
  reembolso, canais de venda/app, atendimento, pontos/resgate, preco, outro. "canais de venda/app" é o nome fiel ao
  problema do Consumidor.gov.br (acesso aos canais de venda); em review de loja cobre o app e o check-in nele.
- **Sentimento:** nota 1–2 negativo, 3 neutro, 4–5 positivo. Léxico = positivas − negativas, com "não/nunca/nem"
  invertendo a palavra seguinte. Nota 3 com saldo ≠ 0 segue o léxico. Nota 4–5 com saldo ≤ −2 vira negativo
  (elogio na nota, reclamação no texto). Nota 1–2 com saldo ≥ 2 vira neutro.
- Limites conhecidos: radicais abertos ("erro", "atend", "cobr") casam derivados de outro sentido; ironia e negação longa
  passam; léxico pequeno.

## Teste e validação
- `python -I nlp/tests/test_reviews.py`: 20 reviews **fictícios** (`nlp/tests/fixture_play.csv`,
  `fixture_appstore.json`, marcados "[FICTICIO]", sem empresa real). Confere leitura UTF-16, anonimização, temas,
  sentimento e os dois contratos.
- **Pendente:** validação manual de 100 amostras estratificadas (acurácia de sentimento, precisão/recall por tema)
  só quando houver export real. Se for feita por assistente de IA, marcar a amostra e pedir conferência humana do
  time antes de usar os números. Não versionar texto completo de terceiros (só id interno, trecho curto
  parafraseado e rótulos).
