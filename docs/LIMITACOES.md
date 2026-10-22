# Limitações · o que o ÓRBITA ainda não prova

1. **Base sintética e circularidade.** Os 50.000 clientes são fictícios. Os efeitos de evasão, os arquétipos e os
   pontos são regras que nós escrevemos no gerador (P-06, P-13). Quando o modelo "descobre" que atraso grave aumenta a
   evasão, ele devolve a regra que colocamos. As métricas não valem para clientes reais. Só as marginais (tarifa,
   rota, atraso, cancelamento, aeroporto de casa) são calibradas em dado público.
2. **Efeitos das ações são supostos.** Recuperação 25%, oferta na rota 20%, desafio 20% etc. são calibração própria
   (P-17), sem experimento. Todo ROI e toda receita protegida dependem deles. No cenário conservador o programa não se
   paga (ROI −0,06, `docs/BUSINESS_CASE.md`).
3. **Sem uplift.** O score diz quem vale proteger e quem tem risco, não quem muda de ideia com a oferta. Exige grupo
   de controle real.
4. **LightGBM ≈ logística no temporal.** Na validação temporal o LightGBM não supera a logística RFM (AUC-PR 0,415 x
   0,425). O ganho aparece só na previsão out-of-fold do mesmo corte, que não é validação temporal (ADR 001).
5. **KB com fontes secundárias.** A página oficial do Azul Fidelidade devolveu HTTP 403. Níveis, benefícios e Status
   Match vêm de blogs de milhas, "a conferir por negócios". A KB diz 1 ponto qualificável por real; o gerador usa 0,5.
   O texto integral da Resolução ANAC 400 não foi lido. Azul One não tem critério público.
6. **Consumidor.gov.br sem 2026.** O arquivo de 2026 não estava publicado (set/2024 a dez/2025). O denominador é voo
   doméstico, mas as reclamações incluem voo internacional.
7. **Escala para a Azul real é ilustrativa.** Não há número público de membros por nível nem de receita por nível. A
   escala usa a razão da base sintética sobre a receita de passageiros do RI (P-19).
8. **Snowflake não testado.** O SQL é ANSI por construção, mas não rodou no Snowflake (ADR 002).
