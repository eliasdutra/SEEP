# Changelog V17

- Implementadas curvas de capacidade térmica **Hot** e **Cold** para M-B-0 e M-B-6.
- Curvas locais são ancoradas nos dados ETAP já disponíveis: In, ILR, Hot Stall e Cold Stall.
- Sem `Points...`, é usada aproximação térmica `t = t_stall (ILR²-In²)/(I²-In²)` e a legenda identifica a curva como **estimada**.
- `thermal_points`, quando preenchido futuramente, tem precedência sobre a aproximação.
- Coordenograma geral continua enxuto e não exibe Hot/Cold.
- Zoom dos coordenogramas locais foi reduzido para tornar as curvas de capacidade visíveis sem perder faltas MIN e inrush relevantes.
