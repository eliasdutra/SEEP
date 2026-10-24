# V20 — cadeia de estudo restaurada

- Restaurado o fluxo completo: **modelo físico → fluxo → curto IEC 60909 → ajustes 50/51 → TCC**.
- Retirado o sistema especialista da interface e do fluxo principal.
- Cinco ajustes P241 editáveis: Relay1, Relay10, Relay12, Relay11 e Relay3.
- Valores iniciais iguais aos OC1 atuais das telas ETAP de 30/08/2026.
- `Restaurar ETAP` volta aos valores transcritos; `Salvar ajustes` persiste somente proteção.
- TCCs não usam Icc copiada de STAR: linhas MAX/MIN vêm do solver.
- Quatro vistas: M-B-0, M-B-6, T1 e Geral.
- T1 inrush atualizado para 8 pu / 1 ciclo = 0,0167 s.
- M-B-0 atualizado para aceleração 100% Vt = 1 s conforme a tela mais recente.
- Tela de ajustes mostra TC primário/secundário, múltiplos OC1, fórmula IEC e atuação calculada nas correntes MAX/MIN.
- Alteração de proteção não dispara novo fluxo/curto; `Recalcular` limpa caches e refaz o estudo elétrico.
