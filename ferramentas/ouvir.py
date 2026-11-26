#!/usr/bin/env python3
"""Ouve uma live inteira no seu computador e deixa tudo pronto para escolher os momentos.

Uso:
  python3 ouvir.py <link da live> [--pasta lives] [--lingua pt] [--cookies chrome] [--sem-chat]

O que faz:
  1. Baixa só o áudio (uma live de 4 horas vira umas centenas de MB, não um vídeo gigante).
  2. Transcreve a live inteira com o Whisper, aqui no computador.
  3. Mede o volume segundo a segundo e marca onde o streamer ficou bem mais alto que o normal.
  4. Se a live tiver replay do chat, conta as mensagens e marca onde o chat disparou.

Escreve em <pasta>/<id da live>/:
  info.json          o título, o canal, a duração, o link
  transcricao.json   cada frase com o segundo em que começa e termina
  sinais.json        o volume, os gritos e os picos do chat
  janelas/           a transcrição em janelas de 12 minutos, com ALTO nos gritos e CHAT nos picos do chat
  resumo.md          os números da live e os maiores picos
  tempos.json        quanto tempo cada passo levou
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comum  # noqa: E402

comum.no_ambiente()
import numpy as np  # noqa: E402

BLOCO = 600   # seconds of audio handed to Whisper at a time
FOLGA = 20    # the cut between two blocks falls on the quietest half second inside this stretch

# Só pistas textuais. O vídeo precisa confirmar se houve a jogada ou o susto.
PISTAS_GAMER = {
    "boss": r"\b(boss|chef[aã]o|chefe final|fase final|segunda fase|terceira fase)\b",
    "jogada": r"\b(clutch|ace|headshot|quadra kill|pentakill|eliminei|matei|derrubei|fiz a play)\b",
    "susto": r"\b(susto|jumpscare|me assustou|que medo|que desespero|corre|foge)\b",
    "erro": r"\b(morri|morreu|perdi|bugou|bug|travou|cai|ca[ií]mos|falhei)\b",
    "descoberta": r"\b(segredo|descobri|achei|escondido|passagem|olha isso|n[aã]o sabia)\b",
    "reacao": r"(n[aã]o acredito|que isso|meu deus|caraca|absurdo|imposs[ií]vel|ganhei|venci|consegui)",
}


def sinais_gamer(fala):
    return [nome for nome, padrao in PISTAS_GAMER.items() if re.search(padrao, fala, flags=re.I)]


def baixar_info(link, pasta, cookies, canal=""):
    origem = Path(link).expanduser()
    if origem.is_file():
        origem = origem.resolve()
        p = subprocess.run([comum.ffmpeg(), "-hide_banner", "-i", str(origem)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", p.stderr)
        if not m:
            sys.exit("Não consegui ler a duração do arquivo local (vídeo ou áudio inválido).")
        duracao = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        codigo = hashlib.sha1(str(origem).encode("utf-8")).hexdigest()[:12]
        info = {"id": "local_" + codigo, "titulo": origem.stem, "canal": canal or "Arquivo local",
                "duracao": duracao, "link": str(origem), "site": "Local", "lingua": None,
                "ao_vivo": "not_live", "arquivo_local": str(origem)}
        destino = Path(pasta) / info["id"]
        destino.mkdir(parents=True, exist_ok=True)
        comum.escrever_json(destino / "info.json", info)
        return info, destino
    r = comum.ytdlp("-J", "--skip-download", link, cookies=cookies)
    if r.returncode:
        sys.exit("Não consegui ler a live:\n" + r.stderr[-1200:] +
                 "\nSe o site pede login ou a live tem restrição de idade, rode de novo com --cookies chrome")
    d = json.loads(r.stdout)
    info = {"id": d.get("id"), "titulo": d.get("title"), "canal": d.get("channel") or d.get("uploader"),
            "duracao": d.get("duration"), "link": d.get("webpage_url") or link, "site": d.get("extractor_key"),
            "lingua": (d.get("language") or "")[:2] or None, "visualizacoes": d.get("view_count"),
            "ao_vivo": d.get("live_status")}
    if canal:
        info["canal"] = canal
    if info["ao_vivo"] == "is_live":
        sys.exit("Essa live ainda está no ar. Espere ela terminar e o replay aparecer.")
    destino = Path(pasta) / re.sub(r"[^A-Za-z0-9_-]", "_", str(info["id"]))
    destino.mkdir(parents=True, exist_ok=True)
    comum.escrever_json(destino / "info.json", info)
    return info, destino


def audio_pronto(destino):
    return [p for p in destino.glob("audio.*") if p.suffix not in (".part", ".ytdl") and not p.name.endswith(".temp.mp4")]


def baixar_audio(info, destino, cookies):
    if info.get("arquivo_local"):
        return Path(info["arquivo_local"]), False  # arquivo original, sem download nem compressão
    # duas horas rodando juntas não baixam o mesmo áudio duas vezes: a segunda espera a primeira terminar
    with comum.Trava(destino, "audio"):
        return _baixar_audio(info, destino, cookies)


def _baixar_audio(info, destino, cookies):
    pronto = audio_pronto(destino)
    if pronto:
        return pronto[0], False
    # never a "drc" format: it flattens the loud moments we are looking for.
    # a site with no audio-only format (Kick) gives its smallest video instead of its biggest
    r = comum.ytdlp("-f", "ba[abr<=70][format_id!*=drc][protocol^=http]/ba[format_id!*=drc][protocol^=http]/ba[format_id!*=drc]/ba/w",
                    "-o", str(destino / "audio.%(ext)s"), info["link"], cookies=cookies)
    pronto = audio_pronto(destino)
    if r.returncode or not pronto:
        sys.exit("Não consegui baixar o áudio:\n" + r.stderr[-1200:])
    return pronto[0], True


def twitch_downloader():
    """O TwitchDownloaderCLI (github.com/lay295/TwitchDownloader), se a pessoa instalou: no PATH ou em ~/.cortes-de-live."""
    for nome in ("TwitchDownloaderCLI", "TwitchDownloaderCLI.exe"):
        achado = shutil.which(nome) or (str(comum.CASA / nome) if (comum.CASA / nome).is_file() else None)
        if achado:
            return achado
    return None


def tem_chat(destino):
    return any(p.suffix == ".json" and p.name != "chat-contagem.json" for p in destino.glob("chat*"))


def baixar_chat(info, destino, cookies, limite):
    """YouTube guarda o replay do chat (o yt-dlp baixa). Na Twitch o yt-dlp não baixa mais o chat: usa o
    TwitchDownloaderCLI quando ele está instalado. Melhor esforço: nunca para a análise."""
    with comum.Trava(destino, "chat", espera=limite + 60):
        if tem_chat(destino):
            return  # already here from an earlier run (or from the other hour running at the same time)
        if info.get("site") == "TwitchVod":
            exe = twitch_downloader()
            if not exe:
                print("    chat da Twitch: instale o TwitchDownloaderCLI (veja README.md) ou passe --chat arquivo.json", flush=True)
                return
            vid = re.sub(r"\D", "", str(info.get("id") or ""))
            try:
                subprocess.run([exe, "chatdownload", "--id", vid, "-o", str(destino / "chat-twitch.json"), "--banner", "false"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=limite)
            except (subprocess.TimeoutExpired, OSError) as e:
                print("    chat da Twitch não veio (%s)" % e, flush=True)
            return
        comum.ytdlp("--skip-download", "--write-subs", "--sub-langs", "live_chat", "-o", str(destino / "chat"),
                    info["link"], cookies=cookies, tempo=limite)


def importar_chat(arquivo, destino):
    """--chat: um replay do chat baixado à mão (TwitchDownloader, chat do YouTube do yt-dlp) vai para a pasta da live."""
    origem = Path(arquivo).expanduser()
    if not origem.is_file():
        sys.exit("Arquivo de chat não encontrado: %s" % origem)
    alvo = destino / ("chat-importado" + "".join(origem.suffixes[-2:] or [".json"]))
    if origem.resolve() != alvo.resolve():
        shutil.copy2(origem, alvo)


def tempos_do_chat(destino):
    """Seconds into the stream of every chat message, from whatever chat file yt-dlp left."""
    tempos = []
    for arq in sorted(destino.glob("chat*")):
        if arq.suffix == ".md" or arq.name == "chat-contagem.json":
            continue
        try:
            texto = arq.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        tempos_json = tempos_de_json(texto)
        if tempos_json is not None:  # Twitch (TwitchDownloader ou rechat antigo): um JSON só
            tempos.extend(tempos_json)
            continue
        for linha in texto.splitlines():  # YouTube: one JSON per line
            m = re.search(r'"videoOffsetTimeMsec":\s*"?(-?\d+)', linha)
            if m and int(m.group(1)) >= 0 and '"addChatItemAction"' in linha:
                tempos.append(int(m.group(1)) / 1000.0)
    return sorted(tempos)


def tempos_de_json(texto):
    """Segundos de cada mensagem num chat em JSON único: TwitchDownloader ({"comments": [...]}) ou a lista do rechat.
    None quando o texto não é um JSON desses (ex.: o chat do YouTube, um JSON por linha)."""
    try:
        dado = json.loads(texto)
    except Exception:
        return None
    lista = dado.get("comments") if isinstance(dado, dict) else dado
    if not isinstance(lista, list):
        return None
    out = []
    for m in lista:
        if isinstance(m, dict) and m.get("content_offset_seconds") is not None:
            out.append(float(m["content_offset_seconds"]))
    return out


def volume_por_segundo(arq, faixa=None):
    """The level of every second of the stream, in dB, counted on the stream's own clock (no second is skipped)."""
    niveis, resto = [], np.zeros(0, dtype=np.int16)
    for pedaco in comum.audio_em_blocos(arq, bloco=comum.TAXA * 60, faixa=faixa):
        junto = np.concatenate([resto, pedaco])
        n = len(junto) // comum.TAXA * comum.TAXA
        if n:
            x = junto[:n].astype(np.float32) / 32768.0
            rms = np.sqrt((x.reshape(-1, comum.TAXA) ** 2).mean(axis=1) + 1e-10)
            niveis.extend((20 * np.log10(rms)).round(1).tolist())
        resto = junto[n:]
    if len(resto) >= comum.TAXA // 2:
        x = resto.astype(np.float32) / 32768.0
        niveis.append(round(float(20 * np.log10(np.sqrt((x ** 2).mean() + 1e-10))), 1))
    return niveis


def volume_da_live(arq, raiz, faixa=None):
    """O volume de cada segundo da live inteira, guardado em lives/<id>/volume.json para as outras horas."""
    cache = raiz / "volume.json"
    with comum.Trava(raiz, "volume"):
        dado = comum.ler_json(cache)
        if dado and dado.get("audio") == arq.name and dado.get("tamanho") == arq.stat().st_size:
            return dado["volume"]
        niveis = volume_por_segundo(arq, faixa)
        comum.escrever_json(cache, {"audio": arq.name, "tamanho": arq.stat().st_size, "volume": niveis})
        return niveis


def mediana_que_anda(x, meia, bloco=4096):
    """Mediana de cada ponto com `meia` vizinhos de cada lado (nas pontas, só os que existem).
    Janelas deslizantes do NumPy em blocos: o mesmo resultado do laço simples, dezenas de vezes mais rápido."""
    x = np.asarray(x, dtype=float)
    n, w = len(x), 2 * meia + 1
    out = np.zeros(n)
    if n < w:
        for i in range(n):
            out[i] = np.median(x[max(0, i - meia): i + meia + 1])
        return out
    janelas = np.lib.stride_tricks.sliding_window_view(x, w)  # janela k = x[k : k + w], centrada em k + meia
    for k in range(0, len(janelas), bloco):
        out[meia + k: meia + k + len(janelas[k:k + bloco])] = np.median(janelas[k:k + bloco], axis=1)
    for i in list(range(meia)) + list(range(n - meia, n)):
        out[i] = np.median(x[max(0, i - meia): i + meia + 1])
    return out


def juntar(marcas, vao, minimo):
    """Indexes that are on -> list of (first, last), joining gaps up to vao and dropping runs shorter than minimo."""
    eventos = []
    for i in np.flatnonzero(marcas):
        if eventos and i - eventos[-1][1] <= vao:
            eventos[-1][1] = i
        else:
            eventos.append([i, i])
    return [(a, b) for a, b in eventos if b - a + 1 >= minimo]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("link", help="URL do VOD ou caminho para gravação original (.mp4/.mkv/.mov)")
    ap.add_argument("--pasta", default="lives")
    ap.add_argument("--canal", default="", help="nome do streamer; útil para arquivos locais")
    ap.add_argument("--lingua", default="", help="pt, en, es... (vazio = a da live, ou descobre sozinho)")
    ap.add_argument("--cookies", default="", help="navegador de onde ler o login: chrome, safari, firefox")
    ap.add_argument("--sem-chat", action="store_true")
    ap.add_argument("--chat", default="", help="arquivo de replay do chat baixado à mão (ex.: JSON do TwitchDownloader)")
    ap.add_argument("--tempo-chat", type=int, default=900, help="segundos no máximo esperando o replay do chat")
    ap.add_argument("--janela", type=int, default=12, help="minutos por janela de transcrição")
    ap.add_argument("--modelo", default="", help="modelo do Whisper (vazio = o melhor para este computador)")
    ap.add_argument("--hora", type=int, default=0,
                    help="processa só a hora N da live (1, 2, 3...) em lives/<id>/hora-N/; áudio e chat são baixados uma vez")
    ap.add_argument("--duracao-hora", type=int, default=3600, help="segundos de cada bloco no modo --hora")
    ap.add_argument("--sobra", type=int, default=60, help="segundos lidos além do fim da hora, só para fechar contexto")
    ap.add_argument("--faixa-voz", type=int, default=-1,
                    help="gravação do OBS com várias faixas: número da faixa só do microfone (0, 1, 2...). "
                         "Assim a transcrição e a legenda nunca pegam o áudio do jogo")
    a = ap.parse_args()

    info, raiz = baixar_info(a.link, a.pasta, a.cookies, a.canal)
    if a.faixa_voz >= 0:
        if not info.get("arquivo_local"):
            sys.exit("--faixa-voz só funciona com a gravação original do OBS (arquivo local com várias faixas de áudio).")
        info["faixa_voz"] = a.faixa_voz
        comum.escrever_json(raiz / "info.json", info)
    print("Live: %s | %s | %s" % (info["canal"], info["titulo"], comum.duracao_falada(info["duracao"] or 0)))
    if info.get("duracao"):
        print("Horas na live: %d (use --hora 1, --hora 2, ...)" % int(np.ceil(info["duracao"] / float(a.duracao_hora))))

    fio = None
    if a.chat:
        importar_chat(a.chat, raiz)
    if not a.sem_chat and (a.chat or not info.get("arquivo_local")):
        fio = threading.Thread(target=baixar_chat, args=(info, raiz, a.cookies, a.tempo_chat), daemon=True)
        fio.start()

    tempos_raiz = comum.Tempos(raiz)
    tempos_raiz.comeca("baixar_audio")
    arq, novo = baixar_audio(info, raiz, a.cookies)
    baixou = tempos_raiz.termina() if novo else 0.0
    # modo por hora: só o trecho [ini, fim + sobra) é transcrito; os tempos continuam sendo os da live inteira
    ini_h, fim_h, destino = 0.0, None, raiz
    if a.hora:
        ini_h = (a.hora - 1) * float(a.duracao_hora)
        if info.get("duracao") and ini_h >= info["duracao"]:
            sys.exit("A live tem só %d hora(s)." % int(np.ceil(info["duracao"] / float(a.duracao_hora))))
        fim_h = ini_h + a.duracao_hora
        destino = raiz / ("hora-%d" % a.hora)
        destino.mkdir(exist_ok=True)
        comum.escrever_json(destino / "info.json", dict(info, hora=a.hora, hora_inicio=ini_h, hora_fim=fim_h,
                                                       pasta_live=str(raiz.resolve()), arquivo_audio=str(arq.resolve())))
    tempos = comum.Tempos(destino)
    if novo:
        tempos.dado["baixar_audio"] = baixou
        print("1/4 áudio baixado: %.0f MB em %s" % (arq.stat().st_size / 1e6, comum.duracao_falada(baixou)))
    else:
        print("1/4 %s: %.0f MB" % ("arquivo local (original, sem download)" if info.get("arquivo_local") else "áudio já estava aqui", arq.stat().st_size / 1e6))

    # 2 and 3: one pass over the audio, block by block: the volume of every second and the transcript
    tempos.comeca("ouvir")
    feito = comum.ler_json(destino / "transcricao.json")
    if feito and feito.get("completa") and feito.get("hora", 0) != a.hora:
        feito = None  # transcrição de outro recorte da live
    if feito and feito.get("completa"):
        segs, lingua = feito["frases"], feito["lingua"]
        if feito.get("versao", 0) < 2:  # an older run counted the seconds per block and drifted
            feito.update({"volume": volume_da_live(arq, raiz, info.get("faixa_voz")), "versao": 2})
            comum.escrever_json(destino / "transcricao.json", feito)
        volume = np.array(feito["volume"])
        levou = tempos.dado.get("ouvir", 0)  # a second run keeps the time the real listening took
    else:
        segs = []
        lingua = a.lingua or info.get("lingua") or None
        total = info["duracao"] or 0
        fila = np.zeros(0, dtype=np.int16)
        andado = 0  # samples already handed to Whisper
        if a.hora:
            total = min(total, fim_h + a.sobra) if total else fim_h + a.sobra
            fonte = comum.audio_em_blocos(arq, inicio=ini_h, duracao=fim_h + a.sobra - ini_h, faixa=info.get("faixa_voz"))
            print("    hora %d: transcrevendo %s a %s" % (a.hora, comum.relogio(ini_h), comum.relogio(total)), flush=True)
        else:
            fonte = comum.audio_em_blocos(arq, faixa=info.get("faixa_voz"))
        acabou = False
        while not acabou or len(fila):
            while not acabou and len(fila) < (BLOCO + FOLGA) * comum.TAXA:
                try:
                    fila = np.concatenate([fila, next(fonte)])
                except StopIteration:
                    acabou = True
            if len(fila) >= (BLOCO + FOLGA) * comum.TAXA:
                trecho = fila[BLOCO * comum.TAXA:(BLOCO + FOLGA) * comum.TAXA].astype(np.float32)
                meio = comum.TAXA // 2
                energia = (trecho[: len(trecho) // meio * meio].reshape(-1, meio) ** 2).mean(axis=1)
                corte = BLOCO * comum.TAXA + int(np.argmin(energia)) * meio + meio // 2
            else:
                corte = len(fila)
            pedaco, fila = fila[:corte], fila[corte:]
            if not len(pedaco):
                break
            base = ini_h + andado / comum.TAXA
            # palavra por palavra já aqui: o cortar.py usa estes tempos na legenda e não roda o Whisper de novo
            achados, lingua_achada = comum.transcrever(pedaco, lingua=lingua, palavras=True, modelo=a.modelo or None)
            lingua = lingua or lingua_achada
            for s in achados:
                if s["t"]:
                    segs.append({"s": round(base + s["s"], 2), "e": round(base + s["e"], 2), "t": s["t"],
                                 "p": [{"w": w["w"], "s": round(base + w["s"], 2), "e": round(base + w["e"], 2)}
                                       for w in s.get("p", []) if w["w"]]})
            andado += len(pedaco)
            print("    ouvido até %s%s" % (comum.relogio(ini_h + andado / comum.TAXA), " de " + comum.relogio(total) if total else ""), flush=True)
        niveis = volume_da_live(arq, raiz, info.get("faixa_voz"))
        volume = np.array(niveis)
        comum.escrever_json(destino / "transcricao.json", {"completa": True, "versao": 3, "palavras": True, "lingua": lingua,
                                                           "modelo": a.modelo or comum.modelo_padrao(), "frases": segs,
                                                           "volume": niveis, "hora": a.hora, "inicio": ini_h, "fim": fim_h})
        levou = tempos.termina()
    # o trecho analisado: a live inteira, ou a hora pedida + a sobra
    fim_r = min(len(volume), (fim_h + a.sobra) if fim_h else len(volume))
    horas = (fim_r - ini_h) / 3600.0
    print("2/4 %s ouvida: %s de áudio, %d frases, em %s" % ("hora %d" % a.hora if a.hora else "live", comum.duracao_falada(fim_r - ini_h), len(segs), comum.duracao_falada(levou)))

    # 3: where the streamer got much louder than the minutes around
    base = mediana_que_anda(volume, 150)
    sobra = volume - base
    falado = volume > np.percentile(volume, 40)
    limite = max(6.0, float(np.percentile(sobra[falado], 97))) if falado.any() else 6.0
    gritos = [{"s": int(a_), "e": int(b_) + 1, "db": round(float(sobra[a_:b_ + 1].max()), 1)}
              for a_, b_ in juntar((sobra >= limite) & falado, 2, 1)]
    gritos = [g for g in gritos if g["e"] >= ini_h and g["s"] < fim_r]
    print("3/4 volume medido: %d momentos bem acima do normal (%.1f dB ou mais)" % (len(gritos), limite))

    # 4: where the chat suddenly ran much faster than the minutes around
    picos, mensagens = [], 0
    if fio is not None:
        fio.join(timeout=a.tempo_chat + 30)
        marcas = tempos_do_chat(raiz)
        mensagens = len(marcas)
        if mensagens >= 200:
            caixas = np.bincount((np.array(marcas) // 10).astype(int), minlength=int(len(volume) // 10) + 1).astype(float)
            normal = np.maximum(mediana_que_anda(caixas, 15), 1.0)
            vezes = caixas / normal
            coberto = int(max(marcas) // 10)
            minimo = max(5.0, float(np.percentile(caixas[: coberto + 1], 90)))
            caixas[0] = 0  # everything typed before the stream began lands on second zero
            for a_, b_ in juntar((vezes >= 2.5) & (caixas >= minimo), 1, 1):
                picos.append({"s": int(a_) * 10, "e": (int(b_) + 1) * 10, "vezes": round(float(vezes[a_:b_ + 1].max()), 1),
                              "mensagens": int(caixas[a_:b_ + 1].sum())})
            picos = [c for c in picos if c["e"] >= ini_h and c["s"] < fim_r]
            comum.escrever_json(raiz / "chat-contagem.json", {"mensagens": mensagens, "ate": round(max(marcas)), "por_10s": caixas.astype(int).tolist()})
            print("4/4 chat lido: %d mensagens até %s, %d picos" % (mensagens, comum.relogio(max(marcas)), len(picos)))
        else:
            print("4/4 essa live não tem replay do chat (ou ele não veio): sigo com a transcrição e o volume")
    else:
        print("4/4 chat pulado")

    comum.escrever_json(destino / "sinais.json", {"gritos": gritos, "chat": picos, "limite_db": round(limite, 1), "mensagens": mensagens})

    # Pistas de acontecimentos em jogos: não substituem a revisão visual.
    pistas = [{"s": s["s"], "tipo": tipo, "texto": s["t"][:160]}
              for s in segs for tipo in sinais_gamer(s["t"])]
    comum.escrever_json(destino / "pistas-gamer.json", {"pistas": pistas})

    # the transcript in windows, with the marks on the lines
    def marca(s, e, fala=""):
        m = ""
        g = [x for x in gritos if x["s"] <= e and x["e"] >= s]
        if g:
            m += "ALTO+%.0fdB " % max(x["db"] for x in g)
        c = [x for x in picos if x["s"] <= e + 15 and x["e"] >= s]
        if c:
            m += "CHAT x%.1f " % max(x["vezes"] for x in c)
        tipos = sinais_gamer(fala)
        if tipos:
            m += "GAME?%s " % ",".join(tipos[:2])
        return m + "| " if m else ""

    pasta_j = destino / "janelas"
    pasta_j.mkdir(exist_ok=True)
    for velho in pasta_j.glob("janela-*.md"):
        velho.unlink()
    passo = a.janela * 60
    n = int(np.ceil((fim_r - ini_h) / passo)) or 1
    for i in range(n):
        ini, fim = ini_h + i * passo, min(ini_h + (i + 1) * passo, fim_r)
        linhas = ["# Janela %d de %d: %s a %s" % (i + 1, n, comum.relogio(ini), comum.relogio(fim)),
                  "%s | %s" % (info["canal"], info["titulo"]), "",
                  "ALTO = volume acima do normal; CHAT = pico de mensagens; GAME? = pista da FALA, confirme no vídeo.", ""]
        for s in segs:
            if ini <= s["s"] < fim:
                if fim_h and s["s"] >= fim_h and not any(x.startswith("--- SOBRA") for x in linhas):
                    linhas.append("--- SOBRA: daqui em diante já é a hora seguinte; só para fechar contexto, NÃO comece cortes aqui ---")
                linhas.append("[%s] %s%s" % (comum.relogio(s["s"]), marca(s["s"], s["e"], s["t"]), s["t"]))
        (pasta_j / ("janela-%02d.md" % (i + 1))).write_text("\n".join(linhas) + "\n", encoding="utf-8")

    def frase_em(t):
        perto = [s for s in segs if s["s"] - 4 <= t <= s["e"] + 4]
        return (perto[0]["t"] if perto else "")[:90]

    linhas = ["# %s" % info["titulo"], "", "- Canal: %s" % info["canal"], "- Link: %s" % info["link"],
              "- Duração: %s" % comum.duracao_falada(len(volume)),
              ("- Hora %d: %s a %s (alvo: cerca de 10 cortes, começando antes de %s)" % (
                  a.hora, comum.relogio(ini_h), comum.relogio(min(fim_h, len(volume))), comum.relogio(min(fim_h, len(volume))))
               if a.hora else "- Trecho: a live inteira"), "- Frases transcritas: %d" % len(segs),
              "- Momentos de volume alto: %d" % len(gritos),
              "- Chat: %s" % ("%d mensagens, %d picos" % (mensagens, len(picos)) if picos or mensagens >= 200 else "sem replay"),
              "- Janelas para ler: %d (pasta janelas/)" % n,
              "- Pistas gamer na fala: %d (pistas-gamer.json; não garantem acontecimentos visuais)" % len(pistas),
              "", "## Pistas gamer (verificar na gameplay)", ""]
    # Distribua pistas ao longo da live; evita 30 marcações consecutivas do mesmo acontecimento.
    vistos_pista = set()
    ordenadas = sorted(pistas, key=lambda x: x["s"])
    for pis in ordenadas:
        chave = (pis["tipo"], int(pis["s"] // 18))
        if chave in vistos_pista:
            continue
        vistos_pista.add(chave)
        linhas.append("- [%s] %s: %s" % (comum.relogio(pis["s"]), pis["tipo"], pis["texto"][:100]))
        if len(vistos_pista) >= 65:
            break
    linhas += ["", "## Os 25 maiores picos de volume", ""]
    for g in sorted(gritos, key=lambda x: -x["db"])[:25]:
        linhas.append("- [%s] +%.0f dB, %d s: %s" % (comum.relogio(g["s"]), g["db"], g["e"] - g["s"], frase_em(g["s"])))
    if picos:
        linhas += ["", "## Os 25 maiores picos do chat", ""]
        for c in sorted(picos, key=lambda x: -x["vezes"])[:25]:
            linhas.append("- [%s] %.1fx o normal, %d mensagens: %s" % (comum.relogio(c["s"]), c["vezes"], c["mensagens"], frase_em(c["s"] - 8)))
    (destino / "resumo.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print("\nPronto: %s" % destino)
    print("Agora leia resumo.md e cada arquivo de janelas/, e escreva momentos.json (veja referencias/como-escolher.md).")
    gasto = sum(v for k, v in tempos.dado.items() if k in ("baixar_audio", "ouvir"))
    print("Baixar e ouvir levou %s (%.0f vezes mais rápido que assistir)" % (comum.duracao_falada(gasto), horas * 3600 / max(1.0, gasto)))


if __name__ == "__main__":
    main()
