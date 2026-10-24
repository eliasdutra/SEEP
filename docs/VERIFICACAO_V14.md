# Verificação técnica — Protection Studio V14

## 1. Itens atacados

A V14 foi criada para resolver os pendentes visíveis no coordenograma geral V13:

1. três pares de coordenação pendentes porque o estágio 50-INST do Sepam tinha delay programado 0 e tempo físico não informado;
2. quatro curvas de cabo I²t pendentes por `k` não preenchido;
3. `N/A` de dever de interrupção nas zonas lógicas T1/T2, que era visualmente confundido com erro.

## 2. Sepam Series 40

A documentação pública da Schneider Electric informa para Sepam Series 20/40 que a saída instantânea confirmada da proteção de sobrecorrente 50/51 opera em menos de 50 ms; a FAQ também informa valor típico de 35 ms em condição citada pelo fabricante.

A V14 usa **0,050 s como limite máximo**, não como valor exato.

Regra segura aplicada quando o Sepam é jusante:

- se `t_down ≤ 0,050 s`, então `Δt = t_up - t_down ≥ t_up - 0,050 s`;
- se esse limite inferior atende à margem de 0,300 s, o par está temporalmente coordenado mesmo no pior caso dentro do limite de catálogo.

Resultados com os ajustes preliminares atuais:

| Par | Resultado V14 |
|---|---:|
| CB27 → T2 | Δt ≥ 0,822 s |
| T2 → T1 | Δt = 3,852 s |
| T1 → CB1 | Δt = 3,854 s |
| CB2 → T1 | Δt ≥ 0,594 s |
| CB8 → CB1 | Δt ≥ 0,737 s |

Todos superam a margem preliminar de 0,300 s. Isso aprova **somente o critério temporal desses pares**.

## 3. Cabos Cu/XLPE

O próprio modelo físico identifica todos os cabos do Caso 01 como condutor de cobre e isolação XLPE. Para o estudo adiabático, a V14 usa a hipótese padrão:

- `k = 143 A√s/mm²`;
- `θi = 90 °C`;
- `θf = 250 °C`.

Assim, a curva `t=(k·n·S/I)²` pode ser desenhada sem exigir uma entrada que já é dedutível do material/isolação cadastrados.

Esse passo **não aprova a ampacidade** e **não aprova sozinho a proteção térmica**, porque o tempo de abertura do disjuntor ainda é necessário para o tempo total de eliminação.

## 4. O que permanece dependente de ETAP/datasheet

- Icu/Ics dos disjuntores;
- tempo de abertura/clearing dos disjuntores;
- tempos de aceleração dos motores;
- limites térmicos/stall dos motores;
- ampacidade nas condições reais de instalação;
- disjuntores físicos associados a T1/T2, caso existam.

Esses dados são ausentes, não falhas do cálculo. A V14 os mantém separados dos resultados inferíveis.

## 5. Testes

A suíte automatizada da V14 inclui testes específicos para:

- defaults Cu/XLPE;
- limite máximo de catálogo do Sepam;
- aprovação conservadora com relé jusante limitado por catálogo;
- ausência de pendência `I²t sem k` no coordenograma geral.
