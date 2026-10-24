# V28 — coordenograma no padrão ETAP Star

Base de comparação: `00123.pdf` — ETAP Star 24.0.3C, folha **Star75**, Bus2,
Nom. kV = 6,6 / Plot Ref. kV = 6,6, Fault: Phase, 08-31-2026.

As curvas vetoriais desse PDF foram extraídas e convertidas para (A, s). A
calibração log-log dos eixos foi ancorada em dois valores já conhecidos do
modelo — pickup 51 do Relay11 (230 A) e pickup 50 (7760 A) — e reproduz ambos
com erro < 0,15 %, o que valida a leitura das demais curvas.

## 1. Correção elétrica: limite de 20 × Is na curva inversa

`relay_time()` agora limita o múltiplo `M = I/Is` em **20** (`CURVE_MULTIPLE_LIMIT`).

A IEC 60255-151 e a IEEE C37.112 definem a característica inversa apenas até
20 × Is. Acima disso o ETAP — e os relés usuais — congelam o tempo no valor de
20 × Is até o estágio 50 assumir.

No caso M-B-0 isso aparece diretamente no Star75: a curva do Relay11 fica
**constante em 0,0653 s de 4600 A até o 50P em 7760 A**, que é exatamente
`t(M=20) = 0,325 × 80 / (20² − 1) = 0,0652 s`.

Sem esse patamar a V27 desenhava 0,0229 s em 7760 A — **2,8 × mais rápido que o
relé real** na faixa de curto. O erro era conservador no sentido errado: a
margem de seletividade contra o Relay12/Relay10 aparecia maior do que é.

O cálculo didático (`Cálculo 51`) mostra o múltiplo limitado e a norma aplicada.

## 2. Curva de partida do motor (`M-B-0-100%`)

`_motor_start_envelope()` foi reescrita para reproduzir a geometria do Star a
partir de FLA, LRC e tempo de aceleração a 100 % Vt:

| trecho | antes (V27) | agora (V28) | Star75 |
|---|---|---|---|
| vertical de carga | 1,15 × FLA = 177,6 A | **FLA = 154,4 A** | 154,4 A |
| patamar | `ta` | `ta` | 1,00 s |
| fim do patamar | 0,78 × LRC | 0,7555 × LRC = 758,2 A | 758,2 A |
| vertical de rotor bloqueado | LRC | LRC = 1003,6 A | 1003,5 A |
| cauda assimétrica | 0,05 s / 0,01 s genéricos | 1,60 × LRC em 0,01 s | 1605,2 A |

## 3. Elementos que faltavam na folha

- **Ampacidade do cabo** — `Cable2` recebeu `ampacity_total_a = 81,3 A`, lida da
  marca *Cable2 Ampacity* do Star75. `Cable1` e `Cable8` continuam sem valor:
  o campo é editável na tela de Ajustes 50/51 e a marca aparece assim que for
  preenchido.
- **Marca de pickup 51** no topo da folha, por relé.
- **Correntes de falta como seta curta na base**, com ponta e rótulo curto
  (`Relay11 - 3P`, `Relay11 - LL`), no lugar da reta tracejada de altura total.
  O Star75 mostra a seta 3P em 10,32 kA; o valor plotado aqui continua sendo o
  calculado pelo estudo, não o copiado do ETAP.
- **Fim da curva do relé**: a característica efetiva agora termina onde encosta
  no piso de 0,01 s. Antes o traço seguia rente à base até a corrente máxima de
  amostragem, desenhando uma linha que não existe no ETAP.

## 4. Apresentação

- Folha branca com moldura fechada, ticks internos maiores e menores (`D1`),
  sem grade interna — igual ao Star75. Grade interna disponível como opção.
- Escala de corrente e de tempo duplicada: `Amps X n` em cima e embaixo,
  `Seconds` à esquerda e à direita. O rótulo `500` do eixo de corrente, que
  faltava, foi incluído.
- **Sem legenda**: cada curva recebe rótulo com seta, como no Star. Os textos
  são distribuídos nas bordas e não invadem o unifilar.
- Cores por elemento no padrão ETAP: relé azul-marinho (demais relés em
  magenta/ocre/teal), capacidade do motor em vermelho, partida do motor em
  preto, cabo em marrom, transformador em verde.
- **Unifilar embutido** no canto inferior esquerdo (barra, disjuntor, TC/relé,
  cabo, motor, transformador), como o Star desenha.
- **Carimbo de rodapé** com Project / Location / Contract / Engineer /
  Filename à esquerda, número da folha ao centro e Date / SN / Rev / Fault à
  direita.
- Alternância folha branca ↔ tema escuro, e **Exportar PNG**.

## 5. Verificação

`python -m validation.validate_v28_etap_star75`

Compara ponto a ponto o coordenograma M-B-0 gerado pela aplicação com as curvas
extraídas do Star75:

```
Relay11 - P OC1 (tempo)     desvio máx   0.40 %  (tol 2 %)  OK
Relay11 - pickups 51/50     desvio máx   0.01 %  (tol 2 %)  OK
M-B-0-100% (partida)        desvio máx   0.31 %  (tol 1 %)  OK
M-B-0 (capacidade térmica)  desvio máx   0.29 %  (tol 1 %)  OK
Cable2 - P (dano)           desvio máx   0.61 %  (tol 1 %)  OK
Cable2 Ampacity             desvio máx   0.00 %  (tol 1 %)  OK
```

A tolerância de 2 % no tempo do relé existe porque as curvas do PDF são
bézier: os nós lidos não caem exatamente sobre a característica.

## 6. Em aberto

- A seta `3P` só aparece com o Pandapower instalado (é o estudo que fornece a
  corrente). O valor do Star75 no ponto do Relay11 é 10,32 kA — comparar com o
  calculado após `Recalcular sistema`.
- `T1 Withstand` continua estimada: os pontos ETAP de suportabilidade do
  transformador ainda não foram exportados.
- Ampacidade de `Cable1` e `Cable8` ainda não informada.
