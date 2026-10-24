# CHANGELOG V29

## Renomeação

O programa passa de "Protection Studio" para **SEPE — Simulador de Estudos de
Proteção Elétrica**. Motivo: não é um SCADA (não monitora nem controla um
sistema elétrico real em tempo real); é um simulador de estudos offline
(fluxo de potência, curto-circuito IEC 60909 e coordenação de proteção).

## Equipamentos editáveis (parâmetros de alto impacto elétrico)

Antes, todo o modelo físico (`core/data.py`) era fixo no código-fonte. A tela
**Modelo físico** agora permite editar, por equipamento, os parâmetros que
efetivamente entram no Pandapower e no cálculo de curto-circuito:

- **Gerador**: `sn_mva`, `kv`, `pf`, `efficiency_percent`, `xdss_pu`, `x_over_r`,
  `x0_pu`, `x0_over_r0`, `x2_pu`, `x2_over_r2`, `neutral_current_a`.
- **Transformador**: `sn_mva`, `vn_hv_kv`, `vn_lv_kv`, `vk_percent`, `x_over_r`,
  `vk0_percent`, `x0_over_r0`, `vector_group`, `shift_degree`, `hv_connection`,
  `lv_connection`, `lv_grounding`.
- **Cabo**: seção, comprimento, paralelos, impedâncias de operação e de curto
  (20 °C) e `k_adiabatic`.
- **Motor**: `kw`, `kv`, `pf`, `efficiency_percent`, `r_percent`, `x_percent`,
  `rx`, `x0_percent`, `x2_percent`, `lrc_percent`.

Campos puramente informativos (rpm, polos, temp_rise_c etc.) e pontos de curva
(inrush, damage_points_pu do trafo, thermal_points do motor) ficaram de fora
desta etapa — não entram em nenhum cálculo hoje, ou exigem um editor de tabela
em vez de um campo único.

### Como funciona

- `core/data.py`: `EQUIPMENT_FIELD_SCHEMA` descreve cada campo editável
  (rótulo, unidade, tipo, faixa válida) e é a fonte única usada tanto pela
  validação do backend quanto pelo formulário do front-end
  (`GET /api/equipment-schema`). `validate_equipment_payload()` rejeita
  campos fora da lista e valores fora de faixa.
- `core/storage.py`: nova tabela `equipment_overrides` (categoria + nome →
  payload). `get_model()` aplica os overrides sobre o `default_model()` de
  fábrica em memória — o dado original nunca é sobrescrito em disco, então
  "Restaurar ETAP" sempre volta ao caso de referência.
- `app.py`: `GET/POST /api/equipment/<categoria>/<nome>` e
  `POST /api/equipment/<categoria>/<nome>/reset`. Salvar ou restaurar um
  equipamento invalida o cache elétrico e dispara o mesmo recálculo do botão
  "Recalcular sistema" (fluxo + curto MAX/MIN + pré-aquecimento das faltas
  remotas de motor), já que mudar potência/impedância de um equipamento muda
  o resultado de curto-circuito e, por consequência, a coordenação de
  proteção — diferente de mudar um ajuste 50/51, que não recalcula
  Pandapower.

### O que continua fora do escopo

- Barras e topologia (`switchgear`) continuam somente leitura: editar isso
  exigiria remontar o unifilar e recalcular referências cruzadas (caminhos de
  coordenação, zonas de relé), o que é um projeto à parte.
- Carregamento variável do fluxo de potência (`study_loading_percent` como
  slider interativo) segue como próximo passo separado, já discutido mas
  ainda não implementado nesta versão.

## V29.4 — símbolo do gerador, texto do curto e largura da folha TCC

### Unifilar: gerador deixou de ser igual ao motor

Gerador e motor eram o mesmo círculo branco, sem nada dentro, então não dava
para saber qual era qual olhando o desenho. O gerador passou a ter o "Y" do
enrolamento em estrela (três raios a 120°), que é o mesmo símbolo que o ETAP
usa para a máquina síncrona na folha de referência do caso; o motor continua
sendo o círculo liso, também como no ETAP. O gerador também foi renomeado de
`GE-TG-5147001A` para `GE` em `core/data.py` (no cadastro e na zona `Z-R1`),
então o rótulo do unifilar passa a ser `33 MW` / `GE` e a curva de dano do
estator aparece como `GE — dano do estator` no coordenograma geral. Não havia
override de equipamento salvo no banco apontando para o nome antigo.

- `static/app.js`: função `generatorSvg()` desenha círculo + raios; o clique
  agora é no grupo inteiro, então continua abrindo o painel do gerador.
- `static/styles.css`: classes `.sld-generator` e `.sld-generator-wye`,
  incluindo o realce laranja de seleção.

### Curto-circuito: notas MAX e MIN reescritas

Os dois textos foram reescritos em linguagem direta. O conteúdo técnico é o
mesmo: método de cada falta, de onde sai cada valor e a ressalva do LG zerado
em Bus01, Bus1 e Bus10. Saiu o rótulo "LIMITAÇÃO CONHECIDA" em caixa alta e o
parágrafo sobre o que faltou para diagnosticar. (`core/solver.py`)

### Coordenograma: folha mais estreita, como no ETAP Star

O gráfico esticava até o fim do card e as curvas ficavam achatadas na
horizontal. Agora a linha gráfico + unifilar tem largura máxima de 720 px e
altura de 620 px, proporção próxima da janela do Star; o card acompanha. Vale
para as quatro vistas (M-B-0, M-B-6, T1 e Geral). O PNG exportado saiu de
1400x1000 para 1000x1080, para bater com o que aparece na tela.
(`static/styles.css`, `static/app.js`)

### Nome por extenso alinhado com o changelog

A renomeação da V29 dizia **SEPE — Simulador de Estudos de Proteção Elétrica**,
mas a interface, o `<title>` da aba, o carimbo da folha TCC e o README ainda
traziam "Sistema de Estudo de Proteção Elétrica". Todos foram alinhados para
"Simulador de Estudos de Proteção Elétrica", que também fecha a sigla S-E-P-E.
(`templates/index.html`, `core/protection.py`, `README.md`)

### Estágio 50 sem retardo: reta vertical, como no Star

A característica efetiva do relé terminava num patamar horizontal no tempo de
catálogo do instantâneo (50 ms do MiCOM P241) que seguia até o fim da escala —
1.000.000 A na folha de 13,8 kV. Não existe curto nessa faixa e o ETAP não
desenha isso: na folha Star86 do ramal M-B-0 o Relay11 mantém o patamar de
0,0652 s (o limite de 20 × Is) até 7.760 A, que é o pickup do 50P, e ali desce
em reta vertical até o piso da folha, à esquerda inclusive da seta de 3P em
10.326 A.

Agora `relay_effective_trace()` faz o mesmo: quando o estágio 50 não tem
retardo intencional (`stage3_delay_s = 0` e sem `stage3_operating_time_s`), a
amostragem da parte inversa para no pickup e a curva fecha com o segmento
vertical até 0,01 s. Com retardo programado (caso do Relay1, 10 ms) o patamar
horizontal continua valendo, como antes.

Conferido nas quatro vistas: Relay11 desce em 7.760 A, Relay3 em 6.990 A,
Relay12 em 9.800 A, Relay10 em 14.000 A e Relay1 em 14.712 A.

O tempo de 50 ms do catálogo não foi descartado: `relay_operating_time()`
continua devolvendo ele, então a aprovação de pares, a verificação do
disjuntor e o cálculo manual da função 51 seguem usando o valor conservador.
A mudança é só no desenho. (`core/protection.py`)

### Trafo do painel lateral, vista Geral sem unifilar e limpeza de rótulos

- **Símbolo do trafo (painel do TCC).** Eram dois círculos de raio 15 a 18 px
  de distância: eles se invadiam e o condutor de cima terminava dentro do
  círculo, o que deixava o desenho torto. Agora são as duas fileiras de arcos
  do Star (quatro semicírculos por fileira, voltados um para o outro), com o
  fio de cima morrendo na fileira superior e o de baixo saindo da inferior. O
  helper `coil()` já existia no arquivo desde a V29 mas nunca tinha sido usado.
- **Vista Geral sem unifilar.** Ela junta relés de ramais diferentes, então um
  único fio vertical não representava o que está no gráfico. `_view_single_line`
  devolve lista vazia para a vista Geral, o painel some e o gráfico ocupa a
  folha inteira; o interruptor "unifilar ao lado" também é escondido nessa
  vista para não sobrar um controle sem efeito.
- **Rótulos.** Saiu o "V28 ·" do cabeçalho do Coordenograma e o "ETAPA 4 DO
  ESTUDO" da tela de Ajustes 50/51.

(`static/app.js`, `core/protection.py`, `templates/index.html`)

### Identificação do build na barra lateral

Com duas cópias do projeto na mesma máquina as telas são idênticas, e não há
como saber de olho se uma correção já está aplicada ou se a pasta é antiga —
o que custou três idas e voltas achando que correções não tinham entrado.
`BUILD_TAG` em `core/data.py` vai para o rodapé da barra lateral, abaixo de
"IEC 60909 · 60 Hz". Precisa ser atualizado a cada entrega.
(`core/data.py`, `app.py`, `templates/index.html`, `static/styles.css`)

## V29.9 — ajuste 50/51 ao vivo dentro do coordenograma

Editar um ajuste exigia sair para a tela Ajustes 50/51, salvar, e voltar para
ver o efeito na curva. Agora a folha tem, à direita, um painel com os cinco
campos que mexem na curva de fase (curva 51, pickup 51, TMS, pickup 50 e
retardo do 50). A curva redesenha enquanto se digita, com 260 ms de espera
depois da última tecla.

**Nada é gravado na prévia.** O desenho vem de um endpoint novo,
`POST /api/tcc-concise/<vista>/preview`, que recebe `{"overrides": {zona:
ajustes}}` e monta a mesma folha com esses valores. Do lado do servidor a
prévia entra por `preview_zone_settings()`, um contexto por thread lido no
fim de `settings_for_zone()` — depois do `save_settings`, de propósito, para
que a prévia nunca encoste no banco. Sair do contexto já volta tudo ao
ajuste salvo.

`update_settings()` foi partido em dois: `apply_settings_patch()` aplica o
patch numa cópia (mesma lista branca de campos) e o `update_settings()`
continua sendo quem grava. Assim a prévia e o salvar usam exatamente a mesma
regra — o que o gráfico mostra é o que o botão vai gravar.

Detalhes de uso:

- **Salvar** e **Descartar** agem sobre todos os relés em prévia, não só sobre
  o que está no seletor: na vista T1 dá para mexer no Relay11 e no Relay12
  para coordenar os dois, e perder metade do trabalho por causa da posição do
  seletor seria uma pegadinha.
- Trocar de vista mantém a prévia (a folha da outra vista também é montada
  com ela), e o status diz em quais relés há ajuste pendente.
- Campo apagado volta ao valor salvo, em vez de mandar vazio para o servidor.
- O redesenho da digitação não remonta os campos, senão o cursor saltaria a
  cada tecla.

Conferido no navegador: pickup 51 de 230 → 400 A move a curva na hora, o banco
continua com 230 durante a prévia, o foco não sai do campo, descartar volta ao
desenho salvo, salvar grava e redesenha. Na vista T1, mexer no pickup 50 do
Relay12 move só a curva dele (fim em 4.687 → 2.870 A na base de 13,8 kV).
(`core/protection.py`, `app.py`, `static/app.js`, `static/styles.css`,
`templates/index.html`)

### Nome e descrição fechados

Nome: **SEPE — Simulador de Estudos de Proteção Elétrico**.
Descrição: *Simulador elétrico em código aberto para estudos de proteção de
sobrecorrente.*

Aplicados em `<title>`, barra lateral, título e texto do dashboard, carimbo da
folha TCC, README e docstring de `core/data.py`. A descrição substitui a frase
antiga do dashboard, mantendo o resto do parágrafo (Python + Pandapower e a
sequência do estudo). (`templates/index.html`, `core/protection.py`,
`core/data.py`, `README.md`)

Nota de redação, para quem mexer depois: "Elétrico" concorda com *Simulador*,
não com *Proteção* — o nome se lê "Simulador Elétrico ... de Proteção", como
diz a descrição. Foi escolha do autor; não "corrigir" para "Elétrica" sem
combinar.

### Sigla vira SEEP

**SEEP — Simulador Elétrico de Estudos de Proteção**, com a mesma descrição:
*Simulador elétrico em código aberto para estudos de proteção de sobrecorrente.*
Agora "Elétrico" fica ao lado de "Simulador", que é a palavra com que concorda,
e a sigla fecha S-E-E-P.

Trocado em tudo que é visível e nos nomes de empacotamento:

- `<title>`, barra lateral, dashboard, carimbo da folha TCC, README e docstring;
- `CASE_ID` passou de `SEPE-V01` para `SEEP-V01` (aparece no campo SN do carimbo);
- `sepe.spec` virou `seep.spec`, o executável passa a ser `SEEP.exe` e a pasta
  de saída `dist\SEEP\` — o `build_exe.bat` já aponta para o spec novo;
- as mensagens dos `.bat` de setup e build.

Quem já tinha um `SEPE.exe` empacotado precisa rodar `build_exe.bat` de novo;
o exe antigo continua com o nome antigo porque templates e static vão dentro
dele. `SEPAM_M40` na biblioteca de relés não foi tocado (é outra palavra).

## V29.12 — sistema especialista vira verificador de coordenação

O módulo deixou de ser só sugestão de ajuste e passou a responder a pergunta do
engenheiro: **os relés estão coordenados entre si e a curva cabe na banda do
motor?** As curvas de partida, dano do motor e inrush passam a ser tratadas
explicitamente como referência fixa — as paredes da verificação, nunca objeto
de ajuste.

### Casos em cascata

Um caso é um prefixo do caminho de coordenação, do motor para a fonte. Em
`PATH-MB0` (`Z-R11 → Z-R12 → Z-R10 → Z-R1`):

- caso 1: Relay11 + Relay12
- caso 2: + Relay10
- caso 3: + Relay1

Não foi preciso cadastrar topologia nova: os casos são profundidades 2, 3 e 4
do caminho que já existia.

### Estágios: relés que abrem o mesmo disjuntor

O Relay12 não tem disjuntor próprio no modelo — ele abre o CB2, junto com o
Relay10. Entre esses dois não existe seletividade a verificar, então eles são
fundidos num estágio só, cuja envoltória é o menor tempo dos dois em cada
corrente. O CTI é cobrado de estágio para estágio (`_effective_breaker`,
`_case_stages`, `_stage_time`).

### As checagens

- **Seletividade (CTI)** entre estágios consecutivos, avaliada na falta máxima
  e na mínima do barramento protegido pelo estágio de jusante. Reprovar em
  qualquer um dos extremos é reprovação.
- **Piso — partida**: vale para TODOS os relés do caso, porque todos enxergam a
  corrente de partida. Percorre o corpo da envoltória de partida e reporta a
  MENOR folga e a corrente em que ela ocorre.
- **Piso — assimétrica**: o pickup do 50 tem que ficar acima de 1,6 × LRC
  (offset CC da partida).
- **Piso — inrush**: relés do lado de alta do T1 e acima não podem desarmar na
  energização.
- **Teto — dano do motor**: só para a proteção principal e a retaguarda
  imediata; os de montante são isentos e aparecem listados como tal.

A verificação para onde o dado para: a curva de dano exportada termina em
3,6 × FLA (556 A no M-B-0) e a LRC é 1.004 A. O trecho entre os dois não tem
teto conhecido, e o relatório diz isso em vez de extrapolar.

### Banda no coordenograma

`_motor_band_trace()` devolve o polígono entre partida e dano, desenhado como
faixa sombreada atrás das curvas, só onde existe dado dos dois lados. A borda
direita é anotada com "fim do dado de dano" para a faixa não parecer ter
acabado por acaso.

### Resultado no caso de referência

Caso 1 reprovado por dois motivos reais:

- CTI Relay11 → Relay12 na falta mínima: folga de 0,061 s contra 0,30 s
  exigidos (LL em Bus4 = 6,511 kA; ambos os relés no patamar de 20 × Is).
- Relay12 acima do dano do motor em 371 A: 244,6 s contra 150 s.

Conferido forçando TMS 0,10 no Relay11: o piso da partida vira reprovação com
folga de −0,341 s em 936 A, e volta a passar ao restaurar 0,325.

`GET /api/coordination-review/<path_id>`. (`core/protection.py`, `app.py`,
`static/app.js`, `static/styles.css`, `templates/index.html`)
