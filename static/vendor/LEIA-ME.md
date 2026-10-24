# Biblioteca de gráficos

`plotly.min.js` está vendorizado aqui para que a aplicação funcione **sem internet**.

## Este arquivo é 93% do peso do projeto

O bundle completo do Plotly traz **49 tipos de gráfico**. Esta aplicação usa **dois**:

| tipo | onde |
|---|---|
| `scatter` | todas as curvas dos coordenogramas e do Cálculo 51 |
| `bar` | gráfico de barras da tela de Curto-circuito |

Vêm junto, sem serem usados: mapas Mapbox, gráficos 3D em WebGL, mapas geográficos,
malhas de contorno de países, diagramas Sankey, candlestick financeiro, coordenadas
paralelas e mais 40 tipos.

## Como reduzir (sem perder nenhuma função)

Troque pelo bundle **basic** do Plotly, que contém `scatter`, `bar` e `pie` — cobre
tudo que a aplicação usa, incluindo eixo logarítmico, anotações com seta, formas
(`shapes`) e o `Plotly.downloadImage` do botão *Exportar PNG*.

1. Baixe `plotly-basic.min.js` na **mesma versão** que está aqui hoje (3.3.1):
   - cdnjs: `https://cdnjs.cloudflare.com/ajax/libs/plotly.js/3.3.1/plotly-basic.min.js`
   - ou npm: `npm pack plotly.js-basic-dist-min@3.3.1`
2. Salve por cima de `static/vendor/plotly.min.js`, **mantendo esse nome**.
   Assim o `templates/index.html` não precisa de nenhuma alteração.
3. Abra a aplicação e confira as três coisas que dependem do Plotly:
   - as quatro vistas do Coordenograma (usam `scatter`);
   - a tela de Curto-circuito (é a única que usa `bar`);
   - o botão **Exportar PNG** do coordenograma.

Se algo não renderizar, basta restaurar o arquivo anterior — nenhuma outra parte do
projeto muda.
