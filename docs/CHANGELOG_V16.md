# Changelog V16

- Página de coordenogramas redesenhada para visualização sucinta.
- Três vistas fixas: M-B-0, M-B-6 e Geral.
- Ajustes e dados de engenharia removidos visualmente da tela TCC; continuam na tela Proteção.
- TCC M-B-0: relés efetivos, partida, Hot Stall, T1 inrush e faltas MIN dos pares.
- TCC M-B-6: relés efetivos, partida, Hot Stall e falta MIN Bus10.
- TCC Geral: somente relés efetivos e faltas MIN de referência.
- Resumo abaixo do gráfico reduzido a Par, falta MIN, Δt e estado.
- Backend ganhou `/api/tcc-concise/<view>` para evitar enviar informação visual desnecessária.
