# SEEP — Simulador Elétrico de Estudos de Proteção

Simulador elétrico em código aberto para estudos de proteção de sobrecorrente.

> **Licença:** o rótulo "código aberto" ainda não tem uma licença formal (`LICENSE`)
> nem repositório público associado — isso ainda está pendente de decisão (MIT,
> GPL-3.0 ou Apache-2.0) antes de valer como open source de fato, importante para
> uso acadêmico/citação.

> **V30 — renumeração das barras e segundo gerador.**
> As barras passaram a ter numeração sequencial de 1 a 6. O nome usado na
> exportação do ETAP continua registrado no campo `etap_name` de cada barra,
> para não se perder a rastreabilidade com o `Dados.xlsx` e com as folhas Star:
>
> | agora | ETAP | papel |
> |---|---|---|
> | `Barra1` | `Bus01` | terminal do gerador GE1 |
> | `Barra2` | — | terminal do gerador GE2 (novo) |
> | `Barra3` | `Barra1` | barra principal 13,8 kV |
> | `Barra4` | `Bus10` | terminal M-B-6 |
> | `Barra5` | `Barra2` | barra principal 6,6 kV |
> | `Barra6` | `Barra4` | terminal M-B-0 |
>
> O gerador passou a se chamar **GE1** e ganhou um par, o **GE2**: mesma máquina
> (41,25 MVA), com barra de terminal, cabo (`Cabo3`), TC, disjuntor `DJ5` e
> relé `Relé2` próprios. Cada gerador tem agora o campo `in_service`, editável
> na tela **Modelo físico** — desligar um deles tira a contribuição dele do
> curto-circuito, que é o efeito a ser demonstrado em aula. Com os dois fora de
> serviço o estudo é recusado com mensagem explícita, porque o sistema ficaria
> sem fonte e sem barra de referência.
>
> Os ajustes do `Relé2` foram copiados do `Relé1` e **precisam ser
> reavaliados**: não há folha ETAP para essa máquina, e a coordenação muda
> conforme os dois geradores estejam ou não em serviço.
>
> **Solver de sequência generalizado.** Os dois solvers próprios do projeto —
> o de faltas à terra (`run_ground_sequence_fallback`) e o de fase MIN
> (`_radial_phase_min_sequence`) — montavam a rede caminhando a árvore a partir
> de uma única fonte e recusavam qualquer outro caso
> (*"requer exatamente uma fonte síncrona"*). Com dois geradores alimentando a
> mesma barra isso deixa de valer: a árvore fecha um laço.
>
> Agora as impedâncias de sequência saem da **matriz nodal** (`Zbus`), montada
> em pu sobre base comum e invertida; a impedância de Thévenin de cada barra é a
> diagonal. É o método geral, aceita fontes em paralelo e qualquer topologia.
> Para uma rede radial de uma fonte o resultado é o mesmo circuito, e foi
> conferido: com apenas o GE1 em serviço, os valores batem com os da V29 com
> desvio máximo de **1,3 × 10⁻¹⁰ %** — ou seja, ruído de ponto flutuante. A
> verificação contra o ETAP não muda.
>
> Efeito medido do segundo gerador, na Barra3 (13,8 kV): a corrente de curto 3F
> mínima passa de **11,44 kA** com um gerador para **22,89 kA** com os dois —
> exatamente o dobro, como se espera de duas máquinas iguais em paralelo. Na
> Barra5 (6,6 kV) o aumento é bem menor, de 8,00 kA para 9,61 kA, porque ali quem
> domina a impedância é o próprio T1. Esse contraste é conteúdo de aula.
>
> **Nomes em português.** Os identificadores de equipamento deixaram de misturar
> inglês e português: `Bus` → `Barra`, `Cable` → `Cabo`, `Relay` → `Relé`,
> `CB` → `DJ` (disjuntor) e `CT-` → `TC-` (transformador de corrente). Como com
> as barras, o nome da exportação do ETAP fica registrado ao lado — `etap_name`
> nos cabos e `relay_etap_name` nas zonas de relé — para que a correspondência
> com o `Dados.xlsx` e com as folhas Star continue explícita. As chaves internas
> dos dicionários (`from_bus`, `hv_bus`, `bus`) seguem em inglês de propósito:
> são estrutura de código, não rótulo de tela.
>
> **Nota do estudo montada na hora.** O texto que acompanha a tela de
> curto-circuito era fixo e trazia uma ressalva escrita à mão citando barras
> pelo nome. Texto fixo envelhece: quando o cálculo melhora a ressalva continua
> assustando quem lê, e quando outra barra passa a falhar ninguém fica sabendo.
> Agora `_nota_do_estudo()` monta a frase a partir das linhas calculadas. A nota
> diz o que foi calculado, não como — método é assunto do README e dos
> comentários, a tela mostra resultado. A única coisa que ela acrescenta é um
> aviso quando alguma barra fica sem valor utilizável, e mesmo esse aviso sai
> das linhas calculadas, nunca escrito à mão.
>
> Os changelogs anteriores (V10 a V29) mantêm os nomes antigos de propósito:
> descrevem versões em que as barras se chamavam assim.


> **V29**: os parâmetros de maior impacto elétrico de gerador, transformador, cabo e
> motor passaram a ser editáveis na tela **Modelo físico** (potência, tensão,
> impedâncias de sequência, grupo vetorial, %R/%X/LRC do motor etc.). Salvar um
> equipamento recalcula o estudo elétrico inteiro automaticamente (mesmo processo
> do botão "Recalcular sistema"); "Restaurar ETAP" volta ao dado original a
> qualquer momento. O programa também foi renomeado de "Protection Studio" para
> **SEEP**, por não ser um SCADA — não monitora nem controla um sistema em tempo
> real, é um simulador de estudos offline. Ver
> [`docs/CHANGELOG_V29.md`](docs/CHANGELOG_V29.md).

> **V28.1**: revisão de consistência (identidade do programa, documentação e um erro
> latente de referência de tensão), remoção de quatro scripts de validação que
> apontavam para o modelo anterior, e o interruptor `CACHE_ENABLED` em `core/solver.py`.
> Ver [`docs/CHANGELOG_V28_1.md`](docs/CHANGELOG_V28_1.md).

> **V28**: os quatro coordenogramas passaram a ser desenhados no padrão do
> ETAP Star (folha branca, escalas duplicadas, rótulos com seta, unifilar
> embutido e carimbo), e a curva do relé ganhou o patamar de 20 × Is da
> IEC 60255-151, que faltava. Detalhes e verificação em
> [`docs/CHANGELOG_V28.md`](docs/CHANGELOG_V28.md); para conferir contra o seu
> Star75: `python -m validation.validate_v28_etap_star75`.


A V27 mantém todas as correções elétricas da V26 (LG/LLG, curvas de cabo, curvas térmicas dos motores e quatro coordenogramas) e muda a forma como o Pandapower é executado para reduzir a espera durante o ajuste de proteção.

## Cadeia do estudo

**Modelo físico → Fluxo de potência → Curto-circuito IEC 60909 → Ajustes 50/51 → Coordenogramas**

Nenhuma etapa elétrica foi removida.

## O que ficou mais rápido

### Cache elétrico em memória

`run_power_flow()` agora possui cache, assim como os estudos de curto-circuito e as faltas remotas já possuíam.

Depois do primeiro cálculo:
- abrir Fluxo reutiliza o resultado;
- abrir Curto MAX/MIN reutiliza o resultado;
- trocar entre os quatro coordenogramas reutiliza os resultados elétricos;
- alterar pickup, TMS, TC, 50P ou delay **não executa Pandapower novamente**.

### Recalcular sistema

O botão **Recalcular sistema** é a única ação do front que invalida voluntariamente o cache elétrico. Ele deve ser usado quando o modelo elétrico/topologia precisar ser refeito.

Ao executar, a V27 calcula uma vez:
- fluxo de potência;
- curto MAX;
- curto MIN;
- e pré-aquece as faltas remotas dos ramais de motor usadas nos TCCs.

### Salvar proteção

Salvar um ajuste grava apenas os parâmetros do relé. O endpoint não monta um TCC desnecessário e não limpa o cache do Pandapower.

## Quatro coordenogramas

1. M-B-0 · 6,6 kV
2. M-B-6 · 13,8 kV
3. T1 · 13,8/6,6 kV
4. Geral · 13,8 kV

As escalas ETAP e os elementos físicos das versões anteriores foram preservados.

## Execução no Windows

1. `setup_windows.bat`
2. `run_windows.bat`
3. Use **Recalcular sistema** apenas quando quiser refazer o estudo elétrico.
4. Durante ajustes 50/51, apenas salve e abra o TCC; os resultados elétricos permanecem cacheados.

## Limitações conhecidas

- **Escopo do modelo**: caso reduzido (5 barras, 1 gerador, 1 trafo, 2 motores), não a FPSO completa. Cobre fluxo de potência e curto-circuito IEC 60909 — não faz harmônicos, estabilidade transitória nem *arc flash*.
- **Proteção só de fase (50/51)**: neutro/terra (51N/50N) existe na estrutura de dados mas está desabilitado em todas as zonas.
- **Um único modelo de relé em uso** (MiCOM P241) — o SEPAM M40 está na biblioteca mas nunca é atribuído a um relé real.
- **Curva de partida do motor**: aproximação com 2 pontos reais (FLA, corrente de rotor bloqueado) interpolados por uma forma estilizada, não uma simulação dinâmica completa.
- **Sistema especialista**: as margens de projeto (1,15×/1,25×/1,10× FLA, CTI de 0,30s) são práticas comuns de engenharia de proteção, não uma citação direta de uma norma específica — critério de engenheiro sênior pode divergir.
- **Curto-circuito fase-terra (LG) — bug conhecido, não resolvido**: nas barras do lado de 13,8 kV ligadas diretamente ao gerador (Barra1, Barra3, Barra4), o LG retorna 0,000 kA mesmo com o cálculo físico de reserva implementado para cobrir exatamente esse caso. Duas hipóteses foram testadas e descartadas (checagem de zero flutuante, coordenação entre `Zs`/`Zt`); a causa raiz não foi confirmada por falta de acesso ao dado bruto do Pandapower em tempo real. Tratar os valores de LG nessas 3 barras como não confiáveis até investigação futura — 3F, LL e LLG não são afetados.
- **Sem licença open source formalizada** ainda (ver aviso no topo deste README).

