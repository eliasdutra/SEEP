# Premissas e limites — V12 / Caso 01

## Fonte física

O modelo é fixo e deriva do Data Report, do unifilar e dos relatórios IEC 60909 do `Modelo_Estudo_de_Caso_2`. Os relatórios externos são usados para validação e rastreabilidade; não alimentam o solver Pandapower.

## Fluxo

- motores operam com os dados nominais utilizados no caso de fluxo apresentado;
- resistências de cabo para fluxo usam o conjunto exportado no Data Report;
- ampacidade: a do `Cable2` (81,3 A) foi lida da marca *Cable2 Ampacity* do STAR75 e entra no coordenograma
  como marca de topo; `Cable1` e `Cable8` continuam sem valor informado. Em nenhum caso a ampacidade é usada
  para afirmar carregamento percentual — ela é apenas desenhada como referência.

## Curto-circuito

- IEC 60909;
- MAX: motores assíncronos incluídos;
- MIN: motores excluídos;
- cabos usam resistência de curto a 20 °C do relatório;
- 3F, LL e LG são solicitados diretamente ao módulo de curto;
- LLG é calculado por componentes simétricas a partir de Z1/Z2/Z0 quando disponíveis;
- para sensibilidade 50/51 de fase, o caso crítico é `min(3F MIN, LL MIN)`;
- a coordenação é avaliada par a par no extremo da zona jusante.

## Dever de interrupção do disjuntor

A V12 separa três grandezas que não devem ser confundidas:

1. **Icc MAX que atravessa o disjuntor** — calculada no ponto imediatamente a jusante do disjuntor;
2. **critério de projeto** — nesta versão, `1,10 × Icc MAX`;
3. **Icu/Ics informado** — dado físico de placa/datasheet, nunca preenchido automaticamente.

Ao calcular a corrente que atravessa o disjuntor, as fontes/motores a jusante do próprio dispositivo são retirados da contribuição, pois alimentam a falta pelo lado da carga e não atravessam o disjuntor. Para CB27, por exemplo, MEQ3005 é retirado desse cálculo.

## Transformadores

- T1: 11 MVA, 13,8/6,6 kV, 8%, X/R 18,6, Dyn;
- T2: 2,5 MVA, 6,6/0,48 kV, 6%, X/R 10, Dyn;
- secundários Y solidamente aterrados;
- inrush cadastrado: 8 pu em 0,1 s para T1 e T2.

## Motores

Os três motores possuem LRC/impedância para contribuição de curto. O modelo de origem não possui tempo de aceleração, WR²/H, torque de carga nem curva térmica válida. Esses itens são representados como `None`/vazio e não são estimados.

## TCC

A V12 mostra, por padrão, uma única **característica efetiva** por relé:

`tempo efetivo = min(t51, t50-TD, t50-INST)`

Isso evita desenhar três funções independentes atravessando todo o gráfico. Nos modos caminho e geral, as correntes são referidas à mesma tensão-base. Icc MIN/MAX dos pontos usados pelos pares permanecem disponíveis como referências verticais. No modo geral, motores/LRC, inrush e I²t ficam desligados inicialmente para reduzir poluição visual e podem ser ativados pelo usuário.

Nenhuma recomendação com dados ausentes ou decisão de engenharia é tratada como ajuste final.
