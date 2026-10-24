# Changelog V14

## Coordenação instantânea

- adicionado limite de catálogo `instantaneous_trip_time_max_s = 0.050 s` ao Sepam Series 40 M40;
- o tempo típico de `0.035 s` é registrado apenas como referência;
- tempo exato informado pelo usuário continua tendo prioridade;
- limite máximo do **relé jusante** é usado para calcular um limite inferior conservador de Δt;
- a tabela mostra `Δt ≥ valor` quando a aprovação é baseada nesse limite;
- limite máximo do relé montante nunca é usado para aprovar seletividade.

## Cabos

- Cable1, Cable8, Cable2 e Cable15 são Cu/XLPE no modelo físico;
- defaults térmicos: `k=143`, `θi=90 °C`, `θf=250 °C`;
- curvas I²t deixam de aparecer como pendentes por ausência de k;
- valores continuam editáveis.

## Interface

- zonas lógicas T1/T2 deixam de mostrar Icc/disjuntor como `N/A` de erro;
- nota dinâmica informa limite de catálogo do instantâneo;
- nota dinâmica informa a origem do k Cu/XLPE;
- tabela diferencia tempo exato de `≤ tempo de catálogo`;
- tabela diferencia `Δt =` e `Δt ≥`.
