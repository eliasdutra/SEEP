# Verificação técnica — Protection Studio V15

## 1. Escopo ativo

A V15 foi reduzida ao unifilar atual:

- GE-TG-5147001A → Cable1 → Bus1 (13,8 kV)
- Bus1 → Cable8 / CB8 → Bus10 → M-B-6 (6000 kW, 13,8 kV)
- Bus1 → T1 (11 MVA, 13,8/6,6 kV) → Bus2
- Bus2 → Cable2 / CB2 → Bus4 → M-B-0 (1600 kW, 6,6 kV)

Modelo ativo: 5 barras, 1 gerador, 1 transformador, 3 cabos, 2 motores, 4 zonas de proteção e 3 pares de coordenação.

## 2. Dados ETAP Protection incorporados

Para M-B-6 e M-B-0 foram preservados literalmente os valores exibidos nas telas do ETAP:

- 100% Vt → aceleração 2 s
- 80% Vt → aceleração 4 s
- 110% Vt → aceleração 8 s
- Hot Stall = 12 s
- Cold Stall = 40 s
- Asymmetrical Locked Rotor Current Factor = 1,6

A inferência automática usa somente o ponto nominal de 100% Vt = 2 s. Os pontos 80% e 110% são mostrados como fatos de origem, sem interpolação ou correção.

A opção Thermal Curve aparece habilitada no ETAP, porém a tabela aberta por `Points...` ainda não foi fornecida. Por isso a V15 não inventa a curva térmica completa.

## 3. Correntes de rotor bloqueado

- M-B-0: In = 154,40 A; LRC = 650%; ILR = 1003,60 A.
- M-B-6: In = 284,44 A; LRC = 650%; ILR = 1848,86 A.

## 4. Nova regra especialista de TMS

Regra `R-MOT-TMS-01` no ponto de LRC:

1. `t51(ILR) >= t_acc(100% Vt) + margem`
2. `t51(ILR) < Hot Stall`
3. respeitar a faixa de TMS do relé
4. depois verificar coordenação com o relé montante

Com margem de 0,30 s e IEC Very Inverse:

### M-B-0

- pickup preliminar 51P = 200 A
- `TMS mínimo pela partida = 0,684548...`
- `TMS máximo aproximado pelo Hot Stall = 3,571556...`
- candidato de estudo aplicado pelo especialista = **0,685**
- TMS inicial 0,20 produziria aproximadamente 0,672 s no LRC, abaixo dos 2,30 s exigidos para partida + margem.

### M-B-6

- pickup preliminar 51P = 400 A
- `TMS mínimo pela partida = 0,617107...`
- `TMS máximo aproximado pelo Hot Stall = 3,219689...`
- candidato de estudo aplicado pelo especialista = **0,620**
- TMS inicial 0,20 produziria aproximadamente 0,745 s no LRC, abaixo dos 2,30 s exigidos.

Esses valores são recomendações matemáticas de estudo. A resolução/passos reais do relé e a coordenação global ainda devem ser confirmadas.

## 5. Coordenograma

- O TCC local mostra In, ILR, partida em 100% Vt, Hot Stall e Cold Stall.
- O TCC geral usa **6,6 kV como base padrão** do caso reduzido; 13,8 kV permanece selecionável.
- A curva Thermal Limit completa não é desenhada enquanto os pontos do ETAP não forem fornecidos.
- Pares ativos:
  - CB2 → T1, falta de referência em Bus4
  - T1 → CB1, falta de referência em Bus2
  - CB8 → CB1, falta de referência em Bus10

## 6. Curto-circuito MIN de fase

O solver radial independente continua validado para as barras ativas. Valores LL MIN de referência:

- Bus01: 9,021 kA
- Bus1: 8,994 kA
- Bus10: 8,865 kA
- Bus2: 6,705 kA
- Bus4: 6,511 kA

Os valores externos são usados apenas para validação; não alimentam o solver.

## 7. Testes executados

- `pytest`: **43 testes aprovados**
- `python -m compileall`: OK
- `node --check static/app.js`: OK
- verificação de referências antigas no código ativo: OK

O ambiente desta execução não possui Flask/Pandapower instalados, portanto o servidor completo e o solver Pandapower MAX não foram executados aqui. Os testes unitários, solver radial independente, sintaxe Python e JavaScript foram verificados.

## 8. Pendências deliberadas

- tabela `Points...` da Thermal Limit Curve dos motores;
- ampacidade real dos cabos;
- Icu/Ics e tempo de abertura dos disjuntores;
- confirmação no ETAP do curto MAX do caso reduzido.
