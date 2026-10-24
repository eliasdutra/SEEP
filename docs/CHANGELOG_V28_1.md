# V28.1 — revisão de consistência e interruptor do cache

Revisão feita sobre a V28, sem alterar nenhum resultado elétrico. A validação
contra o ETAP Star75 continua com desvio máximo de 0,61 %.

## 1. Identidade do programa

A pasta dizia v28 e a aplicação se apresentava como **V27** em nove lugares:
título da janela, selo da tela inicial, aviso do cache, eyebrow do coordenograma,
`setup_windows.bat`, o campo `version` de `/api/settings/export`, o carimbo do
rodapé do coordenograma e o `CASE_ID`/`CASE_NAME` — que são **impressos na própria
folha do coordenograma**. Ou seja, a folha saía carimbada com a versão errada.
Tudo padronizado em V28.

Comentários no código que dizem "V27: tal comportamento passou a…" foram mantidos:
ali a referência histórica está correta.

## 2. Documentação que contradizia o código

`docs/HIPOTESES_DO_MODELO.md` afirmava que a ampacidade "não foi fornecida". A V28
cadastrou 81,3 A para o `Cable2`, lida do STAR75, e desenha essa marca. O texto foi
corrigido, mantendo a ressalva de que a ampacidade não é usada para afirmar
carregamento percentual.

## 3. Correção de um erro latente

Em `_motor_view_traces`, a ampacidade era referida à tensão por
`cable.get("from_kv", motor["kv"])` — e **nenhum cabo possui a chave `from_kv`**.
A expressão caía sempre no kV do motor e só funcionava por coincidência, porque nas
duas vistas de motor o cabo e o motor estão no mesmo nível de tensão. Agora a tensão
vem da barra de origem do cabo (`from_bus`). Sem efeito no caso atual; evita uma
marca deslocada silenciosamente em qualquer caso futuro.

## 4. Scripts de validação obsoletos, removidos

Quatro arquivos apontavam para o modelo **completo anterior** (Bus3, Cable15,
Bus17), que não existe no caso reduzido:

- `reference_case01.py`, `reference_mod3_v12.py` — referências transcritas daquele modelo;
- `validate_v12_manual.py` — calculava Bus17/Cable15 e imprimia resultados de um sistema inexistente;
- `validate_v13_phase_min.py` — quebrava com `KeyError: 'Bus3'`;
- `validate_against_reference.py` — comparava contra as referências acima e respondia
  **"REVISAR" em fluxo, curto MAX e curto MIN sempre**, dando alarme falso sobre um
  modelo que está correto.

Restou `validation/validate_v28_etap_star75.py`, que é a verificação vigente.

## 5. Novo: interruptor do cache elétrico

`core/solver.py` ganhou a constante **`CACHE_ENABLED`** e o decorador `cacheable`,
que substitui o `lru_cache` direto nas seis funções do solver.

```python
CACHE_ENABLED = True     # troque para False e todo cálculo é refeito
```

Com `False`, cada consulta reexecuta o Pandapower. Os resultados são idênticos; muda
apenas o tempo de resposta — e a tela de estado passa a mostrar "Fluxo —" em vez de
"Fluxo OK", porque de fato não há nada guardado.

Antes, desligar o cache exigia comentar os decoradores `@lru_cache`, o que quebrava
`clear_solver_cache()` com `AttributeError` (a função perdia o `cache_clear`). O
invólucro `cacheable` mantém `cache_clear` e `cache_info` nos dois modos.

Existe para que o efeito do cache possa ser **medido**, ligando e desligando, em vez
de explicado.

## 6. Peso do projeto

`static/vendor/plotly.min.js` são 4,6 MB — **93 % de todo o projeto**. O arquivo traz
49 tipos de gráfico embutidos; a aplicação usa dois (`scatter` e `bar`). Instruções
para trocar pelo bundle *basic*, sem perder nenhuma função, em
`static/vendor/LEIA-ME.md`.

## 7. Relatado, não alterado

- **7 rotas sem chamador na interface** (`/api/tcc/<zone>`, `/api/tcc-path`,
  `/api/tcc-master`, `/api/breaker-duty`, `/api/phase-min-validated`,
  `/api/cache-status`, `/api/settings/export`), que sustentam cerca de 559 linhas de
  `core/protection.py` — coordenação por pares, TCC de caminho, TCC mestre e dever de
  interrupção. É engenharia funcionando, não lixo: mantida à espera de interface.
- `syncTCCScope()` definida e nunca chamada em `static/app.js`.
- CSS de telas que não existem mais (`.tcc-card`, `.tcc-layout`, `.analysis-card`,
  `.tcc-toolbar`, `.pair-table`, `.general-filters`, `.breaker-duty-panel`), incluindo
  três definições concorrentes de `.tcc-card:before`.
