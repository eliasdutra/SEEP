# Changelog V10

## Núcleo

- Adicionado `core/facts.py`.
- Adicionado `core/rules.py`.
- Adicionado `core/inference.py`.
- Mantido `core/protection.py` como núcleo de curvas/TCC, mas corrigido o critério de falta de fase crítica.

## Critérios corrigidos

- Sensibilidade 50/51: `min(3F MIN, LL MIN)`.
- Coordenação de caminho: menor falta de fase MIN no terminal.
- Dever de interrupção: maior corrente MAX disponível entre 3F, LL, LG e LLG.

## Interface

- Tela Proteção redesenhada como **Sistema especialista**.
- Resumo de fatos por zona.
- Recomendações com regra e justificativa.
- Estados APROVADO / REPROVADO / PENDENTE / DECISÃO DE ENGENHARIA.
- Lista de dados ausentes que bloqueiam a conclusão.
- Análise de coordenação do caminho sob demanda.
- Acesso ao sistema especialista diretamente a partir do unifilar.

## API

- `GET /api/expert/<zone_id>`
- `POST /api/expert/<zone_id>/apply`
- `GET /api/expert-path/<path_id>`
- `GET /api/expert-knowledge`
- `POST /api/protection/<zone_id>/reset`
- `/auto` mantido somente por compatibilidade.

## Testes

- 23 testes aprovados no ambiente de desenvolvimento.
- Incluídos testes da seleção de LL MIN e da maior falta MAX.
- Incluídos testes de recomendações e bloqueios do MEQ3005.
