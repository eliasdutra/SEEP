# Changelog V13

## 1. Curto MIN de fase corrigido

A coordenação 50/51 de fase passa a usar um solver radial IEC independente para 3F/LL no caso MIN. Ele propaga Z1 e Z2 a partir dos dados físicos do gerador, cabos e transformadores, com motores excluídos.

Motivo: o elemento `gen` do Pandapower aplica correções internas de curto que, neste Caso 01, produziam diferenças crescentes em barras próximas da fonte. A maior diferença observada era Bus10 LL MIN (~9%). O cálculo radial físico reproduz o relatório ETAP sem usar correntes ETAP como entrada.

Os valores Pandapower MIN brutos continuam preservados nos campos `3f_ka_pandapower` e `ll_ka_pandapower` para diagnóstico.

## 2. Estágio 50 instantâneo não usa mais 0 s como tempo físico

`phase_stage3_delay_s = 0` significa apenas que o estágio é instantâneo por ajuste.

Foi criado o campo:

- `phase_stage3_operating_time_s` — tempo real de atuação, a preencher com ETAP/datasheet;
- `breaker_opening_time_s` — tempo de abertura do disjuntor, informativo para tempo total de eliminação.

Se uma falta é eliminada pelo 50-INST e o tempo real não foi informado, a coordenação do par fica `PENDENTE`; o programa não calcula Δt usando 0 s fictício.

No gráfico, 0 s continua representado no piso logarítmico de 0,01 s apenas para visualização.

## 3. Estado da tabela de pares

A coluna de estado agora mostra:

- `Δt OK` — somente o critério temporal do par foi atendido;
- `Δt INSUF.` — margem temporal insuficiente;
- `PENDENTE` — faltam dados/tempo físico ou um relé não sensibiliza.

Isso evita interpretar a tabela como aprovação global do ajuste.

## 4. Interface

Foram adicionados campos para:

- tempo real do 50/50N instantâneo;
- tempo de abertura do disjuntor.

O TCC geral mantém característica efetiva, foco por par, Icc MIN/MAX e base comum.
