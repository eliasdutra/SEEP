# Changelog V12

## Correções técnicas

- dever de interrupção do disjuntor separado do curto total da barra;
- cálculo do dever no ponto do disjuntor, retirando fontes a jusante do dispositivo;
- `Icu/Ics informado` separado de `classe mínima recomendada`;
- classe recomendada não é mais gravada automaticamente como rating físico;
- CB27 possui referência externa de 42,920 kA apenas para validação.

## Coordenograma

- uma característica efetiva por relé: `min(51, 50-TD, 50-INST)`;
- estágios 50 deixam de atravessar o gráfico inteiro como curvas independentes;
- legenda reduzida;
- filtros gerais com relés e Icc ativos por padrão;
- motores/LRC, inrush e I²t desativados inicialmente;
- foco por par de coordenação;
- eixos logarítmicos rotulados apenas nas décadas principais.

## Sistema especialista

- TMS permanece explicitamente preliminar quando faltam dados de partida;
- dever de interrupção usa fato próprio do disjuntor;
- recomendação de classe e dado físico de placa são tratados como conceitos diferentes.

## Validação

- novo `validation/reference_mod3_v12.py` com valores transcritos dos relatórios fornecidos;
- novo `validation/validate_v12_manual.py` para reproduzir o cálculo manual do Cable15/Bus17;
- testes novos para topologia a jusante de CB1/CB2/CB8/CB27, dever de interrupção e característica efetiva.

> **Nota da V28.1:** `reference_mod3_v12.py` e `validate_v12_manual.py` foram removidos. Eles descreviam o modelo completo (Bus3, Cable15, Bus17), anterior à redução do caso. Este changelog é mantido como registro histórico.
