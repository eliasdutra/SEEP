# V18 — transformador no coordenograma

- adicionada vista dedicada `T1 · Trafo`;
- T1 mostra R-T1, R-CB1, inrush, curva `T1-damage` e LL MIN em Bus2;
- M-B-0 também mostra inrush e damage do T1, por fazer parte do caminho;
- coordenograma geral continua limpo, sem curvas de dano/inrush;
- `T1-damage` aceita `damage_points_pu` exatos do ETAP;
- enquanto os pontos exatos não são fornecidos, usa uma curva I²t preliminar ancorada em 2 s na corrente limitada por Z%;
- a curva estimada é identificada como tal na legenda e na nota da vista.
