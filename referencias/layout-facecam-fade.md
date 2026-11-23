# Referência visual obrigatória: facecam superior com fade para gameplay

**Imagem de referência:** `layout-facecam-fade-exemplo.png` (captura enviada pelo usuário).

## Como interpretar a imagem

A captura mostra **o tratamento visual suave entre duas cenas**. Ela é referência **somente para o acabamento da junção**, NÃO para a ordem dos blocos. **A imagem está invertida em relação ao layout que o usuário deseja:** na referência, a gameplay aparece em cima e a câmera embaixo; no resultado solicitado, a **facecam fica sempre em cima** e a **gameplay sempre embaixo**.

## Regras obrigatórias do layout final (Shorts 9:16)

1. **Parte superior: facecam real** retirada da transmissão ou gravação original. Enquadrar por recorte (crop), preservando a proporção, sem deformar o rosto e **sem zoom/upscale agressivo**. Manter olhos e expressão visíveis e preservar a nitidez que a fonte permite. Não gerar/recriar a facecam artificialmente.
2. **Parte inferior: gameplay**, com prioridade à ação, personagem, boss, alvo e HUD relevante. Não cortar informações críticas da partida para encaixar um template.
3. **Junção entre as duas:** aplicar um **fade espacial vertical suave (máscara de gradiente/alfa)**, de aproximadamente **100–180 px no vídeo 1080 × 1920**, ajustável conforme a composição. A borda inferior da facecam perde opacidade progressivamente, revelando a gameplay imediatamente abaixo. O resultado deve parecer uma transição de cenas sem uma linha dura, com aparência semelhante ao exemplo. Preferir mistura das imagens à aplicação de uma faixa branca opaca.
4. **Preservar a ordem facecam → gameplay durante todo o Short.** Não trocar a câmera para baixo para imitar a referência.
5. **Não confundir efeitos:** o fade pedido é **na separação espacial dos blocos**, e não um fade-in temporal do vídeo todo nem uma transição animada a cada corte.
6. **Não adicionar efeitos desnecessários:** nada de moldura chamativa, barras gigantes, desfoque no rosto, zoom reativo automático ou tarjas que encubram a jogada.
7. **Saída:** MP4 vertical **1080 × 1920**, armazenado em `lives/<id>/shorts/`, com imagem de conferência para validar rosto, enquadramento, blend e legibilidade da gameplay.

## Critérios de aceitação

- A facecam **está no topo**, mesmo que o print de referência a coloque embaixo.
- A gameplay **fica embaixo** e continua sendo o foco do conteúdo gamer.
- A facecam foi **cropada proporcionalmente**, sem esticamento ou ampliação exagerada.
- A fronteira entre ambos é **suave, sem divisão abrupta**, e não apresenta uma tarja clara ou efeito pesado.
- Título e legendas não tapam o rosto nem a ação principal.
- A revisão visual foi feita em quadros do vídeo exportado.

## Para quem estiver implementando no `cortar.py`

Usar esta especificação como referência de design. No caminho acelerado (FFmpeg), substituir a emenda seca de `vstack` por uma composição com máscara/overlay de transparência na zona de sobreposição. No renderizador de fallback (OpenCV), aplicar a mesma máscara de alfa quadro a quadro. Manter a mesma convenção de posição nos dois renderizadores. **Este documento é uma referência visual; sua simples inclusão não implementa o fade no renderizador.**
