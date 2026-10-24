# Verificação técnica — Protection Studio V16

## Objetivo

Reduzir o coordenograma a três visualizações realmente úteis, sem alterar a lógica elétrica de coordenação já existente.

## Verificações executadas

- `python -m compileall`: OK
- `node --check static/app.js`: OK
- suíte Python com `PYTHONPATH=.`: **46 testes aprovados**
- testes novos confirmam que:
  - M-B-0 não mostra cabo, Icc MAX nem corrente nominal como linhas extras;
  - M-B-6 mostra somente os elementos essenciais;
  - Geral contém somente características efetivas dos relés e faltas MIN.

## Limitação do ambiente

Flask e Pandapower não estão instalados neste ambiente, portanto a inicialização completa do servidor/solver deve ser confirmada no Windows pelo `setup_windows.bat` + `run_windows.bat`.
