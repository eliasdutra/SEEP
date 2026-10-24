# V30 — nomes em português, segunda fonte e cargas manobráveis

Esta versão prepara o caso reduzido para a aula: o que antes era um sistema
fixo passa a ter equipamento que o aluno liga e desliga, e o efeito disso
aparece direto no curto-circuito e no coordenograma.

## Nomenclatura

Barras, cabos e relés passaram a nomes em português e em sequência: `Bus01` e
`Bus1` viraram `Barra1` e `Barra3`, `Cable1` virou `Cabo1`, `Relay1` virou
`Relé1`. O nome usado na exportação do ETAP continua registrado em cada item
(`etap_name`, `relay_etap_name`) para não se perder a rastreabilidade com o
`Dados.xlsx` e com as folhas Star — um teste trava esse mapeamento.

## Segundo gerador (GE1 / GE2)

`GE2` é máquina espelhada do `GE1`, na `Barra2`, com ramal próprio
(`Cabo3`, `DJ5`, `Relé2`, `TC-Relé2`). Os dois geradores têm o campo
**Em serviço**, editável em *Modelo físico*.

Medido no caso de referência, com os dois em serviço: 3F mínimo na `Barra3`
sobe de 11,44 kA para 22,89 kA (exatamente o dobro — duas fontes idênticas em
paralelo) e na `Barra5` sobe de 8,00 kA para 9,61 kA (aqui quem manda é a
impedância do T1, não a fonte). É esse contraste que a aula usa.

Desligar todos os geradores é recusado com mensagem explícita: sem fonte não
há barra de referência nem corrente de curto.

## Redes de sequência nodais

O solver de sequência caminhava a topologia como árvore radial a partir de uma
única fonte — com o GE2 isso deixou de valer e estourava
`Solver de terra requer exatamente uma fonte síncrona`.

`run_ground_sequence_fallback` e `_radial_phase_min_sequence` passaram a montar
a Ybus em pu na base comum, inverter por componente conexo e ler a Thévenin na
diagonal. Barras sem caminho até uma referência de terra na sequência (as de
13,8 kV atrás do delta do T1 na sequência zero) ficam marcadas como sem Z0
utilizável, em vez de receber um valor inventado.

Conferido contra o baseline de uma fonte só: desvio máximo de 1,3e-10 %, zero
divergências. Os métodos passaram a se chamar "IEC nodal …".

## Dois motores manobráveis na barra de 6,6 kV

`M-B-1` e `M-B-2` são cópias integrais do `M-B-0` (mesma placa, mesma
impedância, mesmos pontos térmicos, mesmo Hot Start), cada um no seu terminal
(`Barra7`, `Barra8`) com ramal próprio (`Cabo4`/`Cabo5`, `DJ6`/`DJ7`,
`Relé4`/`Relé5`, `TC-Relé4`/`TC-Relé5`, zonas `Z-R4`/`Z-R5`). Entram **fora de
serviço**.

Os motores ganharam o mesmo campo **Em serviço** dos geradores. Fora de
serviço, o motor não carrega a barra no fluxo, não entra como fonte de
contribuição no caso MAX da IEC 60909 e não desenha curva no coordenograma
geral — que mostra a configuração que está rodando, não o cadastro. No caso MIN
nada muda, porque o caso MIN já não conta com motor nenhum.

Um teste garante que os espelhos continuam idênticos ao `M-B-0`: se alguém
editar a placa ou a curva térmica de um só, a comparação da aula deixaria de
ser entre iguais.

## Unifilar

Ramais de gerador e de motor fora de serviço aparecem esmaecidos, com o
disjuntor marcado em vermelho e o rótulo "fora de serviço". Os ramais de motor
passaram a mostrar o nome do relé, como os demais.

O cabo deixou de ser um traço reto: é desenhado pela sua impedância — zigue-zague
de resistência e bobina de indutância em série, como no ETAP.

## Curva Hot Start dos motores

O coordenograma dos motores passou a desenhar a envoltória de Hot Start,
`t(I) = t_stall·(ILR² − In²)/(I² − In²)`, recortada ao domínio físico (do
primeiro ponto Stator-Hot até a corrente de rotor bloqueado). `M-B-0`:
557,9 A/34,2 s → 1003,7 A/10,0 s. `M-B-6`: 1027,2 A/41,1 s → 1848,1 A/12,0 s.

A faixa sombreada entre partida e dano e a anotação "fim do dado de dano"
saíram: poluíam o desenho sem acrescentar informação.

## Tela "Cálculo 51" oculta

O passo a passo do estágio inverso (`view-manual`) saiu do menu. É material de
apoio, não faz parte do fluxo de estudo. A rota `/api/manual51`, a seção
`view-manual` e os testes continuam no lugar — o botão está comentado em
`templates/index.html` e volta descomentando uma linha.

## Documentação dos módulos (build 30.1)

Passagem de documentação para apresentação em aula. **Nenhuma linha de código
executável foi alterada** — verificado comparando a árvore sintática de cada
módulo, com as docstrings removidas, antes e depois: idêntica nos sete
arquivos.

- **Docstring de módulo nos sete arquivos.** Cinco não tinham nenhuma
  (`network.py`, `solver.py`, `protection.py`, `storage.py`, `app.py`). Cada
  uma diz o que o módulo é, onde entra no pipeline
  `data → storage → network → solver → protection → app`, quais são os pontos
  de entrada e qual decisão de projeto vale explicar.
- **Dezenove faixas de seção** em `protection.py` (2.914 linhas, antes com
  duas marcas) e `solver.py`. Os seis blocos de `protection.py` batem com a
  lista que a docstring do módulo anuncia.
- **Comentários e docstrings de módulo reflúidos a 72 colunas**, conforme a
  PEP 8: *"for flowing long blocks of text with fewer structural restrictions
  (docstrings or comments), the line length should be limited to 72
  characters"*.
- A docstring de `data.py` foi reescrita: a anterior ainda falava da V27 e
  tinha uma frase quebrada ("A V27 mantém a separar corretamente").

## Documentação das funções (build 30.2)

A passagem anterior documentou os módulos; esta documenta as **funções**. Ela
também não altera código executável: mesma verificação de árvore sintática,
idêntica nos sete arquivos (a única diferença em `data.py` é o `BUILD_TAG`).

- **As 92 funções públicas têm docstring.** Antes, 49 não tinham nenhuma e
  outras 19 tinham só a linha de resumo, sem explicar nada.
- **Cada docstring abre pelo objetivo**, numa frase, e quando a função é um
  passo de uma cadeia mostra essa cadeia com setas — o mesmo recurso que as
  docstrings de módulo usam para situar o arquivo no pipeline. Nas rotas do
  Flask a seta liga a URL à função que faz o trabalho, por exemplo
  `GET /api/tcc/<zona>  ->  build_tcc  ->  traços  ->  Plotly`.
- Depois do objetivo vem a **razão da decisão de projeto**, que é o que não se
  descobre lendo o código: por que o caso MIN ignora os motores, por que a
  prévia do coordenograma entra depois do `save_settings`, por que dado
  ausente devolve *pendente* em vez de reprovado, por que o múltiplo congela
  em 20 × Is.
- **A regra de 72 colunas agora vale para o arquivo inteiro**, não só para as
  docstrings de módulo e os comentários: eram 193 linhas fora da regra nas
  docstrings de função e em comentários de fim de linha, hoje são zero. Os
  resumos compridos foram **encurtados**, não quebrados em duas linhas, porque
  a PEP 257 pede resumo de uma linha só.
- Três defeitos de formatação da passagem anterior corrigidos: itens de lista
  cujas linhas de continuação tinham perdido o recuo (em `data.py`,
  `network.py` e `protection.py`), e a docstring de `protection.py`, que
  anunciava cinco blocos existindo seis. As faixas `BLOCO 5` e `BLOCO 6`
  trocaram de nome para ficarem em ordem crescente no arquivo.

Sobre o comprimento das linhas de código: 618 passam de 79 colunas, a maior
parte literais de dado em `data.py` e expressões longas em `protection.py`.
A própria PEP 8 prevê isso — um time pode subir o limite do código até 99
colunas *desde que comentários e docstrings fiquem em 72*, que é exatamente a
situação atual. Reflúir os dados em várias linhas deixaria a tabela do caso
menos legível, não mais.

## Setas de corrente paradas no coordenograma (build 30.3)

Recalcular o sistema com a folha de coordenograma aberta não movia as setas de
falta: elas continuavam no valor do curto anterior. Trocar de aba e voltar
mostrava o resultado certo, o que escondia o defeito.

A causa era de tela, não de cálculo. Cada vista só se remontava ao ser **aberta
pelo menu** (`showView`). O botão *Recalcular sistema* e o salvamento de
equipamento invalidavam o cache do servidor e recarregavam o resumo, mas não
pediam o desenho de novo — a figura do Plotly ficava com os dados antigos na
tela.

Conferido que o servidor estava certo: substituindo a fonte de falta por um
valor controlado, `build_concise_tcc` devolve 10.000 A e, depois de
`clear_solver_cache()`, 22.000 A na mesma folha. O número novo existia; só não
chegava à tela.

Duas funções novas em `static/app.js`:

- `invalidateDerivedState()` — limpa tudo que foi derivado do resultado
  elétrico: fluxo, curto, `expertData`, `review` e a última folha desenhada. O
  `expertData` era o pior dos casos: `loadExpert()` só busca quando ele está
  nulo, então o especialista guardava número velho a sessão inteira, mesmo
  saindo da tela e voltando.
- `reloadActiveView()` — remonta a vista que está aberta no momento.

As duas são chamadas pelo botão *Recalcular sistema* e por
`refreshAfterEquipmentChange()` (salvar/restaurar equipamento). Quando a folha
está na frente, o aviso passa a dizer "coordenograma redesenhado".

Verificação no navegador (Chromium, `tests` manuais em `scratchpad`): com a
fonte de falta trocada de 10 kA para 22 kA e um clique em *Recalcular sistema*,
as setas da folha M-B-0 vão de 10.000/6.960 A para 22.000/15.312 A sem trocar
de aba. Com a correção desativada, as duas ficam paradas — que é exatamente o
defeito relatado.

`tests/test_v30_redraw.py` trava o comportamento.

## Seta de falta das folhas de motor (build 30.5)

Mudando a potência do `M-B-0` de 6.000 para 8.600 kW, as curvas do motor e o
unifilar andavam, mas as setas de falta da folha dele ficavam paradas. Não era
defeito de tela: era o que as setas mediam.

A falta do `Relé11` é aplicada no terminal do motor e, no caso MAX, **o próprio
motor protegido é retirado** (`run_zone_remote_fault`) — ele não alimenta,
através do próprio cabo e do próprio relé, um curto que está atrás dele. A seta
mostrava essa corrente *passante*, que é a grandeza certa para ajustar o 50/51
e que, por construção, não depende da placa daquele motor. No caso MIN nenhum
motor entra, então ali nada mudava nunca.

Conferido montando a rede de curto que o solver gera, com 6.000 e com 8.600 kW:

| folha | falta em | rede de curto |
|---|---|---|
| M-B-0 · Relé11 | Barra6, MAX | `M-B-0` fora → **idêntica**, a seta não andava |
| M-B-6 · Relé3 | Barra4, MAX | `M-B-0` de 6,62 → 9,49 MVA → a seta anda |
| T1 · Relé10 | Barra5, MAX | `M-B-0` de 6,62 → 9,49 MVA → a seta anda |
| qualquer, MIN | — | nenhum motor → nunca anda |

As duas folhas de motor passaram a desenhar **uma seta só: o curto na barra do
próprio equipamento** (`Barra6 - 3P` e `Barra4 - 3P`), caso MAX, com o motor
dentro. É a leitura que acompanha o estudo quando a placa do motor muda, e é a
que a aula usa. As duas setas antigas, de corrente passante, saíram do desenho.

**Nenhum número saiu do estudo.** A corrente passante e o mínimo de
sensibilidade continuam calculados e seguem comandando a coordenação, as
verificações da zona e o módulo especialista; na folha, aparecem escritos na
nota, junto da falta da barra. `_motor_view_fault_note` monta esse texto.

T1 e Geral não mudaram: lá nenhum motor é retirado, então a falta da barra já
era o que estava desenhado.

De quebra, rótulo de seta perto da borda direita passou a virar para a
esquerda, em vez de sair da folha.

`_zone_fault_reference_trace` saiu, por ter ficado sem uso — quem calcula a
corrente passante é `run_zone_remote_fault`, que continua no lugar.
`tests/test_v30_redraw.py` cobre o comportamento.

## Correções

- `Icu/Ics` é nomenclatura da IEC 60947-2, que cobre até 1000 V. O caso é de
  13,8/6,6 kV, então os disjuntores são de média tensão (IEC 62271-100) e o
  parâmetro chama-se corrente nominal de interrupção em curto-circuito. O rótulo
  errado aparecia em três pontos de `core/protection.py` e dois de `static/app.js`.

- `relay_operation_detail` estourava `UnboundLocalError` quando o estágio 50
  tinha delay programado maior que zero e a corrente passava do pickup — o caso
  do `Relé1` (0,01 s, pickup 14.712 A). Antes do GE2 a corrente não chegava lá;
  com as duas fontes em paralelo, chega.
- `Z-R12` tinha a chave `relay_etap_name` repetida no mesmo dicionário.
- O teste `test_toda_vista_tem_unifilar_e_carimbo` ainda exigia unifilar na
  Vista Geral, que deixou de desenhar um de propósito (junta relés de ramais
  diferentes; um fio vertical único não representaria o gráfico).
