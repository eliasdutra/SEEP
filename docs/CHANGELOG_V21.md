# V21 — TCC alimentado pela corrente vista pelo relé/cabo

- Mantém Modelo → Fluxo → IEC 60909 → Ajustes → TCC.
- Cable2 e Cable8 usam K²S² exato do ETAP (5,23 e 115,03 kA²s).
- Para ramais de motor, o curto MAX usado no TCC é a corrente que atravessa o relé/cabo: falta no extremo do ramal com o próprio motor protegido excluído da contribuição a montante.
- O curto MIN continua com motores excluídos.
- Adiciona envelope de partida baseado em FLA, LRC e tempo de aceleração 100% Vt.
- Valores do Cable Editor do ETAP ficam como referência de validação, não como entrada do solver.
