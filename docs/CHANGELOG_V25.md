# V25 — Cable-P somente na região de curto tempo

## Correção principal

A curva térmica do cabo (`Cable2-P`, `Cable8-P`) não é mais prolongada até 1000 s.

Nos STAR do ETAP do caso atual, a curva `Cable-P` é mostrada somente na região de curto tempo. A V25 passa a desenhá-la em:

- `t_min = 0,01 s`
- `t_max = 10 s`

Acima disso, a referência do cabo é a **ampacidade** (reta vertical), quando esse valor estiver informado.

## Equações preservadas

Quando existe `K²S²` do ETAP:

`t = K²S² / I(kA)²`

- Cable2: `K²S² = 5,23 kA²s`
- Cable8: `K²S² = 115,03 kA²s`

## Curvas dos motores

As curvas térmicas reais `M-B-0` e `M-B-6`, obtidas dos `Thermal Curve Points`, continuam no coordenograma. As curvas de partida `M-B-0-100%` e `M-B-6-100%` também permanecem.
