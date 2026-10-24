# Arquitetura de proteção V9

## Caminho principal

`MEQ3005 → Cable15 → CB27/Sepam M40 → T2 → P14x → T1 → P14x → CB1/P14x → gerador`

A lista representa a cadeia de seletividade de **fase** usada no caminho principal. Os identificadores `R-T1` e `R-T2` são posições lógicas de proteção de sobrecorrente no estudo; não substituem um identificador de disjuntor que não foi fornecido.

## Funções

Cada posição possui, para fase e para neutro, espaço para:

- estágio 1: inverso;
- estágio 2: tempo definido;
- estágio 3: instantâneo.

## Curve shift

Para comparar curvas de diferentes níveis em um mesmo TCC de fase:

`I_ref = I_local × V_local / V_ref`

A regra preserva a potência aparente trifásica e é utilizada apenas para magnitude de corrente de fase equilibrada. Não deve ser usada para transferir corrente de sequência zero através de um enrolamento delta.

## Cabo I²t

Com `n` cabos idênticos em paralelo e divisão uniforme de corrente:

`t = (k × n × S / I_total)²`

A V9 não escolhe `k` automaticamente. O valor deve ser confirmado com a norma/fabricante e temperaturas do estudo.
