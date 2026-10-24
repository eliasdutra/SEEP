# Verificação técnica — Protection Studio V12

Data da revisão: 24/08/2026.

## Escopo verificado

A revisão V12 foi feita para corrigir os problemas observados no coordenograma geral da V11 e para manter separadas as grandezas de estudo das grandezas físicas informadas pelo usuário.

### 1. Coordenograma

- O relé é desenhado pela **característica efetiva**: `min(t51, t50-TD, t50-INST)`.
- Os estágios 50 não aparecem mais como linhas independentes atravessando todo o gráfico.
- O geral trabalha em uma tensão-base comum e permite foco por **par de coordenação**.
- Motores/LRC, inrush e cabos I²t ficam opcionais para reduzir poluição visual.
- Os eixos logarítmicos rotulam apenas as décadas principais.

### 2. Coordenação seletiva

A coordenação principal usa os pares:

| Par | Barra de falta |
|---|---|
| CB27 → T2 | Bus17 |
| T2 → T1 | Bus3 |
| T1 → CB1 | Bus2 |

Os demais ramais usam CB2 → T1 em Bus4 e CB8 → CB1 em Bus10.

Para fase, a referência mínima é `min(3F MIN, LL MIN)` e cada corrente é referida ao nível de tensão do relé antes do cálculo de tempo.

### 3. Dever de interrupção

A capacidade física do disjuntor não é mais preenchida automaticamente.

O programa separa:

1. `Icc MAX no disjuntor` — cálculo;
2. `Icc MAX × 1,10` — critério de projeto adotado;
3. `classe mínima recomendada` — recomendação;
4. `Icu/Ics informado` — placa/datasheet, entrada do usuário.

Para calcular o dever do disjuntor, a falta é colocada na barra do lado da fonte, imediatamente antes da impedância do alimentador, e as contribuições de motores que estão a jusante daquele disjuntor são excluídas. Assim o valor representa a corrente que atravessa o próprio dispositivo e não o curto total somado com fontes do lado da carga.

Referências externas disponíveis apenas para conferência:

- CB27: 42,920 kA, LG, contribuição Bus2 → Bus3 no relatório MAX;
- CB1: 12,513 kA, 3F, contribuição do gerador para Bus01 no relatório MAX.

Esses números **não são usados como entrada do solver**.

### 4. Verificação manual independente — Cable15 / Bus17 MIN

Dados utilizados do relatório:

- Cable15: 35 mm², 3 cabos em paralelo por fase, 164 ft;
- R1 = 0,1601632 Ω/1000 ft;
- X1 = 0,0274320 Ω/1000 ft;
- R0 = 0,2546595 Ω/1000 ft;
- X0 = 0,0696773 Ω/1000 ft;
- Bus3 MIN: Z1 = 0,00070 + j0,00802 Ω;
- Z2 = 0,00075 + j0,00818 Ω;
- Z0 = 0,00055 + j0,00550 Ω;
- cmin em 0,48 kV = 0,95.

Resultados independentes:

- `Z1 Cable15 = 0,008755588 + j0,001499616 Ω`;
- `Z0 Cable15 = 0,013921386 + j0,003809026 Ω`;
- Bus17 3F MIN ≈ **19,621 kA**;
- Bus17 LL MIN ≈ **16,899 kA**;
- Bus17 LG MIN ≈ **17,976 kA**;
- Bus17 LLG MIN ≈ **20,017 kA**.

O script estava em `validation/validate_v12_manual.py`.

> **Removido na V28.1.** Ele calculava Bus17/Cable15/Bus3, do modelo completo anterior. O caso atual é o reduzido (Bus01, Bus1, Bus10, Bus2, Bus4), então o script produzia números corretos para um sistema que este projeto não contém mais. A verificação vigente é `validation/validate_v28_etap_star75.py`.

### 5. Testes executados neste pacote

- `pytest`: **34 testes aprovados**;
- `python -m compileall`: aprovado;
- `node --check static/app.js`: aprovado;
- validação manual independente: aprovada.

## Limitação da verificação neste ambiente

O ambiente usado para empacotar esta revisão não possui Flask nem Pandapower instalados. Portanto, não foi possível iniciar o servidor Flask nem executar o solver Pandapower real aqui. Essa parte deve ser validada no ambiente Windows criado por `setup_windows.bat`.

A suíte foi construída para testar a lógica de regras, coordenação, topologia, TCC efetivo, separação Icu/Ics e os cálculos manuais sem depender dessas bibliotecas em tempo de teste.

## Critério de aceite recomendado no Windows

Após instalar as dependências e abrir o programa:

1. abrir `Z-MEQ3005 / CB27`;
2. confirmar que `Icu/Ics informado` começa vazio;
3. confirmar que o painel mostra `Icc MAX no disjuntor` calculado;
4. comparar o resultado calculado para CB27 com a referência externa de 42,920 kA;
5. verificar que a classe recomendada é 50 kA se o cálculo ficar próximo da referência;
6. conferir que o TMS do MEQ3005 continua marcado como preliminar enquanto o tempo de aceleração não for informado;
7. abrir o coordenograma geral e alternar `CB27 → T2`, `T2 → T1`, `T1 → CB1` e `Todos`;
8. confirmar que cada relé aparece por uma única característica efetiva.

Se o dever de CB27 calculado pelo Pandapower divergir significativamente de 42,920 kA, a divergência deve ser investigada antes de aceitar a capacidade interruptiva recomendada.
