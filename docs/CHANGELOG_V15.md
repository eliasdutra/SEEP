# Changelog V15

- Modelo ativo reduzido para GE + T1 + M-B-6 + M-B-0, conforme último unifilar ETAP.
- Removidos do caso ativo: T2, Bus3, Bus17, Cable15, CB27 e MEQ3005.
- Cadastrados dados ETAP Protection de M-B-6 e M-B-0: aceleração 100/80/110% Vt = 2/4/8 s, Hot Stall 12 s, Cold Stall 40 s e fator LRC assimétrico 1,6.
- Nova regra especialista `R-MOT-TMS-01`: janela de TMS entre ride-through da partida e Hot Stall no ponto de LRC.
- Recomendações de estudo: M-B-0 TMS 0,685 e M-B-6 TMS 0,620 para IEC VI, pickup preliminar atual e margem 0,30 s.
- Coordenogramas local, caminho e geral exibem In, ILR, partida 100% Vt e pontos Hot/Cold Stall.
- Base padrão do coordenograma geral alterada para 6,6 kV; o nível 0,48 kV foi removido do caso ativo.
- Curva térmica completa continua pendente até receber `Points...` do ETAP; nenhum ponto intermediário é inventado.
- Suíte V15 atualizada para o modelo reduzido: 43 testes aprovados.
