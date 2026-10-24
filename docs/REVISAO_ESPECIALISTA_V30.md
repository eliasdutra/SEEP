# Revisão do módulo especialista do SEEP contra a especificação

Comparação item a item entre o documento *Módulo Especialista de Proteção —
Especificação de dados, regras, restrições e rotina de coordenação 50/51* e o
que está implementado hoje em `core/protection.py`, `core/criteria.py` e
`core/data.py`.

Legenda: **atende** · **parcial** · **não atende**.

---

## Veredito

O SEEP já tem as quatro camadas da especificação e implementa o núcleo de
coordenação 50/51 com mais rigor do que o exemplo numérico do documento — ele
verifica a falta máxima **e** a mínima em cada par, soma o tempo do disjuntor,
funde relés que comandam o mesmo disjuntor num estágio só e trata dado ausente
como "não avaliável" em vez de inventar valor.

O que falta é de outra natureza. A especificação pede um módulo que **procura**
um ajuste dentro de um espaço discreto e o rejeita quando viola restrição
(seções 6, 7 e 10). O SEEP hoje **calcula um valor por regra** e depois
**verifica** o ajuste que está lá. São coisas diferentes: o atual responde
"este ajuste passa ou não"; o especificado responde "existe algum ajuste que
passa, e se não existe, qual restrição impede".

Três lacunas são de engenharia, não de esforço, e valem mais que o resto:
a busca de ajustes, a acumulação de carga a jusante e os critérios que hoje
são constantes no código.

---

## 1. Escopo (seção 2 da especificação)

| # | Requisito | Status | Onde está / o que falta |
|---|---|---|---|
| 1 | Identificar automaticamente a cadeia de proteção | **parcial** | `_coordination_pairs` deriva os pares a partir da lista de zonas, mas a cadeia em si é cadastrada à mão em `_COORDINATION_PATHS` (`core/data.py`). Não há descoberta de topologia a partir de barras e trechos. |
| 2 | Calcular a corrente de carga vista por cada relé | **não atende** | `_protected_fla` (linha 122) devolve a FLA do **equipamento protegido**, não a soma das cargas a jusante. Ver seção 3 abaixo. |
| 3 | Selecionar pickup e TMS dentro das faixas reais do relé | **parcial** | `_relay_validation` confere faixa; `suggest_phase_settings` faz *clamp* do TMS na faixa. O **passo** de ajuste não é respeitado — a sugestão é um número contínuo arredondado, não um valor da lista do relé. |
| 4 | Coordenar as funções 51 de jusante para montante | **atende** | `review_coordination` roda casos em cascata (caso 1 = 2 relés, caso 2 = 3, …), e `_check_cti` avalia cada par. |
| 5 | Definir e verificar a função 50 conforme critério de alcance | **parcial** | Existe sugestão (`R50-PICKUP`) e verificação contra a partida assimétrica (`_check_asym_start`). Mas o critério do SEEP é 1,25 × Icc MAX da barra de jusante, fixo no código; a especificação usa ~1,1 × Icc remoto e exige que o critério seja **parametrizável**. |
| 6 | Verificar partida de motor e energização de transformador | **atende** | `_check_start_floor`, `_check_asym_start` e `_check_inrush_floor`. |
| 7 | Comparar com curvas de dano de motor e transformador | **parcial** | Motor: `_check_damage_ceiling` (aceita/rejeita). Transformador: a curva existe e é desenhada (`_transformer_damage_traces`), mas **não há verificação de aceitação**. |
| 8 | Comparar com a suportabilidade térmica do cabo | **não atende** | A curva I²t é calculada e desenhada (`_cable_damage_trace`), e `analyze_zone` avisa quando falta o `k`. Mas nenhuma verificação reprova um ajuste por cabo. |
| 9 | Considerar o tempo total de eliminação, incluindo o disjuntor | **parcial** | `_check_cti` soma `breaker_opening_time_s` ao tempo do relé de jusante. `_check_damage_ceiling` **não soma** — compara o tempo do relé com o dano. `evaluate_coordination_pair` **também não soma** (linha 1554), o que a deixa inconsistente com `_check_cti`. |
| 10 | Executar as verificações em todos os cenários | **parcial** | `_check_cti` roda MAX e MIN. Os cenários **operativos** (GE2 ligado/desligado, motores ligados/desligados) já existem no modelo desde a V30, mas o especialista não os varre — ele avalia a configuração que está salva. |
| 11 | Explicar por que um ajuste foi aceito ou rejeitado | **atende** | É o ponto mais forte. Cada verificação devolve o número, a corrente em que ocorre o pior caso e a margem exigida. |
| 12 | Não forçar solução; declarar inexistência e indicar o conflito | **parcial** | `_case_status` devolve *approved / rejected / pending* e a lista de verificações reprovadas. Mas não existe a frase "não há solução com os ajustes disponíveis", porque não existe busca — só se verifica um ajuste por vez. |

---

## 2. Restrições da seção 6

| Restrição | Verificação no SEEP | Status |
|---|---|---|
| Carga normal | Faixa do relé em `_relay_validation`; pickup sugerido = fator × FLA | **parcial** — não há reprovação por pickup abaixo da carga |
| Partida de motor | `_check_start_floor` + `_check_asym_start` | **atende** |
| Inrush de transformador | `_check_inrush_floor` | **atende** |
| Curto mínimo (sensibilidade) | `analyze_zone`: Icc MIN / pickup ≥ 1,5 | **atende** |
| Coordenação 51 | `_check_cti`, falta MAX e MIN | **atende** |
| Função 50 | `_check_asym_start` (só contra partida) | **parcial** — falta a verificação de alcance/sobrealcance |
| Dano do motor | `_check_damage_ceiling` | **atende** |
| Dano do transformador | — | **não atende** |
| Cabo (I²t) | — | **não atende** |
| Disjuntor | `breaker_duty_for_zone`: capacidade de interrupção | **parcial** — verifica Icu/Ics, não o tempo total de eliminação como restrição |

Sete das dez restrições da matriz já reprovam de fato. As três que faltam —
dano do transformador, cabo e tempo total — são do mesmo formato das que já
existem: recebem a curva, varrem os pontos, guardam a menor folga.

---

## 3. A acumulação de carga (seção 4.2)

A especificação é explícita: *"em sistema radial, a rotina deve acumular
automaticamente as cargas a jusante de cada relé. Isso evita que o usuário
tenha de informar manualmente a corrente vista por cada proteção."*

Hoje `_protected_fla` devolve a corrente nominal do equipamento que a zona
protege. Enquanto cada zona protegia exatamente um motor ou um transformador,
os dois números coincidiam e a diferença não aparecia.

Com os motores novos da V30 isso deixou de valer. A `Barra5` tem agora três
ramais de 6,6 kV, e o `Relé12` protege a barra inteira: a corrente que ele
enxerga em operação normal é a soma dos motores em serviço, não a FLA do T1.
Com M-B-1 e M-B-2 ligados, a soma passa de 463 A contra os 962 A de FLA do T1 —
ainda folgado, mas o número certo é a soma, e o critério de pickup deveria
partir dela.

A informação para calcular já existe: `_graph_downstream_motor_names`
(`core/solver.py`, linha 762) percorre o grafo e devolve os motores a jusante
de um disjuntor. Falta somar as correntes e usar isso em `_protected_fla`.

---

## 4. Critérios que hoje são constantes no código (seção 4.10)

A especificação diz: *"todos os critérios devem ser dados de entrada ou
parâmetros de configuração. Eles não devem ficar escondidos no código como
constantes sem identificação."*

Levantamento do que está fixo:

| Constante | Valor | Onde | O que decide |
|---|---|---|---|
| fator de pickup 51 | 1,15 / 1,25 / 1,10 | `protection.py` 1292-1298 | margem sobre a FLA, por tipo de equipamento |
| fator do pickup 50 | 1,25 | `protection.py` 1411 | seletividade com a falta MAX de jusante |
| fator de partida no 50 | 1,7 | `protection.py` 1421 | folga sobre a LRC assimétrica |
| `CTI_DEFAULT_S` | 0,30 s | `protection.py` 1254 | margem de coordenação (já sobrescritível por zona) |
| `BAND_MARGIN_S` | 0,30 s | `protection.py` 2598 | folga mínima sobre a partida do motor |
| `ASYM_LRC_FACTOR` | 1,6 | `protection.py` 2599 | assimetria da corrente de partida (sobrescritível por motor) |
| limite de sensibilidade | 1,5 | `protection.py` 1125 | Icc MIN / pickup |
| margem do disjuntor | 1,10 | `breaker_duty_for_zone` | Icc exigido de projeto |

Dois deles (`CTI_DEFAULT_S` e `ASYM_LRC_FACTOR`) já aceitam sobrescrita por
zona/equipamento, que é meio caminho. Os outros seis não.

O caminho natural: uma entrada `criteria` no modelo, exposta no schema de
edição como as outras categorias, lida por estas funções com `.get(chave,
padrão)`. O padrão continua sendo o valor de hoje, então nada muda de
resultado — muda só quem manda no número.

---

## 5. A busca de ajustes (seção 7)

É a lacuna estrutural. A especificação pede:

1. representar cada ajuste como conjunto discreto (curvas, tapes, TMS, pickup da 50);
2. gerar as combinações fisicamente possíveis;
3. eliminar as que violam carga normal ou faixa;
4. verificar partida/inrush, sensibilidade, coordenação 51, alcance da 50, curvas de dano e cabo;
5. registrar as combinações válidas ou diagnosticar a inexistência.

O SEEP tem as peças: `CURVES` (6 famílias), `RELAY_LIBRARY` com faixa por
curva, `PICKUP_STANDARDS`, `CT_STANDARDS` e `INST_STANDARDS` (listas discretas,
linhas 83-85), `_next_standard` para subir ao valor comercial seguinte, e todas
as verificações já devolvendo *ok/bad/warn*. O que não existe é o laço que
combina e filtra — hoje as listas discretas só arredondam um valor calculado.

Um protótipo honesto seria: para uma zona, varrer curva × tape × TMS dentro das
faixas do relé, rodar as verificações que já existem em cada combinação, e
devolver as que passam em todos os cenários, ordenadas pela folga mínima. Com
6 curvas × ~40 tapes × ~30 TMS são ~7000 combinações por zona — trivial para o
tempo de cálculo das verificações, desde que o curto-circuito venha do cache.

---

## 6. Dados de entrada (seção 4)

| Bloco | Situação |
|---|---|
| 4.1 Topologia | **atende** — barras, trechos (cabos), relé por trecho, sentido pelo caminho |
| 4.2 Correntes de carga | **parcial** — ver seção 3 |
| 4.3 Curto-circuito | **atende, com folga** — MAX e MIN, 3F/LL/LG/LLG, cenários de geração e equipamentos fora de serviço |
| 4.4 TCs | **parcial** — relação e secundário sim; classe de exatidão, carga nominal e saturação não |
| 4.5 Relé | **parcial** — fabricante, modelo, famílias e faixas sim; **passos** de ajuste e tolerâncias não |
| 4.6 Motor | **atende** — falta só a curva de dano **frio** (desmarcada no ETAP do caso) |
| 4.7 Transformador | **parcial** — Sn, tensões, Z%, inrush sim; o inrush é um **ponto**, não um envelope; a curva de dano é calculada por C57.109, não fornecida |
| 4.8 Cabo | **atende** nos dados (material, seção, isolação, temperaturas, k, K²S²); falta a verificação |
| 4.9 Disjuntor | **parcial** — tempo de abertura sim; tempo de interrupção/extinção não |
| 4.10 Critérios | **parcial** — ver seção 4 |

---

## 7. O que fechar primeiro

Ordenado por (valor para a especificação) ÷ (esforço):

1. **Verificação do cabo e do dano do transformador.** Mesma forma das
   verificações que já existem; as curvas já são calculadas. Fecha dois itens
   da matriz de restrições de uma vez.
2. **Tempo total de eliminação nas comparações com dano.** Somar
   `breaker_opening_time_s` em `_check_damage_ceiling`, e alinhar
   `evaluate_coordination_pair` com `_check_cti` — hoje as duas discordam.
3. **Critérios como dado editável.** Mecânico, sem risco de mudar resultado, e
   é uma exigência literal da especificação.
4. **Acumulação de carga a jusante.** O grafo já existe em `solver.py`; falta
   somar e trocar a fonte do `_protected_fla`.
5. **Passo de ajuste do relé.** Acrescentar `tap_step` / lista de TMS à
   `RELAY_LIBRARY` e fazer a sugestão cair num valor realizável.
6. **Busca de ajustes.** O item maior. Só vale depois dos anteriores, porque a
   busca reusa exatamente as verificações e os critérios acima.
7. **Varredura de cenários operativos.** Rodar o conjunto de verificações para
   cada combinação de fontes/cargas em serviço. Fica barato depois do item 6,
   porque é o mesmo laço uma camada acima.

---

## 8. Onde o SEEP já vai além da especificação

Vale registrar, porque num parecer só de lacunas isso se perde:

- **Falta máxima e mínima em cada par.** O exemplo do documento coordena num
  ponto; `_check_cti` reprova se qualquer um dos dois extremos falhar.
- **Casos em cascata.** `review_coordination` mostra em que profundidade da
  cadeia a coordenação quebra, em vez de um veredito único.
- **Estágios fundidos.** Relés que comandam o mesmo disjuntor viram um estágio
  só — entre eles não há seletividade a cobrar.
- **Dado ausente ≠ reprovação.** O status *pending* separa "reprovou" de "não
  dá para avaliar", que é exatamente o que a matriz de aceitação da seção 10
  pede na coluna "não avaliável".
- **Aprovação conservadora por limite de catálogo.** Quando o tempo exato do
  instantâneo não é conhecido, `evaluate_coordination_pair` usa o limite máximo
  do fabricante — e só aceita isso quando o limite está do lado que torna a
  conclusão segura.
- **Limite de 20 × Is da IEC 60255-151** no cálculo da curva inversa.
- **Capacidade de interrupção** calculada com a falta imediatamente a jusante
  do disjuntor, removendo as fontes do lado da carga.

---

*Base: SEEP build 29.13 · `core/protection.py` (2 914 linhas), `core/criteria.py`,
`core/data.py`. Números de linha referem-se a essa versão.*
