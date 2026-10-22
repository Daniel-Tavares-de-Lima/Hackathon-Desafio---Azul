# ADR 005 · Só fontes públicas; reviews de loja recusados por termos de uso

**Status:** aceita (2026-10-20). **Detalhes:** P-01, P-18.

## Contexto
Zero dado real de cliente. Precisamos de sinais de ameaça e de atrito que a Azul reconheça.

## Decisão
- Ameaças A, B e C só com dado aberto da ANAC: VRA (atraso, cancelamento, oferta por rota) e microdados de tarifas
  domésticas, set/2024 a ago/2026.
- Atrito público: Consumidor.gov.br nos dados abertos republicados pela ANAC (licença cc-by), set/2024 a dez/2025.
- Clientes: base sintética calibrada nessas marginais públicas.
- **Reviews de loja recusados:** os termos do Google Play e da App Store proíbem coleta automatizada (e os
  `robots.txt` bloqueiam os caminhos de reviews); a página de termos do Reclame Aqui deu HTTP 403, e sem confirmação
  não coletamos.
- Leitor do export oficial de reviews (Play Console e App Store Connect) fica pronto para quando a Azul fornecer o
  arquivo.

## Consequências
- Sem texto livre de cliente: sem citações nem sentimento por frase.
- Consumidor.gov.br não tem 2026 publicado; a ponte com o atraso é só por companhia e mês.
- Regras do Azul Fidelidade vêm de fontes secundárias (página oficial com HTTP 403), "a conferir por negócios".
