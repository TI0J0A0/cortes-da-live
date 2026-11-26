---
name: cortes-de-live
description: >
  Transforma VODs e gravações de gameplay em múltiplos Shorts gamers: examina
  toda a live, acha jogadas, bosses, sustos, bugs e reações autênticas, seleciona
  cerca de 10 cortes por hora de live, processando e entregando hora a hora,
  na melhor qualidade possível, preserva a facecam,
  renderiza vertical com gameplay em destaque e entrega arquivos em shorts/.
  Use quando pedirem cortes de live, shorts de jogos, clipes gamers, edição de VOD
  ou preparação do projeto de cortes, inclusive para Claude Code.
---

# Cortes de live gamer: fluxo obrigatório

**Prioridade:** gameplay e emoções reais, não uma edição de podcast. A câmera precisa permanecer nítida e não pode ser esticada até ocupar a tela toda quando a fonte for pequena. Resultado deve ser rápido, mas precisa passar por revisão. Não faça postagens nas redes, entregue arquivos.

**Referência visual do usuário:** leia `referencias/layout-facecam-fade.md` e consulte `referencias/layout-facecam-fade-exemplo.png`. O exemplo demonstra **somente o fade/gradiente de união**: a posição dos blocos na imagem está invertida em relação ao solicitado. **No resultado, facecam em cima e gameplay embaixo, sempre.** O fade vertical na emenda **já está implementado** nos dois renderizadores do `cortar.py` (veja "Esqueleto da tela").

## ⚠️ REGRA GERAL (vale para TODA live, sem precisar pedir)

1. **Cerca de 10 cortes por hora de live.** Meta de 10 por hora (aceitável de 8 a 12). Uma live de 5 h rende ~50 shorts. **Nunca invente cortes fracos para bater a meta:** se uma hora só tiver 6 momentos bons, entregue 6 e diga por quê.
2. **⚠️ LEGENDA SÓ COM A FALA DO STREAMER.** Diálogo de personagem, cinemática, rádio e NPC do jogo **nunca** entram na legenda, nem no "O QUE É DITO" do `.txt`. O `cortar.py` mede o idioma de cada frase no áudio e tira da legenda o que não é português, porque o jogo fala inglês e o Whisper com língua fixa em português *traduz* essa fala e ela vazaria como se fosse sua. Quando mais da metade da fala de um corte é do jogo, ele mostra **⚠️ ALERTA** (na prévia e no render): nesse caso, confira se o momento se sustenta só com a sua reação ou troque o momento. Na revisão (seção 5), toda legenda que mostrar fala de personagem é defeito: refaça com `--so NN`.
3. **Shorts curtos e com gancho.** Mire em **25 a 45 s**; o `conferir.py` avisa acima de 45 s e rejeita acima de 60 s. Comece no gatilho (a ação nos 2 primeiros segundos) e termine logo depois da reação.
4. **Melhor qualidade possível.** Fonte original do OBS quando existir; senão, o link (o `cortar.py` baixa a melhor resolução até 4K, maior fps e maior bitrate). Render H.264 `crf 16`/`slow`, áudio 256 kbps. Nada de recomprimir trechos à toa.
5. **Separado por hora.** Cada hora vira uma pasta própria: `lives/<id>/hora-1/`, `hora-2/`, `hora-3/`... (análise, cortes e entrega independentes).
6. **Ordem: hora 1 → hora 2 → hora 3 → ...** Comece SEMPRE pela primeira hora.
7. **Entregar enquanto processa a próxima.** Assim que a hora N estiver cortada e revisada, entregue (`entregar.py`) e avise o usuário com a lista dos shorts. Enquanto você analisa/corta a hora N, a transcrição das próximas horas já está rodando em segundo plano. O usuário recebe vídeos desde a primeira hora, sem esperar a live inteira.

### Pipeline por hora (como executar a regra)

```bash
# UMA vez, em SEGUNDO PLANO (tarefa em background no Claude Code): baixa áudio e chat uma vez só e
# transcreve hora 1, 2, 3... em sequência. Cada hora aparece pronta em lives/<id>/hora-N/ ("HORA N PRONTA").
python "$SKILL/ferramentas/pipeline.py" ouvir "LINK" --lingua pt
# a qualquer momento: em que pé está cada hora e qual o próximo passo
python "$SKILL/ferramentas/pipeline.py" status "lives/<id>"
```

Rodar `ouvir.py --hora N` à mão continua funcionando; duas horas rodando ao mesmo tempo não baixam o áudio duas vezes (há uma trava na pasta da live), mas em sequência é mais rápido, porque o Whisper já usa todos os núcleos.

Para cada hora N, em ordem, assim que ela estiver transcrita:

1. Leia `lives/<id>/hora-N/resumo.md` e **todas** as `janelas/` da hora; escreva `hora-N/momentos.json` com os melhores candidatos (mire em ~10 que passem no filtro; pode listar alguns a mais para o conferir escolher). A janela final tem uma faixa `--- SOBRA ---` com o primeiro minuto da hora seguinte: use só para fechar contexto, **não comece cortes ali** (eles pertencem à próxima hora).
2. `python "$SKILL/ferramentas/conferir.py" "lives/<id>/hora-N"` (padrão: até 10 cortes, nota mínima 65, 12 a 60 s).
3. `python "$SKILL/ferramentas/cortar.py" "lives/<id>/hora-N" --previa`: baixa os trechos e monta `trechos/NN-previa.jpg` (6 quadros do momento, com o horário da live), **sem renderizar**. Abra cada prévia: se a ação prometida no título não aparece, rebaixe ou troque o momento no `momentos.json` e rode o conferir de novo.
4. `python "$SKILL/ferramentas/cortar.py" "lives/<id>/hora-N"` (pode rodar em segundo plano enquanto você começa a ler as janelas da hora N+1). Os trechos da prévia são reaproveitados.
5. Revise as folhas `-conferir.jpg` (seção 5). Refaça só o que falhar com `--so NN`.
6. `python "$SKILL/ferramentas/entregar.py" "lives/<id>/hora-N"` → `Shorts prontos para postar/<AAAA-MM-DD - Site - live de XhYY (id)>/Hora N - NN - Título.mp4`, com `textos/` e o `LEIA-ME.txt` da live.
7. Avise o usuário: "Hora N entregue: X shorts em ..." com título, duração e nota de cada um. **Siga direto para a hora N+1**, sem esperar resposta.

`pipeline.py`/`ouvir.py` mostram quantas horas a live tem. A última hora pode ser mais curta (ex.: 6h54 → hora 7 tem 54 min; meta proporcional, ~1 corte a cada 6 min). As horas compartilham o áudio, o chat e o volume baixados uma vez em `lives/<id>/`.

## Instalação (uma vez)

No Windows, use `python` (ou `py`) em vez de `python3`. Os exemplos devem ser executados a partir da pasta de trabalho onde ficará `lives/`. `$SKILL` é o caminho para esta pasta do skill.

```bash
python "$SKILL/ferramentas/preparar.py"
python "$SKILL/ferramentas/preparar.py" --conferir
```

O instalador prepara yt-dlp, FFmpeg, OpenCV, fontes, detector de rostos e Whisper em `~/.cortes-de-live`. O modelo padrão do Whisper é o `large-v3-turbo` (muito mais preciso em PT-BR com gíria de jogo; ~6x mais rápido que o tempo real no processador). Para velocidade, `--modelo small` ou `CORTES_MODELO=small`.

**Chat da Twitch:** o yt-dlp não baixa mais o replay do chat da Twitch. Com o [TwitchDownloaderCLI](https://github.com/lay295/TwitchDownloader) no PATH (ou em `~/.cortes-de-live/`), o `ouvir.py` baixa o chat sozinho. Sem ele, a análise segue só com fala e volume, ou passe um chat baixado à mão com `--chat arquivo.json`.

## 1. Receber o material

Aceite **um link de VOD finalizado** do YouTube, Twitch ou Kick, ou **arquivo original** `.mp4`/`.mkv`/`.mov` do OBS (preferível pela qualidade). Se o usuário já passou fonte, não pergunte de novo. Se não passou nada, peça o link ou caminho do arquivo. O modo de busca por assunto usa `achar.py` no YouTube e não procura automaticamente Twitch/Kick.

```bash
python "$SKILL/ferramentas/pipeline.py" ouvir "https://www.youtube.com/watch?v=ID" --lingua pt
# Gravação original, sem compressão adicional durante a leitura:
python "$SKILL/ferramentas/pipeline.py" ouvir "D:\\Videos\\live.mkv" --lingua pt --canal TiojoaoYT
```

O `ouvir.py` (chamado pelo pipeline) cria `lives/<id>/info.json`, e em cada `hora-N/`: `transcricao.json` (com o tempo de **cada palavra**, reaproveitado na legenda), `sinais.json`, `pistas-gamer.json`, `janelas/`, `resumo.md` e `tempos.json`. O VOD ainda no ar não é suportado. Para conteúdo com restrições, experimente `--cookies chrome` se o usuário tiver acesso autorizado.

Se um hook avisar que o link **já foi processado**, avise o usuário e pergunte antes de reprocessar.

## 2. Analisar TODA a live para captar vários shorts

1. Leia `referencias/como-escolher.md` e `referencias/layout-facecam-fade.md` com atenção. **Não use critérios de podcast** e respeite a referência visual. Se existir `desempenho/relatorio.md`, leia também: ele diz que tipos e durações performam no canal.
2. Leia `resumo.md` e `pistas-gamer.json`. São orientações para encontrar passagens, não prova de eventos visuais.
3. Leia **todas** as `janelas/janela-XX.md` em ordem. Para cada janela de 12 minutos, registre 0 a 4 candidatos, se existirem. Linhas marcadas `JOGO |` são fala do jogo (personagem/cinemática em inglês): **não são do streamer**, não entram na legenda e não sustentam um corte sozinhas. O `conferir.py` dá ⚠️ ALERTA quando mais da metade da fala de um momento é do jogo.
4. Dê destaque a clutch/ace, sustos, boss fights, erros e reviravoltas, descoberta, lore e momentos hilários ligados à partida. Guarde a progressão completa: contexto curto → acontecimento → reação. Evite diálogos longos e frases descontextualizadas.
5. Monte `momentos.json` no formato do guia, com todos os candidatos de nota ≥60. Não invente falas ou acontecimentos a partir de palavras soltas.

Não encerre a análise ao achar apenas três cortes. Pela regra geral, procure **cerca de 10 por hora**, **sem inventar para completar a cota**. Se o usuário pedir outro número, use `--manter N`.

## 3. Conferir momentos

```bash
python "$SKILL/ferramentas/conferir.py" "lives/<id>/hora-N"            # = --manter 10 --nota-minima 65 --maximo 60
```

A ferramenta encaixa os tempos nas frases, rejeita durações inválidas (12 a 60 s), avisa acima de 45 s e evita sobreposição entre momentos selecionados, priorizando a maior nota. Para relaxar o filtro, passe explicitamente outros valores; nunca crie eventos sem evidência.

Leia `momentos-conferidos.json` e os avisos. Não afirme que viu algo que ainda não verificou: a verificação visual vem na prévia (passo seguinte).

## 4. Prévia e corte em `shorts/`

```bash
python "$SKILL/ferramentas/cortar.py" "lives/<id>/hora-N" --previa   # só trechos + trechos/NN-previa.jpg
python "$SKILL/ferramentas/cortar.py" "lives/<id>/hora-N"            # render
```

O programa:
- baixa/copia apenas os trechos aprovados, preservando a melhor fonte disponível (até 4K/2160p por padrão, maior fps e bitrate); **não recodifica os trechos só para forçar keyframes**;
- procura a facecam e usa a câmera inteira na proporção da webcam (veja "Esqueleto da tela");
- usa as palavras com tempo já gravadas pelo `ouvir.py` na legenda (sem rodar o Whisper de novo); em transcrições antigas, ou com `--whisper-trecho`, transcreve o trecho;
- **tira da legenda a fala do jogo**: mede o idioma de cada frase (modelo `small`, ~1 s por frase) e remove as que não são em português, mostrando `legenda: N frase(s) do jogo (en) fora da legenda` e o **⚠️ ALERTA** quando o jogo domina a fala. `--legenda-tudo` desliga (só para jogo dublado em que você fale junto). **Jogo dublado em português:** o idioma não separa; grave no OBS com o microfone numa faixa própria e rode `ouvir.py ... --faixa-voz N` (N = número da faixa do microfone, 0, 1, 2...), que transcreve só a sua voz;
- quando há um layout gamer estável, usa FFmpeg para composição/legendas mais rápida; em trocas complexas de cena e comentários, usa o método compatível;
- exporta MP4 vertical H.264/AAC **1080 × 1920**, título, descrição, hashtags e folha de 6 quadros;
- grava tudo em **`lives/<id>/hora-N/shorts/`** (`.mp4`, `.txt`, `-conferir.jpg` e `cortes.json`). Reedições recebem sufixos `-v2`, `-v3` em vez de apagar os MP4 anteriores.

**Opções úteis:**

```bash
# codificar na placa de vídeo (AMD AMF / NVIDIA NVENC / Intel QSV): ~2,5x mais rápido no encode,
# qualidade um pouco menor que o crf 16 (SSIM 0,995 x 0,997). Sem placa que funcione, volta ao processador.
python "$SKILL/ferramentas/cortar.py" "lives/<id>/hora-N" --gpu
# gameplay mais fluida (aumenta custo de processamento):
python "$SKILL/ferramentas/cortar.py" "lives/<id>/hora-N" --fps 60
# enquadramento da gameplay de UM momento (ex.: o celular do GTA fica na borda direita e sai cortado):
#   no momentos.json, no momento: "enquadrar": "direita"  (ou "esquerda", "centro", ou 0 a 1 = centro do corte)
# câmera manual (coordenadas da imagem de origem; confira trechos/NN-quadro.jpg):
python "$SKILL/ferramentas/cortar.py" "lives/<id>/hora-N" --so 3 --camera 35,38,430,245
# se a detecção automática falhar:
python "$SKILL/ferramentas/cortar.py" "lives/<id>/hora-N" --modo sem
# visual antigo, pode pixelizar câmeras pequenas:
python "$SKILL/ferramentas/cortar.py" "lives/<id>/hora-N" --layout classico
```

A fonte original do OBS é preferível. **Zoom limitado preserva nitidez relativa, mas não recupera pixels ausentes na gravação.**

## 5. Revisão obrigatória

Abra cada `shorts/NN-...-conferir.jpg`. Veja: rosto não esticado, câmera correta e legível, ação presente, HUD relevante visível, começo antes do evento, final depois da reação, texto sem encobrir a jogada, legenda sincronizada e **só com a sua fala** (nada de fala de personagem ou cinemática na legenda amarela/branca; a legenda do próprio jogo, pequena embaixo, é do jogo e pode aparecer). Corte com **⚠️ ALERTA** de fala do jogo precisa de atenção redobrada. Se precisar, veja os MP4 completos.

Se um corte falhar, corrija `momentos.json`, rode `conferir.py` e reexporte **só ele** usando `--so NN`. Se um trecho manualmente alterado mudar de início/fim, o cache será invalidado.

Não considere finalizada a entrega sem inspeção visual. Se não conseguir abrir os MP4 ou revisar as cenas, indique essa limitação em vez de declarar qualidade verificada.

## 6. Entregar

Entregue **por hora**, assim que cada hora ficar pronta:

```bash
python "$SKILL/ferramentas/entregar.py" "lives/<id>/hora-N"
```

Cada live tem **uma pasta só**, com nome legível e os vídeos soltos nela, já na ordem de postar:

```text
Shorts prontos para postar/
  2026-11-24 - Twitch - live de 4h29 (v2938905930)/
    Hora 1 - 01 - Entrei na mansão de um rapper.mp4
    Hora 1 - 02 - O cachorro do rapper apareceu do nada.mp4
    Hora 2 - 01 - ...
    LEIA-ME.txt     título, legenda, hashtags, duração e nota de cada short, hora por hora
    textos/         o .txt de cada short, com o mesmo nome do vídeo
```

O nome da pasta é escolhido na primeira entrega e guardado em `lives/<id>/pasta-entrega.txt`, para as horas seguintes caírem na mesma pasta. Os vídeos entram como **hard link** (aparecem nas duas pastas mas ocupam o disco uma vez só; em outro disco ele copia), na versão mais recente de cada corte (a `-v3` ganha da `-v2`). O `entrega.json` da hora guarda título, tipo, duração, nota, legenda e hashtags de cada short (usado pelo `LEIA-ME.txt` e pelo `desempenho.py`). Reentregar uma hora troca só os arquivos `Hora N - ...` dela. Depois de entregar, apaga de `shorts/` as versões superadas e os cortes descartados na revisão (`--manter-tudo` desliga a limpeza). A pasta `trechos/` fica, para refazer cortes sem baixar de novo. Informe ao usuário: hora, quantidade de shorts, pasta e, para cada short, título, duração, nota e motivo. Se a hora tiver menos de 8, explique que só esses atingiram os critérios. Ao final da live, um resumo geral (`pipeline.py status`). Não publique nada diretamente.

## 7. Agendar no Metricool e limpar

Quando o usuário pedir para agendar shorts (o Metricool é acessado pelo conector MCP; marca, padrão de texto e horários na memória do projeto):

```bash
# 1. salve a agenda atual (getScheduledPosts, em períodos curtos por causa do limite de tamanho) em agenda.json e planeje:
python "$SKILL/ferramentas/agendar.py" planejar "Shorts prontos para postar/<pasta da live>" --shorts "Hora 2 - 02" "Hora 5 - 03" --agenda agenda.json --de 2026-11-26 --ate 2026-11-27
# 2. mande cada post de plano-agendamento.json para o createScheduledPost (Instagram REEL, TikTok, YouTube short, GAMING,
#    madeForKids false, comentário fixado do plano)
# 3. depois de agendados: registra o texto postado, apaga vídeo e texto da pasta de entrega e refaz o LEIA-ME
python "$SKILL/ferramentas/agendar.py" concluir plano-agendamento.json
```

O `planejar` escolhe os horários livres no padrão do canal (10h, 16h, 18h, extras 13h e 21h; se o dia estiver cheio, 12h, 20h, 19h, 15h; no mínimo 1 h entre posts), sobe os vídeos no litterbox (72 h; o Metricool copia o vídeo na hora do agendamento) e monta texto, títulos do YouTube/TikTok, tags e comentário fixado. Respeite horários e datas que o usuário pedir (`--de/--ate`).

**Limpeza** (o usuário quer a pasta de entrega só com o que falta postar e sem arquivos de trabalho):

```bash
python "$SKILL/ferramentas/limpar.py" --agendados agenda.json --trabalho            # só lista
python "$SKILL/ferramentas/limpar.py" --agendados agenda.json --trabalho --apagar   # apaga
```

`--agendados` apaga os shorts entregues que já estão no Metricool (mesmo título ou texto registrado em `postado`, e post criado depois da entrega daquela hora, para um título repetido de outra live não apagar o short errado). `--trabalho` deixa em `lives/<id>/` só `info.json`, `pasta-entrega.txt` e os `hora-N/info.json` e `entrega.json`, apagando trechos, áudio, transcrições e versões, e só em lives com todas as horas entregues. `--sem-entrega` inclui lives nunca entregues. No Windows/OneDrive, as pastas vazias que o Python não remove saem pelo PowerShell. Rode com `--apagar` quando o usuário pedir ou já tiver autorizado a limpeza depois de agendar.

## 8. Aprender com o desempenho (Metricool)

Uma tarefa agendada (`relatorio-semanal-shorts`, toda segunda às 9h, com o app aberto) puxa as métricas da semana, roda o `desempenho.py` e atualiza a seção "O que o público do canal mostrou" do `como-escolher.md` quando houver conclusão nova. Também dá para fazer na hora:

Quando o usuário pedir (e com o Metricool autorizado em `/mcp`): puxe as métricas dos posts de Shorts pelo MCP do Metricool, salve a lista de posts em `desempenho/metricool-AAAA-MM-DD.json` e rode:

```bash
python "$SKILL/ferramentas/desempenho.py" desempenho/metricool-AAAA-MM-DD.json
```

Ao **agendar** um short no Metricool com um texto diferente do título entregue, acrescente esse texto em `"postado": ["..."]` no item do short em `hora-N/entrega.json`, para o `desempenho.py` reconhecer o post depois.

Ele liga cada post ao short entregue pelo título (ou pelo `postado`), lista à parte os posts sem short correspondente e escreve `desempenho/relatorio.md` com views, retenção e "pulou em 3 s" (skip rate do Instagram, métrica IGRE30) por tipo de momento e por faixa de duração, se a nota prevê o resultado, e os 5 melhores e piores. Use as conclusões nas próximas escolhas e proponha ajustes em `referencias/como-escolher.md`.

## Esqueleto da tela (padrão aprovado)

A tela padrão está em `referencias/esqueleto-tela.json` (referência: `referencias/layout-esperado.webp`): facecam em largura total no topo **na mesma proporção da webcam do OBS (1280x720 = 16:9 → 0–608 px, `"proporcao": "16:9"`), câmera inteira sem cortar laterais**, fade de 90 px sobre a gameplay (gameplay de 518 px até o fim), selo amarelo do título centrado na emenda (y=608) **só nos primeiros 3,5 s** (gancho; some com fade), legenda Arial Bold de 90 px palavra por palavra em **y=1300** (68% da altura, acima da descrição e dos botões que o TikTok e o Instagram põem no rodapé) e **sem barra de progresso** (as plataformas já têm a delas). O fade **já está implementado** nos dois renderizadores. `cortar.py` lê esse arquivo como padrão; mude a tela ali, não no código.

**Câmera inteira:** a facecam usa a caixa completa da webcam. Quando a detecção pega só um pedaço (ou pega parte do jogo), `cortar.py` usa a caixa dominante da hora somada às horas anteriores, guardada em `lives/<id>/camera-live.json`. Se mesmo assim um corte sair errado, refaça com `--so NN --camera x,y,l,a`.

Para conferir o layout antes de renderizar tudo:

```bash
python "$SKILL/ferramentas/esqueleto.py"                                        # wireframe com medidas
python "$SKILL/ferramentas/esqueleto.py" --quadro "lives/<id>/hora-N/trechos/01-quadro.jpg"   # sobre um quadro real (usa camera.json)
```

## Encerramento (últimos 2,5 segundos)

Todo short termina com o card `referencias/encerramento-ao-vivo.png` ("Venha assistir ao vivo" + Twitch/Kick/YouTube), igual a `referencias/encerramento-exemplo.png`: nos últimos **2,5 s** (era 5 s: num short de 25–45 s, 5 s de tela desfocada é 1/5 do vídeo sem conteúdo e atrapalha o replay automático) o vídeo desfoca e escurece levemente, o card entra com fade + zoom leve (85% → 100%, ease-out em 0,4 s), título e legenda somem, e o vídeo e o áudio terminam com fade out de 0,6 s. O som do corte continua por baixo do card. Em cortes curtos o encerramento usa no máximo 40% da duração. Ajuste em `referencias/esqueleto-tela.json` → `encerramento`, ou por live no `estilo.json` (`"encerramento": false` desliga; `{"segundos": 4}` muda só essa chave). Para trocar a arte, substitua o PNG (fundo transparente).

## Alterar o estilo

`lives/<id>/hora-N/estilo.json` pode conter:

```json
{
  "layout": "gamer",
  "cor_destaque": "#FFD60A",
  "facecam_zoom_max": 1.65,
  "palavras_por_legenda": 3,
  "tamanho_legenda": 76,
  "titulo": true,
  "barra": true,
  "maiusculas": true,
  "gpu": false,
  "qualidade_amf": 45
}
```

Apenas o que quiser mudar precisa constar nesse arquivo. `qualidade_amf` (placa AMD): maior = melhor, 1 a 51. `qualidade_gpu` (NVIDIA/Intel): menor = melhor.

## Modo comentário opcional

Coloque `lives/<id>/hora-N/comentarios/NN-abre.m4a` ou `NN-fecha.m4a` e rode `cortar.py ... --so NN` para criar uma versão comentada. No canal de jogos, **não introduza narração extra quando a própria gameplay e a reação já contam a história**. O render de comentários usa o modo compatível.

## Testes

```bash
python -m unittest discover -s testes -v     # com o Python de ~/.cortes-de-live/ambiente
```
