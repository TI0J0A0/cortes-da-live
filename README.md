# Cortes de live gamer 🎮

Skill para o Claude Code que transforma lives da Twitch, YouTube e Kick (ou gravações originais do OBS) em **vários Shorts 9:16**: facecam em cima, gameplay embaixo, título, legenda palavra por palavra e card final "Venha assistir ao vivo".

**Regra do projeto:** cerca de **10 cortes por hora de live**, de **25 a 45 s**, na melhor qualidade possível, processados **hora por hora** e entregues em `Shorts prontos para postar/`, uma pasta por live (`2026-11-24 - Twitch - live de 4h29 (id)/Hora 1 - 01 - Título.mp4`), assim que cada hora fica pronta, enquanto a próxima já está sendo transcrita. O fluxo completo está em [SKILL.md](SKILL.md) e os critérios editoriais em [referencias/como-escolher.md](referencias/como-escolher.md).

## Como funciona

```text
pipeline.py ouvir ──► hora-N/ transcrição (palavra por palavra), volume, chat, janelas/
        Claude lê as janelas ──► momentos.json
conferir.py ──► momentos-conferidos.json (até 10, nota ≥ 65, 12–60 s, sem sobreposição)
cortar.py --previa ──► trechos/NN-previa.jpg (confere a ação antes do render)
cortar.py ──► shorts/NN-titulo.mp4 + .txt + -conferir.jpg
entregar.py ──► Shorts prontos para postar/<data - site - duração (id)>/Hora N - NN - Título.mp4
```

| Ferramenta | O que faz |
|---|---|
| `preparar.py` | instala tudo em `~/.cortes-de-live` (yt-dlp, FFmpeg, OpenCV, Whisper, fontes) |
| `pipeline.py` | `ouvir`: transcreve as horas em sequência, em segundo plano. `status`: em que pé está cada hora |
| `ouvir.py` | baixa áudio e chat uma vez, transcreve uma hora, mede volume e picos do chat |
| `conferir.py` | encaixa os momentos nas frases e escolhe os melhores sem sobreposição |
| `cortar.py` | baixa os trechos, acha a facecam, monta e codifica os Shorts (`--previa`, `--gpu`) |
| `entregar.py` | põe a versão final de cada short na pasta de entrega (hard link, sem duplicar no disco) |
| `limpar.py` | libera espaço apagando trechos de horas já entregues (só lista sem `--apagar`) |
| `desempenho.py` | cruza as métricas do Metricool com os shorts entregues (por tipo e duração) |
| `esqueleto.py` | desenha a tela padrão (wireframe ou sobre um quadro real) |
| `achar.py` | procura lives gravadas de um assunto no YouTube |

## Instalação

1. Clone este repositório numa pasta de trabalho com espaço livre (as lives ocupam alguns GB).
2. Rode o instalador uma vez:

```powershell
python ferramentas\preparar.py
```

3. Opcional, para o **chat da Twitch**: instale o [TwitchDownloaderCLI](https://github.com/lay295/TwitchDownloader) e deixe o `TwitchDownloaderCLI.exe` no PATH ou em `%USERPROFILE%\.cortes-de-live\`. O yt-dlp não baixa mais o chat da Twitch; sem essa ferramenta a análise usa só fala e volume.

Depois, no Claude Code, é só pedir: *"Faça os cortes desta live: https://www.twitch.tv/videos/..."*.

## Uso manual (PowerShell)

```powershell
python ferramentas\pipeline.py ouvir "https://www.twitch.tv/videos/123" --lingua pt
python ferramentas\pipeline.py status "lives\v123"
python ferramentas\conferir.py "lives\v123\hora-1"
python ferramentas\cortar.py "lives\v123\hora-1" --previa
python ferramentas\cortar.py "lives\v123\hora-1"
python ferramentas\entregar.py "lives\v123\hora-1"
```

O `momentos.json` de cada hora é escrito pelo Claude depois de ler `resumo.md` e as `janelas/`; o `conferir.py` não funciona sem ele.

## Desempenho e qualidade

- **Whisper `large-v3-turbo`** por padrão: bem mais preciso em PT-BR com gíria de jogo e ~6x mais rápido que o tempo real no processador (1 h de live em ~10 min). `--modelo small` ou `CORTES_MODELO=small` para mais velocidade.
- A transcrição já guarda o tempo de **cada palavra**: o `cortar.py` não roda o Whisper de novo para a legenda.
- **`--gpu`** no `cortar.py` codifica na placa (AMD AMF, NVIDIA NVENC ou Intel QSV): ~2,5x mais rápido no encode, com qualidade um pouco menor que o padrão (`libx264 crf 16 slow`).
- A facecam embutida num VOD 1080p tem poucos pixels; **nenhum encoder recria detalhe que não existe**. Para câmera nítida, grave a live localmente no OBS e use o arquivo original.

## O que não vai para o git

`lives/`, `Shorts prontos para postar/` e `desempenho/` ficam fora do repositório (`.gitignore`): são grandes e trazem dados das suas lives.

## Testes

```powershell
& "$HOME\.cortes-de-live\ambiente\Scripts\python.exe" -m unittest discover -s testes -v
```

## Limites

O projeto escolhe momentos com transcrição, volume e chat; **não interpreta a gameplay sozinho**. Termos como `GAME?boss` são pistas da fala. A prévia (`--previa`) e as folhas `-conferir.jpg` existem para o Claude conferir a imagem antes de entregar. VODs ainda ao vivo não são suportados.

Histórico de mudanças: [ALTERACOES.md](ALTERACOES.md).
