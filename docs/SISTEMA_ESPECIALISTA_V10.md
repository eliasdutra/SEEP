# Sistema Especialista — Protection Studio V10

## 1. Objetivo

Separar claramente o cálculo elétrico da tomada de decisão de proteção. O Pandapower fornece o estado elétrico e as correntes de curto; o sistema especialista interpreta esses fatos segundo uma base de regras e explica cada conclusão.

## 2. Camadas

### Base de fatos — `core/facts.py`

Fatos típicos de uma zona:

- tipo de aplicação: motor, transformador ou montante;
- corrente nominal protegida;
- LRC do motor ou inrush do transformador;
- dados do cabo;
- faltas 3F, LL, LG e LLG nos casos MIN/MAX;
- dados ausentes;
- cobertura de validação externa.

### Base de regras — `core/rules.py`

Exemplos:

- `R-CT-01`: TC >= 1,15 × In;
- `R-51-01`: pickup 51P >= 1,15 × In;
- `R-MOT-50-01`: 50P-TD >= max(1,25 × ILR, 4 × I51);
- `R-MOT-START-01`: sem tempo de partida não há aprovação final da curva 51 contra aceleração;
- `R-SENS-01`: sensibilidade usa a menor falta de fase MIN, `min(3F, LL)`;
- `R-BRK-01`: dever de interrupção considera a maior falta MAX disponível;
- `R-COORD-01`: Δt entre relés consecutivos deve superar a margem configurada.

### Motor de inferência — `core/inference.py`

O motor:

1. coleta fatos;
2. escolhe regras aplicáveis;
3. executa cálculos determinísticos;
4. classifica cada regra;
5. monta recomendações explicadas;
6. lista pendências;
7. determina se o ajuste pode ou não ser chamado de final.

## 3. Caso MEQ3005

Dados disponíveis no modelo:

- motor: MEQ3005;
- potência: 90 kW;
- tensão: 0,48 kV;
- In: 144,22 A;
- LRC: 600%;
- ILR: 865,32 A;
- relé: Sepam M40;
- cabo: Cable15.

Regras determinísticas preliminares:

### TC

`1,15 × 144,22 = 165,853 A`

Relação padronizada seguinte: `200/1 A`.

### 51P

`1,15 × 144,22 = 165,853 A`

Pickup padronizado seguinte: `200 A`.

### 50P-TD

`ILR = 6 × 144,22 = 865,32 A`

`1,25 × ILR = 1081,65 A`

`4 × I51 = 800 A`

Logo:

`max(1081,65; 800) = 1081,65 A`

Ajuste padronizado seguinte: `1200 A`.

Esses valores são recomendações preliminares explicáveis. A aprovação final permanece bloqueada enquanto o tempo de partida e a curva térmica do motor não estiverem disponíveis.

## 4. Curto-circuito crítico

A V9 usava 3F MIN diretamente na sensibilidade e na coordenação de caminho. A V10 corrige isso para proteção de fase:

`I_fase,min = min(I_3F,min, I_LL,min)`

Nos relatórios fornecidos, LL MIN é menor que 3F MIN nas barras resumidas, portanto essa mudança é tecnicamente relevante para sensibilidade e seletividade.

Para dever de interrupção:

`I_max,duty = max(I_3F,max, I_LL,max, I_LG,max, I_LLG,max)`

A recomendação preliminar aplica 10% de margem e escolhe a classe padronizada seguinte.

## 5. Dados ausentes

A V10 não estima automaticamente:

- tempo de aceleração do motor;
- curva térmica do motor;
- ampacidade do cabo;
- `k` adiabático do cabo.

A ausência desses dados aparece como **PENDENTE** e bloqueia a classificação de ajuste final quando o dado é necessário para a conclusão.

## 6. Interface

Na tela **Sistema especialista**, cada zona mostra:

- fatos principais;
- falta MIN crítica;
- maior falta MAX;
- recomendações;
- regra responsável por cada recomendação;
- explicação matemática;
- pendências;
- estado global;
- coordenação do caminho sob demanda.

O usuário ainda pode abrir o coordenograma e editar parâmetros, mas a lógica de decisão fica visível antes do gráfico.
