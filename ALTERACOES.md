# Relatório das mudanças

Projeto original examinado: `SKILL.md`, `LEIA-ME.md` (hoje `README.md`), `como-escolher.md`, `comum.py`, `conferir.py`, `cortar.py`, `ouvir.py`, `preparar.py`, `achar.py`.

## Problema → correção

1. **Só três cortes** → `conferir.py` mantém até **12** por padrão com `--nota-minima 70`. Evita candidatos sobrepostos escolhendo o de maior nota. `--manter N` ajusta o limite sem exigir uma quantidade fixa.
2. **Câmera pixelizada** → `cortar.py` usa layout gamer com facecam em um painel proporcional, limite padrão de escala 1,65×. A fonte preserva até 1440p e evita recodificação antecipada dos trechos.
3. **Estética de podcast** → novo guia editorial privilegia boss, clutch, susto, falha, descoberta, lore e reações ligadas à gameplay. `ouvir.py` marca termos `GAME?`, explicitamente como pistas não verificadas.
4. **Lento** → renderizador FFmpeg para plano gamer com facecam estável; mantém Python para cenas variáveis/comentários. Correlação de áudio feita por OpenCV e amostragem de quadros reduzida.
5. **Pasta de saída errada** → o resultado fica em `lives/<id>/shorts/`.
6. **Falta de fonte original** → `ouvir.py` e `cortar.py` aceitam gravações locais do OBS e copiam os trechos sem recompressão inicial.
7. **Reexportação destruía o resultado anterior** → sufixos automáticos `-v2`, `-v3`, etc.

## Testes executados

- Compilação de todos os scripts Python.
- 4 testes de regressão: facecam pequena, limite de 12 e sobreposições, pistas gamer, legenda ASS.
- Render de um **vídeo sintético** com FFmpeg, gerando MP4 1080×1920/30fps, AAC e folha de seis quadros.
- Leitura de arquivo local e cópia de trecho sem transcodificação, com reutilização do cache.

## Limitações

Não foram fornecidos os VODs/gravações originais da live. Logo, não foi possível selecionar cenas reais nem gerar Shorts reais do canal. A qualidade da câmera ainda depende dos pixels da fonte; a ampliação reduzida não cria detalhes inexistentes. O projeto ainda trabalha com VODs finalizados ou gravações locais; **não realiza captura de clips em tempo real de uma live em andamento**. A análise visual de conteúdo continua exigindo revisão dos trechos.

## Referência visual adicionada após feedback

- `referencias/layout-facecam-fade.md`: regra detalhada de câmera superior cropada, gameplay inferior e gradiente suave na emenda.
- `referencias/layout-facecam-fade-exemplo.png`: print do usuário, **apenas para o acabamento do fade**. A disposição do print é oposta à solicitada.
- `SKILL.md` e `LEIA-ME.md` apontam para a referência. (O fade foi implementado depois, na atualização de 2026-11-20.)

## Atualização 2026-11-20: esqueleto da tela e qualidade máxima

- **Esqueleto da tela fixo:** `referencias/esqueleto-tela.json` define a tela aprovada (`referencias/layout-esperado.webp`): facecam 0–760 px, fade de 160 px (o fade já está implementado nos dois renderizadores), título centrado na emenda (y=760), legenda em y=1574 e barra de progresso de 12 px. `cortar.py` lê esse arquivo como padrão.
- **`ferramentas/esqueleto.py`:** desenha o wireframe ou monta a tela sobre um quadro real da live (`--quadro`) e mostra o zoom da facecam, para conferir antes de renderizar.
- **Mesmo visual nos dois renderizadores:** a legenda passa a usar Arial Bold no modo compatível também, e a barra do modo rápido virou barra de progresso (antes era fixa).
- **Encode de qualidade maior:** H.264 `crf 16`, preset `slow`, perfil High, GOP de 2 s; AAC 256 kbps (antes `crf 18 veryfast` e 192 kbps). Ajustável em `estilo.json` (`crf`, `preset`, `audio_kbps`). O render fica um pouco mais lento, cerca de 2 s de processamento por segundo de vídeo.
- **Nitidez leve na facecam:** unsharp sutil aplicado só quando a câmera é ampliada (`nitidez_camera`: 0.6; 0 desliga). Não cria detalhe inexistente.
- **Limite real:** com o VOD do YouTube, a facecam ocupa ~493×274 px e é ampliada ~2,8× no layout aprovado. Para câmera sem perda, gravar localmente no OBS e gravar a webcam separada (plugin Source Record).

- **Encerramento com card "Venha assistir ao vivo":** nos últimos 5 s de cada short, blur + leve escurecimento, card com fade + zoom leve, título/legenda ocultos e fade out final de vídeo e áudio (0,6 s). Implementado nos dois renderizadores; arte em `referencias/encerramento-ao-vivo.png`, exemplo em `referencias/encerramento-exemplo.png`, ajustes em `esqueleto-tela.json` → `encerramento`.

## Regra geral: ~10 cortes por hora, por hora, entregando enquanto processa

- **Regra documentada no topo do `SKILL.md`:** cerca de 10 cortes por hora de live (8–12, sem inventar cortes fracos), melhor qualidade possível, processamento separado por hora (hora 1 → 2 → 3...), e cada hora é entregue assim que fica pronta enquanto a próxima já está sendo transcrita em segundo plano.
- **`ouvir.py --hora N`:** baixa o áudio, o chat e o volume uma única vez em `lives/<id>/` e transcreve só a hora N (mais 60 s de sobra para contexto, marcada `--- SOBRA ---` nas janelas) em `lives/<id>/hora-N/`, com os tempos da live inteira. Mostra quantas horas a live tem. Opções `--duracao-hora` e `--sobra`.
- **`cortar.py`:** acha o áudio da live na pasta-mãe quando roda em `hora-N/`. Fonte padrão agora até **4K (2160p)**, ordenando por resolução, fps e bitrate.
- **`entregar.py` (novo):** copia a versão mais recente de cada corte (sem o sufixo `-vN`) com o `.txt` para `Shorts prontos para postar/<id>/hora-N/` e escreve um `LEIA-ME.txt` da hora (título, duração, nota, motivo, legenda, hashtags). Reentregar substitui a entrega da hora.
- **`conferir.py` no modo por hora:** `--manter 10 --nota-minima 65`.
- 3 testes novos (entrega, encerramento, esqueleto): 7 testes passando.

## Ajustes feitos durante a primeira live processada por hora (Twitch v2935010407)

- **`entregar.py`:** entrega só os cortes que continuam aprovados (`manter`) no `momentos-conferidos.json` — cortes descartados na revisão visual ficam de fora — e numera a entrega 01, 02, 03... na ordem da live, sem buracos.
- **Legenda sem caracteres estranhos:** `cortar.py` descarta qualquer letra fora do alfabeto latino nas legendas (o Whisper às vezes solta um caractere chinês ou cirílico no meio da fala).
- **Legenda de reserva:** quando a transcrição do trecho vem com menos de 40% das palavras da transcrição da hora (ex.: o Whisper só pegou a fala de um NPC), o `cortar.py` usa a transcrição da hora, distribuindo as palavras dentro do tempo de cada frase.
- **Revisão visual obrigatória funcionando na prática:** cortes cujo título promete algo que não aparece na gameplay (ex.: crocodilo que não aparece na tela) são rebaixados e substituídos pelo próximo candidato.

## 2026-11-21 — Câmera na proporção da webcam do OBS (16:9)

- A facecam no topo agora usa a mesma proporção da webcam do OBS (1280x720 = 16:9): painel 1080x608. A câmera entra inteira, sem cortar as laterais, o que também diminui a ampliação (mais nitidez).
- `esqueleto-tela.json` ganhou `camera.proporcao` ("16:9"); com ela, `cortar.py` calcula a altura do painel sozinho. Fade reduzido para 90 px para não cobrir o rosto; título centrado em y=608.
- Testes atualizados.
- Câmera inteira em todos os cortes: quando a detecção pega só um pedaço da webcam (rosto + parte do fundo), `cortar.py` troca pela caixa dominante da live (a que contém as outras detecções), evitando zoom extra e corte do topo da cabeça.
- A câmera inteira fica guardada por live em `lives/<id>/camera-live.json`: se numa hora a detecção só pega pedaços da webcam, as horas anteriores dizem onde está a câmera completa.
- Também troca pela câmera inteira quando a detecção vem maior que a webcam (pegando parte do jogo), se mais da metade dela estiver sobre a câmera conhecida.
- Live v2933814291 (9 h 17 min): 46 shorts em 9 pastas; hora 10 sem cortes (só cena e despedida). Trecho 5:00–5:36 sem cortes: outra pessoa jogando no lugar do streamer.

## 2026-11-21 — Entrega sem vídeo duplicado

- `entregar.py` agora põe os vídeos em `Shorts prontos para postar/` como hard link em vez de copiar: o arquivo aparece nas duas pastas mas ocupa o disco uma vez só (em outro disco, copia).
- Depois de entregar, apaga de `shorts/` as versões superadas (`-vN` antigas) e os cortes descartados na revisão. `--manter-tudo` desliga a limpeza.
- Reaplicado na live v2933814291: 69 arquivos antigos apagados e as cópias trocadas por links (cerca de 3,7 GB a menos no disco). Teste novo em `testes/test_projeto.py`.

## 2026-11-23 — Revisão geral: velocidade, chat, prévia e repositório

- **Repositório git:** `.gitignore` deixa de fora `lives/`, `Shorts prontos para postar/` e `desempenho/` (grandes e pessoais); `.gitattributes` normaliza fim de linha. `LEIA-ME.md` virou `README.md` (página do GitHub), reescrito sem as informações velhas ("fade não implementado").
- **Chat da Twitch:** o yt-dlp não baixa mais o replay (a live v2936842493 teve 0 mensagens). O `ouvir.py` agora usa o TwitchDownloaderCLI quando instalado, lê o JSON dele (`comments[].content_offset_seconds`) e aceita `--chat arquivo.json` para um chat baixado à mão.
- **Trava de download:** `comum.Trava` impede duas horas rodando juntas de baixar o mesmo áudio/chat ou recalcular o volume ao mesmo tempo (a segunda espera; trava esquecida por processo morto expira).
- **Whisper uma vez só:** o `ouvir.py` grava o tempo de cada palavra (`transcricao.json` versão 3) e o `cortar.py` usa essas palavras na legenda em vez de transcrever cada trecho de novo. Transcrições antigas, ou `--whisper-trecho`, mantêm o comportamento anterior.
- **Whisper `large-v3-turbo` como padrão** (antes `small` no Windows). Teste em 3 min da live: o turbo acertou "Tabela periódica" e "caranguejo", que o small errou; roda ~6x mais rápido que o tempo real no Ryzen 7 5800XT. `CORTES_MODELO=small` volta ao anterior.
- **Shorts mais curtos:** `conferir.py` passa a usar o padrão da regra por hora (`--manter 10 --nota-minima 65`), teto de 60 s (antes 75) e aviso acima de 45 s. Os cortes da hora 1 da última live tinham 51–73 s. `como-escolher.md` pede 25–45 s com gancho nos 2 primeiros segundos.
- **Prévia antes do render:** `cortar.py --previa` baixa os trechos e monta `trechos/NN-previa.jpg` (6 quadros com o horário da live) sem renderizar, para descartar momentos cuja ação não aparece antes de gastar o render.
- **Placa de vídeo:** `cortar.py --gpu` (ou `"gpu": true` no estilo) codifica com AMD AMF / NVIDIA NVENC / Intel QSV, testando antes se o encoder funciona. Na RX 9070 XT: encode ~2,5x mais rápido que o `libx264 slow`, SSIM 0,995 contra 0,997. O modo CQP da AMF travou no teste e não é usado. A lista de encoders do FFmpeg é lida uma vez por execução.
- **`pipeline.py`:** `ouvir` transcreve as horas em sequência num processo só (em segundo plano), com andamento em `lives/<id>/fila.json`; `status` mostra uma linha por hora com o próximo passo.
- **`limpar.py`:** lista (e com `--apagar` apaga) os `trechos/` de horas entregues há N dias e, com `--audio`, o áudio das lives totalmente entregues. Nunca toca em shorts, transcrições ou gravação original. Na live v2936842493: 2,15 GB liberáveis.
- **`desempenho.py`:** cruza um JSON de posts do Metricool com os shorts entregues (por título) e escreve `desempenho/relatorio.md` por tipo e duração. O `entregar.py` agora guarda título, tipo, duração e nota de cada short no `entrega.json`; entregas antigas são lidas pelo `cortes.json`.
- **`mediana_que_anda`** (volume e chat) com janelas deslizantes do NumPy: mesmo resultado do laço, bem mais rápida.
- **Testes:** 18 passando (9 novos: chat, trava, mediana, palavras gravadas, padrões do conferir, limpar, desempenho, status, encoder).

## 2026-11-24 — Entrega organizada: uma pasta legível por live

- **Problema:** `Shorts prontos para postar/` tinha pastas com o ID da live (`v2938905930`, `cTh8ABhVRIw`), uma subpasta por hora e seis pastas `hora-N` soltas de uma entrega antiga. Não dava para achar os cortes.
- **`entregar.py`:** cada live agora tem uma pasta só, `AAAA-MM-DD - Site - live de XhYY (id)`, com os vídeos soltos e nomeados `Hora N - NN - Título.mp4` (o título de verdade, com acento), os `.txt` em `textos/` e um `LEIA-ME.txt` da live inteira. O nome da pasta fica em `lives/<id>/pasta-entrega.txt`. O `entrega.json` passou a guardar legenda, hashtags e motivo.
- **Migração:** os 185 shorts já entregues (5 lives) foram movidos, sem re-renderizar nem trocar versão, para a estrutura nova. O que sobrou da estrutura antiga (incluindo 30 cópias velhas da entrega de 20/11) foi para `_estrutura antiga (pode apagar)/`.
- Teste novo: 20 testes passando.
