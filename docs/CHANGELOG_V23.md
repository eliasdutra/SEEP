# V23 — curva térmica real dos motores via ETAP Points

## Alteração principal

Os coordenogramas dos motores agora desenham a característica térmica `M-B-0` e `M-B-6` usando diretamente os pontos de `Thermal Curve Points > Stator-Hot` fornecidos no ETAP.

Pontos cadastrados para ambos os motores:

- 1,55 × FLA → 1000 s
- 1,70 × FLA → 500 s
- 1,90 × FLA → 300 s
- 2,40 × FLA → 150 s
- 3,00 × FLA → 87 s
- 3,60 × FLA → 60 s

A tabela Stator-Cold do ETAP está vazia/zerada; portanto nenhuma curva Cold é fabricada.

## Resultado nos TCCs

### M-B-0
- Relay11 · OC1
- **M-B-0** — Thermal Curve real do ETAP
- M-B-0-100% — partida
- Cable2 - P
- 3F MAX e LL MIN

### M-B-6
- Relay3 · OC1
- **M-B-6** — Thermal Curve real do ETAP
- M-B-6-100% — partida
- Cable8 - P
- 3F MAX e LL MIN

As escalas fixas do ETAP implementadas na V22 foram preservadas.
