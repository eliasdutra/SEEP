# Changelog V11

## Coordenação

- Coordenação de fase alterada de uma única falta terminal para **pares principal/retaguarda**.
- Cada par usa o extremo da zona da proteção jusante como ponto de falta.
- Caminho principal:
  - CB27 → T2: Bus17;
  - T2 → T1: Bus3;
  - T1 → CB1: Bus2.
- Mantido o critério de falta mínima de fase `min(3F, LL)`.
- Correntes são convertidas para o nível de tensão nativo de cada relé antes do cálculo do tempo.

## Coordenograma geral

- O escopo geral passa a ser o padrão ao abrir a tela de coordenograma.
- Incluídos todos os relés 50/51 em base comum.
- Incluídas referências de corrente nominal e LRC dos motores.
- Incluídos pontos de inrush de T1/T2.
- Incluídas linhas verticais de Icc MIN/MAX de fase nos pontos usados pelos pares.
- Adicionados filtros por grupo de elementos.
- Adicionada tabela de pares com corrente vista, estágio, tempo, Δt e estado.

## Sistema especialista

- `R-COORD-01` atualizado para coordenação par a par.
- `run_path_expert()` agora explica cada par separadamente.
- `collect_path_facts()` passa a coletar fatos por par.
- Mantida a política de não inventar dados ausentes.

## Testes

- Adicionado `tests/test_v11_pairwise.py`.
- 27 testes aprovados no ambiente de desenvolvimento.
