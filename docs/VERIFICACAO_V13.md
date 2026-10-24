# Verificação técnica — Protection Studio V13

## Objetivo

Corrigir os três pontos encontrados na revisão visual da V12:

1. diferença de aproximadamente 9% em Bus10 LL MIN;
2. uso de `0,000 s` como se fosse tempo físico do 50 instantâneo;
3. rótulo `APROVADO` confundindo aprovação de Δt com aprovação global do ajuste.

## Curto-circuito MIN de fase

A V13 implementa um solver radial independente de 3F/LL MIN usando somente dados físicos do modelo.

Para a única fonte síncrona:

- Z1 vem de Xd'' e X/R;
- Z2 vem de X2 e X2/R2;
- cabos usam R1/X1 a 20 °C e paralelos físicos;
- transformadores usam Z% e X/R, referidos ao nível de tensão seguinte;
- motores são excluídos no cenário MIN;
- cmin = 1,00 acima de 1 kV e 0,95 em 0,48 kV, conforme o caso fornecido.

### Comparação com o ETAP MIN fornecido

| Barra | 3F V13 (kA) | 3F ETAP (kA) | erro | LL V13 (kA) | LL ETAP (kA) | erro |
|---|---:|---:|---:|---:|---:|---:|
| Bus01 | 11,4797 | 11,480 | -0,0027% | 9,0208 | 9,021 | -0,0025% |
| Bus1 | 11,4425 | 11,443 | -0,0041% | 8,9940 | 8,994 | +0,0002% |
| Bus2 | 8,0043 | 8,004 | +0,0041% | 6,7046 | 6,705 | -0,0055% |
| Bus3 | 32,7204 | 32,720 | +0,0011% | 28,0373 | 28,037 | +0,0010% |
| Bus4 | 7,7718 | 7,772 | -0,0023% | 6,5112 | 6,511 | +0,0024% |
| Bus10 | 11,2740 | 11,274 | +0,0002% | 8,8650 | 8,865 | ~0,0000% |

A diferença anterior de Bus10 foi eliminada. A causa não era Cable8: a soma manual de Z1/Z2 de Bus1 + Cable8 reproduz exatamente Bus10 do ETAP. A divergência vinha do equivalente de fonte/correções internas do elemento de geração usado no cálculo MIN do Pandapower.

## Bus17

Bus17 não existe no resumo ETAP fornecido, então permanece como ponto calculado. O solver radial, usando os comprimentos físicos em metros do modelo, fornece aproximadamente:

- 3F MIN = 19,626 kA;
- LL MIN = 16,897 kA.

O cálculo manual anterior usando os comprimentos arredondados exportados em pés (164,0 ft) resulta em LL ≈ 16,899 kA. A diferença é apenas de arredondamento de comprimento.

## 50 instantâneo

A V13 separa:

- delay programado do estágio 3;
- tempo real de operação do 50 instantâneo;
- tempo de abertura do disjuntor.

Se `delay programado = 0` e `tempo real do 50 instantâneo` não foi informado, o estágio é reconhecido como atuante, porém `time_s = None` para coordenação. O par fica PENDENTE e Δt não é aprovado.

## Testes executados

- `python -m compileall`: OK;
- `node --check static/app.js`: OK;
- suíte automatizada: **38 passed**;
- comparação independente V13 x ETAP MIN: OK, erros < 0,006% nas barras com referência.

## Dados ainda necessários para fechar o estudo

Para transformar os pares com 50-INST em coordenação temporal aprovada, obter no ETAP/datasheet:

1. tempo real de operação do estágio 50 instantâneo dos relés envolvidos;
2. tempo de abertura/interrupção dos disjuntores físicos, se quisermos também mostrar tempo total de eliminação;
3. Icu/Ics reais dos disjuntores;
4. tempo de aceleração/curva térmica dos motores;
5. ampacidade e constante adiabática k dos cabos, se o estudo térmico for incluído.
