# Como selecionar SHORTS GAMERS (não cortes de podcast)

A live é a fonte da verdade. O objetivo é preservar **a experiência de jogar**, a reação autêntica e o acontecimento que a provocou. Não transforme a live num compilado de frases de efeito. O corte deve fazer sentido para quem nunca assistiu ao canal.

## Fontes disponíveis

- `resumo.md`: duração, picos de volume/chat e **pistas gamer**.
- `pistas-gamer.json`: palavras como `boss`, `clutch`, `susto`, `bug`, `descoberta`. **São apenas pistas extraídas da fala. Não provam que o evento aconteceu no vídeo.**
- `janelas/janela-XX.md`: transcrição integral em intervalos de 12 minutos. `ALTO+9dB` indica mudança de volume; `CHAT x3.1` indica pico de mensagens; `GAME?boss` indica termo relacionado a gameplay.
- `trechos/NN-quadro.jpg` e `shorts/NN-...-conferir.jpg`: revisão visual. Se a transcrição for ambígua, **verifique o trecho em vídeo**, não invente o que aconteceu.

## Como escolher

1. Leia `resumo.md` e as janelas em ordem, **sem pular** períodos sem sinais. Há ótimos momentos sem gritos.
2. Anote **0 a 4 candidatos por janela** quando existirem. Se não houve um evento bom, anote zero.
3. Identifique o tipo de acontecimento e por que vale um short sozinho. Não selecione dez reações quase iguais.
4. Escreva `momentos.json` com todos os candidatos de nota **60 ou maior**.
5. Rode `python ferramentas/conferir.py lives/<id>/hora-N` (até 10 por hora, nota mínima 65, 12 a 60 s). O 10 é um **teto**, não uma meta; selecione menos quando a hora não render.
6. Leia os avisos, rode `cortar.py --previa` e olhe cada `trechos/NN-previa.jpg` antes do render. Uma fala desconectada da gameplay, ou um título que promete algo que não aparece na tela, precisa de ajuste ou descarte.
7. Se existir `desempenho/relatorio.md`, use-o: dê preferência aos tipos e durações que performam no canal.

## Categorias que têm prioridade

1. **Jogada decisiva**: clutch, ace, recuperação impossível, vitória no último segundo, disputa apertada.
2. **Luta ou boss marcante**: introdução do inimigo, surpresa, virada, derrota dramática ou final da luta. Mostre a ação, não apenas a frase depois dela.
3. **Susto real / terror**: alguns segundos de expectativa antes, o susto e o alívio ou risada. Sem cortar o susto.
4. **Falha engraçada**: plano do jogador, erro visível e consequência.
5. **Descoberta de jogo**: segredo, arma, mecânica, bug interessante, puzzle ou revelação.
6. **Reação a um momento de história**: emoção autêntica, reviravolta e comentário espontâneo; evite spoilers gratuitos no título.
7. **Interação com o chat que altera a gameplay**: desafio, trollagem, aposta dentro do jogo, decisão sugerida.
8. **Opinião sobre o jogo**, somente quando ligada a um acontecimento mostrado na tela e com uma conclusão clara. Conversa isolada e trechos de podcast são prioridade baixa.

## Condições para um bom corte

- **Ação compreensível nos 3 primeiros segundos:** comece no gatilho da jogada, susto ou conflito. Se precisar de contexto, acrescente de 3 a 8 segundos anteriores; não invente narração.
- **Uma progressão completa:** preparação → tensão/ação → reação/desfecho. Preserve música, suspense, silêncio e falas relevantes. Não interrompa o clímax.
- **Duração:** mire em **25 a 45 segundos**. Shorts curtos retêm mais: corte a preparação longa e termine logo depois da reação. O `conferir.py` avisa acima de 45 s e rejeita acima de 60 s; boss ou história que realmente precisem de mais tempo pedem `--maximo` explícito.
- **Gancho:** os 2 primeiros segundos precisam mostrar ou anunciar o que vai acontecer (a ação começando, o grito, o inimigo aparecendo). Nada de abrir com silêncio, menu ou "então, gente...".
- **Sem repetição:** não entregue dois shorts quase idênticos. Se dois bons candidatos se sobrepõem, fique com o melhor.
- **Identidade do canal:** expressões naturais do streamer, sem vozes artificiais, sem memes aleatórios ou hashtags inventadas.
- **Ação mostrada:** no conteúdo visual ambíguo, confirmar o vídeo. O transcript sozinho não identifica os acontecimentos do jogo.

## Nota de 0 a 100

| Pontuação | Critério |
|---|---|
| 30 | Acontecimento/jogada visual forte, verificado no vídeo ou inequívoco no material disponível |
| 20 | Gancho e contexto entendidos até 3 segundos |
| 20 | Progressão com clímax real e desfecho |
| 15 | Reação espontânea do streamer e emoção preservada |
| 10 | Originalidade / potencial de compartilhamento |
| 5 | Sinais extras de chat/volume (ajudam, não decidem) |

65+ pode virar short; 60–64 fica como candidato para revisão; abaixo de 60 descarte. **Não aumente a nota só para chegar a 10.** Na ausência de acesso ao vídeo, indique que a avaliação visual permanece pendente e não afirme que a jogada foi confirmada.

## Títulos, descrição e tags

- **Título:** 4 a 9 palavras, preferencialmente até 45 caracteres. Contexto, curiosidade e tensão, sem revelar o resultado desnecessariamente. Exemplos de tom, **não aplicar sem evidência**: "Esse boss não me deu chance", "O clutch mais improvável da live", "Eu não esperava esse susto".
- **Legenda do post:** frase curta, natural, com pergunta apenas quando fizer sentido.
- **Hashtags:** 3 a 5, com o jogo correto e `#tiojoaoyt` quando o canal for TiojoaoYT. Nunca invente o nome de um jogo que não conste em `info.json`, `resumo.md` ou fala confirmada.
- **Texto na tela:** 2 a 3 palavras por bloco, sem cobrir rosto, HUD ou ação decisiva.

## Exemplo de `momentos.json`

```json
{
  "momentos": [
    {
      "inicio": "1:23:45",
      "fim": "1:24:20",
      "nota": 88,
      "tipo": "boss / reação",
      "titulo": "Esse boss quase me derrotou",
      "motivo": "luta, virada e reação natural dentro do mesmo acontecimento",
      "legenda": "Eu já tinha aceitado a derrota. Você passaria desse boss?",
      "hashtags": ["#jogo", "#tiojoaoyt", "#gameplay", "#shorts"]
    }
  ]
}
```

**Atenção:** os nomes e a ação acima são fictícios para explicar o formato. Não os aplique sem confirmar o conteúdo real da live. Os tempos são do relógio da transmissão.
