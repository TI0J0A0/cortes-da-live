#!/usr/bin/env python3
"""Faz os cortes prontos para postar: vertical, a câmera do streamer em cima, o jogo embaixo, o título e a legenda palavra por palavra.

Uso:
  python3 cortar.py <pasta da live> [--so 2] [--cookies chrome] [--camera x,y,l,a] [--modo facecam|cheia|sem]

Lê <pasta da live>/momentos-conferidos.json (do conferir.py) e, para cada momento marcado:
  1. Baixa só aquele trecho da live, não a live inteira.
  2. Acerta o trecho com o áudio da live, para o corte começar na palavra certa.
  3. Acha a câmera do streamer sozinho (o rosto que fica parado no mesmo lugar) e acompanha quando ele troca a tela no
     meio do momento.
  4. Transcreve o trecho palavra por palavra para a legenda.
  5. Monta o vídeo 1080x1920 e acerta o volume.

Escreve em <pasta da live>/shorts/:
  NN-titulo.mp4            o corte
  NN-titulo.txt            o título, a legenda do post, as hashtags e de onde veio
  NN-titulo-conferir.jpg   seis quadros do corte, para olhar antes de postar
  cortes.json              a lista

O modo comentário: grave a sua fala e salve em <pasta da live>/comentarios/ como NN-abre.m4a (toca antes do
corte) e NN-fecha.m4a (toca depois), com NN o número do momento. O corte sai como NN-titulo-comentado.mp4, com a sua
voz por cima da primeira e da última imagem do corte, paradas e escurecidas, e a sua fala legendada em outra cor.

O visual muda em <pasta da live>/estilo.json (as chaves estão em ESTILO, aqui embaixo).
Se a câmera sair errada, olhe trechos/NN-quadro.jpg e passe --camera x,y,largura,altura.
"""
import argparse
import os
import json
import re
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comum  # noqa: E402

comum.no_ambiente()
import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

try:
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
except Exception:
    pass

L, A, FPS = 1080, 1920, 30  # 30 fps rápido; use --fps 60 para jogos competitivos
MARGEM = 8  # seconds downloaded before and after each moment

ESTILO = {
    "cor_destaque": "#FFD60A",       # the word being said, the title box, the progress bar
    "cor_comentario": "#4ADE80",     # the word being said in the person's own comment
    "cor_legenda": "#FFFFFF",
    "cor_contorno": "#000000",
    "cor_titulo_texto": "#111111",
    "tamanho_legenda": 76,
    "tamanho_titulo": 48,
    "palavras_por_legenda": 3,
    "letras_por_legenda": 22,
    "altura_legenda": 0.82,          # a legenda fica sobre a gameplay, sem cobrir o rosto
    "layout": "gamer",              # gamer preserva facecam; classico estica a câmera até 1080 px
    "facecam_zoom_max": 1.65,       # nunca amplia a câmera mais que 65% por padrão
    "altura_painel_camera": 608,    # facecam em largura total no topo (crop proporcional, sem distorcer)
    "fade_camera": 160,             # px do gradiente vertical que une a facecam à gameplay (referencias/layout-facecam-fade.md)
    "titulo": True,
    "barra": True,
    "maiusculas": True,
    "volume": -14,                   # LUFS
    "crf": 16,                       # qualidade do H.264 (menor = melhor; 16 é quase sem perda visível)
    "preset": "slow",                # slow comprime melhor que veryfast na mesma qualidade
    "audio_kbps": 256,
    "nitidez_camera": 0.6,           # unsharp leve na facecam ampliada; 0 desliga
    "gpu": False,                    # true = codifica na placa de vídeo (igual a --gpu)
    "qualidade_amf": 45,             # AMD (QVBR): MAIOR = melhor, 1 a 51
    "qualidade_gpu": 18,             # NVIDIA (cq) / Intel (global_quality): MENOR = melhor
    "titulo_desloca": 0,             # px do centro do título em relação à emenda câmera/gameplay
    "altura_barra": 12,
    "cor_barra": "#FFD60A",
    # card final "Venha assistir ao vivo" (referencias/esqueleto-tela.json -> encerramento); false desliga
    "encerramento": {"ativo": False},
}

ESQUELETO = Path(__file__).resolve().parent.parent / "referencias" / "esqueleto-tela.json"


def carregar_esqueleto(caminho=ESQUELETO):
    """Lê referencias/esqueleto-tela.json (a tela padrão) e devolve as chaves de ESTILO que ele define."""
    e = comum.ler_json(caminho, {}) or {}
    if not e:
        return {}
    cam, fade, tit, leg, barra = (e.get(k, {}) for k in ("camera", "fade", "titulo", "legenda", "barra"))
    alto = float(e.get("tela", {}).get("altura", A))
    prop = str(cam.get("proporcao") or "")
    if ":" in prop:  # ex.: "16:9" = mesma proporção da webcam do OBS (1280x720), sem cortar as laterais
        pw, ph = (float(v) for v in prop.split(":", 1))
        largura = float(e.get("tela", {}).get("largura", L))
        cam = dict(cam, altura=int(round(largura * ph / pw / 2.0)) * 2)
    mapa = {
        "altura_painel_camera": cam.get("altura"),
        "fade_camera": fade.get("altura"),
        "titulo_desloca": (tit["centro_y"] - cam.get("altura", ESTILO["altura_painel_camera"])) if "centro_y" in tit else None,
        "tamanho_titulo": tit.get("tamanho_fonte"),
        "cor_titulo_texto": tit.get("cor_texto"),
        "cor_destaque": leg.get("cor_destaque") or tit.get("cor_fundo"),
        "tamanho_legenda": leg.get("tamanho_fonte"),
        "palavras_por_legenda": leg.get("palavras"),
        "altura_legenda": (leg["centro_y"] / alto) if "centro_y" in leg else None,
        "cor_legenda": leg.get("cor"),
        "cor_contorno": leg.get("cor_contorno"),
        "altura_barra": barra.get("altura"),
        "cor_barra": barra.get("cor"),
        "encerramento": ({k: v for k, v in e["encerramento"].items() if not k.startswith("_")}
                         if isinstance(e.get("encerramento"), dict) else None),
    }
    return {k: v for k, v in mapa.items() if v is not None}


ESTILO.update(carregar_esqueleto())


def encerramento(estilo, dur):
    """O card final já resolvido para um corte de `dur` segundos, ou None se estiver desligado/sem imagem.
    Em cortes curtos o encerramento encolhe para no máximo 40% do corte."""
    enc = estilo.get("encerramento")
    if not isinstance(enc, dict) or not enc.get("ativo", True):
        return None
    img = Path(enc.get("imagem", "encerramento-ao-vivo.png"))
    if not img.is_absolute():
        img = ESQUELETO.parent / img
    if not img.exists():
        print("    aviso: imagem do encerramento não encontrada (%s); corte sai sem o card." % img, flush=True)
        return None
    seg = min(float(enc.get("segundos", 5)), dur * 0.4)
    if seg < 1.0:
        return None
    return {"imagem": img, "seg": seg, "inicio": dur - seg, "largura": int(enc.get("largura", 810)),
            "centro_y": int(enc.get("centro_y", 975)), "blur": float(enc.get("blur", 18)),
            "escurecer": float(enc.get("escurecer", 0.85)), "entrada": max(0.05, float(enc.get("entrada", 0.6))),
            "zoom_de": float(enc.get("zoom_de", 0.85)), "fade_saida": min(seg, max(0.0, float(enc.get("fade_saida", 0.6))))}


_CARDS = {}


def card_rgba(enc):
    """O card na largura final (RGBA, com a transparência original)."""
    chave = (str(enc["imagem"]), enc["largura"])
    if chave not in _CARDS:
        im = Image.open(enc["imagem"]).convert("RGBA")
        alt = int(round(im.height * enc["largura"] / float(im.width)))
        _CARDS[chave] = np.array(im.resize((enc["largura"], alt), Image.LANCZOS))
    return _CARDS[chave]


def aplicar_encerramento(tela, p, enc):
    """Um quadro do encerramento, p segundos depois do começo: desfoque entrando, card com fade + zoom leve."""
    a = suave(p / 0.4)
    pequeno = cv2.resize(tela, (L // 4, A // 4), interpolation=cv2.INTER_AREA)
    borrado = cv2.resize(cv2.GaussianBlur(pequeno, (0, 0), enc["blur"] / 4.0), (L, A), interpolation=cv2.INTER_LINEAR)
    tela = (tela * (1 - a) + borrado * (enc["escurecer"] * a)).astype(np.uint8)
    e = suave(p / enc["entrada"])
    card = card_rgba(enc)
    z = enc["zoom_de"] + (1 - enc["zoom_de"]) * e
    if z < 0.999:
        card = cv2.resize(card, (max(2, int(card.shape[1] * z)), max(2, int(card.shape[0] * z))), interpolation=cv2.INTER_AREA)
    colar(tela, card, L / 2, enc["centro_y"], opacidade=e)
    return tela


def suave(p):
    """Ease-out cúbico de 0 a 1: rápido no começo, assenta devagar."""
    p = min(1.0, max(0.0, p))
    return 1 - (1 - p) ** 3

FONTES = [str(comum.MODELOS / "Anton-Regular.ttf"), "/System/Library/Fonts/Supplemental/Impact.ttf",
          "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "C:/Windows/Fonts/impact.ttf", "C:/Windows/Fonts/arialbd.ttf",
          "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


# a legenda usa Arial Bold, igual ao caminho rápido (libass) e à tela de referência; o título usa Anton
FONTES_LEGENDA = ["C:/Windows/Fonts/arialbd.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                  "/Library/Fonts/Arial Bold.ttf", "/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"] + FONTES


def fonte(tamanho, lista=None):
    for f in (lista or FONTES):
        if Path(f).exists():
            return ImageFont.truetype(f, tamanho)
    return ImageFont.load_default()


def cor(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def para_cv(p):
    """The path as OpenCV can open it. On Windows OpenCV does not open a path with accents (C:\\Users\\João\\...),
    so it gets the same file counted from the current folder, which has none."""
    p = str(p)
    if comum.WINDOWS and not p.isascii():
        try:
            curto = os.path.relpath(p)
            if curto.isascii():
                return curto
        except ValueError:
            pass
    return p


def gravar_jpg(caminho, imagem, qualidade):
    """cv2.imwrite fails without a word on a Windows path with accents: encode here, write with Python."""
    ok, dado = cv2.imencode(".jpg", imagem, [cv2.IMWRITE_JPEG_QUALITY, qualidade])
    if ok:
        Path(caminho).write_bytes(dado.tobytes())


def nome_de_arquivo(t):
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:50] or "corte"


# ---------- the piece of the stream ----------

def baixar_trecho(info, pasta, n, ini, fim, cookies, max_altura=2160):
    """Copia trechos na qualidade original. NÃO força keyframes: isso recodificava e degradava o vídeo."""
    destino = pasta / ("%02d.mp4" % n)
    cache = pasta / ("%02d-origem.json" % n)
    fonte = info.get("arquivo_local") or info["link"]
    chave = {"origem": fonte, "inicio": round(ini, 2), "fim": round(fim, 2), "max_altura": max_altura}
    if info.get("arquivo_local"):
        stat = Path(info["arquivo_local"]).stat()
        chave.update({"tamanho_origem": stat.st_size, "modificado_ns": stat.st_mtime_ns})
    if destino.exists() and destino.stat().st_size > 100000 and comum.ler_json(cache) == chave:
        return destino
    destino.unlink(missing_ok=True)
    a, b = max(0.0, ini - MARGEM), fim + MARGEM
    if info.get("arquivo_local"):
        r = subprocess.run([comum.ffmpeg(), "-hide_banner", "-v", "error", "-y", "-ss", "%.3f" % a,
                            "-i", info["arquivo_local"], "-t", "%.3f" % (b - a), "-map", "0:v:0",
                            "-map", "0:a:0", "-c", "copy", "-avoid_negative_ts", "make_zero", str(destino)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
    else:
        # Melhor fonte disponível até max_altura: maior resolução, depois mais fps, depois mais bitrate.
        fmt = ("bv*[height<=%d]+ba/bv*[height<=%d]/b" % (max_altura, max_altura))
        r = comum.ytdlp("-f", fmt, "-S", "res,fps,vbr,abr", "--download-sections", "*%.3f-%.3f" % (a, b),
                        "--merge-output-format", "mp4", "-o", str(pasta / ("%02d.%%(ext)s" % n)),
                        info["link"], cookies=cookies)
    if r.returncode or not destino.exists() or destino.stat().st_size < 100000:
        sys.exit("Não consegui obter o trecho %d:\n%s" % (n, (r.stderr or "")[-1200:]))
    comum.escrever_json(cache, chave)
    return destino


def envelope(x):
    x = np.abs(x.astype(np.float32))
    n = len(x) // 160 * 160
    e = x[:n].reshape(-1, 160).mean(axis=1)  # 100 values per second
    return (e - e.mean()) / (e.std() + 1e-9)


def alinhar(trecho, audio_da_live, pedido):
    """Where in the stream (seconds) the downloaded piece really starts, found by matching its sound to the stream's sound."""
    som = comum.audio(trecho)
    if len(som) < comum.TAXA * 5:
        return pedido, som, 0.0
    folga = 25.0
    base = max(0.0, pedido - folga)
    regiao = comum.audio(audio_da_live, inicio=base, duracao=len(som) / comum.TAXA + 2 * folga)
    x, y = envelope(som), envelope(regiao)
    if len(y) <= len(x):
        return pedido, som, 0.0
    # OpenCV faz a correlação em código otimizado, evitando uma operação quadrática em NumPy.
    c = cv2.matchTemplate(y.reshape(1, -1).astype(np.float32),
                          x.reshape(1, -1).astype(np.float32), cv2.TM_CCORR_NORMED).ravel()
    k = int(np.argmax(c))
    certeza = float((c[k] - c.mean()) / (c.std() + 1e-9))
    if certeza < 6:
        return pedido, som, certeza
    return base + k / 100.0, som, certeza


# ---------- the streamer's camera ----------

class Rostos:
    def __init__(self):
        modelo = comum.MODELOS / "face_detection_yunet_2023mar.onnx"
        self.yunet = self.haar = None
        if modelo.exists() and hasattr(cv2, "FaceDetectorYN"):
            try:
                self.yunet = cv2.FaceDetectorYN.create(str(modelo), "", (320, 320), 0.7, 0.3, 50)
            except Exception:
                self.yunet = None
            if self.yunet is None:  # a path OpenCV cannot open (accents, on Windows): hand it the file's bytes
                try:
                    dado = np.frombuffer(modelo.read_bytes(), np.uint8)
                    self.yunet = cv2.FaceDetectorYN.create("onnx", dado, np.zeros(0, np.uint8), (320, 320), 0.7, 0.3, 50)
                except Exception:
                    self.yunet = None
        if self.yunet is None:
            try:
                haar = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
                self.haar = None if haar.empty() else haar
            except Exception:
                self.haar = None

    def em(self, quadro):
        h, w = quadro.shape[:2]
        if self.yunet is not None:
            self.yunet.setInputSize((w, h))
            _, achados = self.yunet.detect(quadro)
            return [tuple(float(v) for v in f[:4]) for f in (achados if achados is not None else [])]
        if self.haar is None:
            return []  # no face finder on this computer: the cut goes out with the video in the middle
        cinza = cv2.cvtColor(quadro, cv2.COLOR_BGR2GRAY)
        return [tuple(float(v) for v in f) for f in self.haar.detectMultiScale(cinza, 1.1, 5, minSize=(40, 40))]


def amostrar(trecho, t0, dur, rostos, cada=0.5):
    """Looks at the cut twice a second. Returns the faces seen at each look and the pictures themselves (all of them, at half size
    when there are many, so a long cut does not fill the memory; faces are searched on the full picture)."""
    cap = cv2.VideoCapture(para_cv(trecho))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    alvos = [int(round((t0 + i * cada) * fps)) for i in range(int(dur / cada) + 1)]
    quadros, achados, i = [], [], 0
    while alvos:
        ok = cap.grab()
        if not ok:
            break
        if i == alvos[0]:
            ok, q = cap.retrieve()
            if ok:
                achados.append(rostos.em(q))
                quadros.append(q)
            alvos.pop(0)
        i += 1
    cap.release()
    return quadros, achados


def rosto_parado(quadros, achados):
    """The streamer's camera: a face that stays in the same place in most pictures and is alive.
    A face painted on the game's artwork or on an overlay also stays in place, but its pixels never change. Returns (x, y, w, h) or None."""
    if not quadros:
        return None
    W = quadros[0].shape[1]
    grupos = []
    for qi in range(len(quadros)):
        vistos = set()
        for (x, y, w, h) in achados[qi]:
            cx, cy = x + w / 2, y + h / 2
            for gi, g in enumerate(grupos):
                if abs(cx - g["cx"]) < 0.06 * W and abs(cy - g["cy"]) < 0.06 * W and 0.5 < w / g["w"] < 2.0:
                    if gi not in vistos:
                        g["caixas"].append((x, y, w, h))
                        g["onde"].append(qi)
                        g["cx"], g["cy"], g["w"] = np.median([[b[0] + b[2] / 2, b[1] + b[3] / 2, b[2]] for b in g["caixas"]], axis=0)
                        vistos.add(gi)
                    break
            else:
                grupos.append({"cx": cx, "cy": cy, "w": w, "caixas": [(x, y, w, h)], "onde": [qi]})
    grupos = [g for g in grupos if len(g["caixas"]) >= max(3, 0.35 * len(quadros))]
    if not grupos:
        return None
    H = quadros[0].shape[0]
    for g in grupos:
        x, y, w, h = [int(v) for v in np.median(np.array(g["caixas"]), axis=0)]
        x, y = max(0, x), max(0, y)
        w, h = max(8, min(w, W - x)), max(8, min(h, H - y))
        minis = [cv2.resize(cv2.cvtColor(quadros[i][y:y + h, x:x + w], cv2.COLOR_BGR2GRAY), (48, 48), interpolation=cv2.INTER_AREA).astype(np.float32)
                 for i in range(len(quadros))]
        # how much the picture inside the box changes from one second to the next (grey levels)
        g["vida"] = float(np.median([np.abs(minis[i + 1] - minis[i]).mean() for i in range(len(minis) - 1)])) if len(minis) > 1 else 0.0
    vivos = [g for g in grupos if g["vida"] >= 1.5]
    melhor = max(vivos or grupos, key=lambda g: (len(g["caixas"]), g["w"]))
    return tuple(float(v) for v in np.median(np.array(melhor["caixas"]), axis=0))


def linhas_paradas(quadros):
    """Edges that are in the same place in every frame: the borders of what the streamer put over the game."""
    soma_v = soma_h = None
    for q in quadros:
        c = cv2.cvtColor(q, cv2.COLOR_BGR2GRAY).astype(np.float32)
        gv, gh = np.abs(cv2.Sobel(c, cv2.CV_32F, 1, 0, ksize=3)), np.abs(cv2.Sobel(c, cv2.CV_32F, 0, 1, ksize=3))
        soma_v = gv if soma_v is None else np.minimum(soma_v, gv)  # the minimum over time keeps only what never moves
        soma_h = gh if soma_h is None else np.minimum(soma_h, gh)
    return soma_v, soma_h


def caixa_da_camera(quadros, rosto):
    """From the face to the whole camera box: first a guess from the size of the face, then snapped to borders that never move."""
    H, W = quadros[0].shape[:2]
    fx, fy, fw, fh = rosto
    cx, cy = fx + fw / 2, fy + fh / 2
    # the guess
    esq, dir_ = cx - 1.7 * fw, cx + 1.7 * fw
    topo, base = cy - 1.0 * fh, cy + 1.5 * fh
    achou = {}
    if len(quadros) >= 4:
        bv, bh = linhas_paradas(quadros)
        y0, y1 = int(max(0, cy - 0.8 * fh)), int(min(H, cy + 0.8 * fh))
        x0, x1 = int(max(0, cx - 0.8 * fw)), int(min(W, cx + 0.8 * fw))
        col = bv[y0:y1].mean(axis=0)   # one number per column: how much of a standing line it holds
        lin = bh[:, x0:x1].mean(axis=1)

        def procura(serie, de, ate, piso):
            de, ate = int(max(0, min(de, ate))), int(min(len(serie), max(de, ate)))
            if ate - de < 4:
                return None
            k = de + int(np.argmax(serie[de:ate]))
            return k if serie[k] >= piso else None

        piso_c, piso_l = max(12.0, 6 * float(np.median(col))), max(12.0, 6 * float(np.median(lin)))
        achou["esq"] = procura(col, cx - 4.0 * fw, cx - 0.8 * fw, piso_c)
        achou["dir"] = procura(col, cx + 0.8 * fw, cx + 4.0 * fw, piso_c)
        achou["topo"] = procura(lin, cy - 3.0 * fh, cy - 0.7 * fh, piso_l)
        achou["base"] = procura(lin, cy + 0.9 * fh, cy + 4.5 * fh, piso_l)
        # a camera that touches the edge of the screen has no line there: the edge is the border
        if achou["esq"] is None and cx - 2.4 * fw <= 0:
            achou["esq"] = 0
        if achou["dir"] is None and cx + 2.4 * fw >= W:
            achou["dir"] = W
        if achou["topo"] is None and cy - 1.6 * fh <= 0:
            achou["topo"] = 0
        if achou["base"] is None and cy + 2.6 * fh >= H:
            achou["base"] = H
        if achou["esq"] is not None and achou["dir"] is not None and 2.0 * fw <= achou["dir"] - achou["esq"] <= 8 * fw:
            esq, dir_ = achou["esq"] + 2, achou["dir"] - 2
        if achou["topo"] is not None and achou["base"] is not None and 1.6 * fh <= achou["base"] - achou["topo"] <= 7 * fh:
            topo, base = achou["topo"] + 2, achou["base"] - 2
    esq, dir_, topo, base = max(0.0, esq), min(float(W), dir_), max(0.0, topo), min(float(H), base)
    return [int(esq), int(topo), int(dir_ - esq), int(base - topo)]


GRANDE = 0.16  # a face this wide (share of the screen's width) means the camera is the whole screen


def planos(quadros, achados, forcado_modo, forcada_camera, cada=0.5):
    """How the cut is framed, stretch by stretch, because streamers change the screen in the middle of a moment.
    Each stretch is 'facecam' (camera on top, game below), 'cheia' (the camera is the whole screen) or 'sem' (no face).
    Returns [{"de": seconds, "entre": seconds of the look before, "pl": {...}}], the first one starting at 0."""
    H, W = quadros[0].shape[:2]
    if forcada_camera:
        return [{"de": 0.0, "entre": 0.0, "pl": {"modo": "facecam", "camera": forcada_camera, "rosto": None}}]
    if forcado_modo == "sem":
        return [{"de": 0.0, "entre": 0.0, "pl": {"modo": "sem", "camera": None, "rosto": None}}]
    n = len(quadros)
    grandes = []
    for fs in achados:
        g = [f for f in fs if f[2] >= GRANDE * W]
        grandes.append(max(g, key=lambda f: f[2]) if g else None)
    marca = ["cheia" if g is not None else "cam" for g in grandes]
    if forcado_modo == "cheia":
        marca = ["cheia"] * n
    if forcado_modo == "facecam":
        marca = ["cam"] * n
    # a single look that disagrees with both neighbours is a wrong detection, not a change of screen
    for _ in range(2):
        for i in range(n):
            antes, depois = marca[i - 1] if i else None, marca[i + 1] if i + 1 < n else None
            if marca[i] != antes and marca[i] != depois and (antes or depois):
                marca[i] = antes or depois
    # the small camera, measured only on the looks where the screen is the game
    idx = [i for i in range(n) if marca[i] == "cam"]
    pl_cam = {"modo": "sem", "camera": None, "rosto": None}
    if idx:
        qs = [quadros[i] for i in idx]
        pequenos = [[f for f in achados[i] if f[2] < GRANDE * W] for i in idx]
        rosto = rosto_parado(qs, pequenos)
        if rosto is not None:
            caixa = caixa_da_camera(qs[::2] if len(qs) > 8 else qs, rosto)
            if rosto[2] >= 0.14 * W and caixa[2] >= 0.55 * W:
                # a stream that is only the streamer talking: the camera is the screen, there is no game to put below
                pl_cam = {"modo": "cheia", "camera": None, "rosto": [int(v) for v in rosto]}
            else:
                pl_cam = {"modo": "facecam", "camera": caixa, "rosto": [int(v) for v in rosto]}
    trechos, i = [], 0
    while i < n:
        j = i
        while j + 1 < n and marca[j + 1] == marca[i]:
            j += 1
        if marca[i] == "cheia":
            caixas = [grandes[k] for k in range(i, j + 1) if grandes[k] is not None]
            rosto = [int(v) for v in np.median(np.array(caixas), axis=0)] if caixas else [W // 2 - 100, H // 3, 200, 240]
            pl = {"modo": "cheia", "camera": None, "rosto": rosto}
        else:
            pl = pl_cam
        trechos.append({"de": i * cada if i else 0.0, "entre": max(0.0, (i - 1) * cada), "pl": pl})
        i = j + 1
    return trechos


def dentro(caixa, maior, folga=16):
    """True se `caixa` (x,y,w,h) cabe dentro de `maior`, com folga em px."""
    x, y, w, h = caixa
    X, Y, Wm, Hm = maior
    return x >= X - folga and y >= Y - folga and x + w <= X + Wm + folga and y + h <= Y + Hm + folga


def sobre(caixa, ref):
    """Fração da área de `caixa` que cai dentro de `ref` (0 a 1)."""
    x, y, w, h = caixa
    X, Y, W2, H2 = ref
    lx = max(0, min(x + w, X + W2) - max(x, X))
    ly = max(0, min(y + h, Y + H2) - max(y, Y))
    return (lx * ly) / float(max(1, w * h))


def caixa_dominante(caixas):
    """A caixa da webcam que contém mais detecções (a câmera inteira); empate fica com a maior."""
    caixas = [[int(v) for v in c] for c in caixas]
    areas = sorted(c[2] * c[3] for c in caixas)
    teto = 3 * areas[len(areas) // 2]  # ignora detecção exagerada (que pegaria parte do jogo)
    candidatas = [c for c in caixas if c[2] * c[3] <= teto] or caixas
    return max(candidatas, key=lambda c: (sum(dentro(o, c) for o in caixas), c[2] * c[3]))


def recortes(pl, W, H, estilo=None):
    """Crops + positions. Gamer fills a small top panel without enlarging the webcam to 1080."""
    estilo = estilo or ESTILO
    if pl["modo"] == "facecam" and estilo.get("layout", "gamer") == "gamer":
        x, y, w, h = (int(v) for v in pl["camera"])
        x, y = max(0, x), max(0, y)
        w, h = min(max(1, w), W - x), min(max(1, h), H - y)
        if w < 8 or h < 8:
            return recortes({"modo": "sem", "camera": None, "rosto": None}, W, H, estilo)
        painel = max(380, min(1000, int(estilo.get("altura_painel_camera", 608))))
        fade = max(0, min(painel // 2, int(estilo.get("fade_camera", 160))))
        # Facecam em largura total: recorta a caixa da câmera na proporção do painel, em volta do rosto (sem esticar).
        prop = L / float(painel)
        if w / float(h) > prop:
            nw = max(2, int(h * prop))
            centro = (pl["rosto"][0] + pl["rosto"][2] / 2) if pl.get("rosto") else x + w / 2
            x = int(min(max(x, centro - nw / 2), x + w - nw))
            cam = (x, y, nw, h)
        else:
            nh = max(2, int(w / prop))
            centro = (pl["rosto"][1] + pl["rosto"][3] * 0.55) if pl.get("rosto") else y + h / 2
            cy = int(min(max(y, centro - nh * 0.45), y + h - nh))
            cam = (x, cy, w, nh)
        alt_jogo = A - painel + fade  # a gameplay começa por baixo do gradiente
        # Crop vertical centrado no jogo, favorecendo a área oposta à posição da facecam original.
        jh = min(H, max(2, int(round(W * alt_jogo / float(L)))))
        jw = min(W, max(2, int(round(jh * L / float(alt_jogo)))))
        jy = max(0, (H - jh) // 2)
        jx = (W - jw) // 2
        if x < jx + jw and x + w > jx:
            esquerda, direita = max(0, x - jw), min(W - jw, x + w)
            jx = direita if (x + w / 2) < W / 2 else esquerda
        jx = max(0, min(W - jw, jx))
        return {"fade": fade, "topo": cam + (0, 0, L, painel),
                "jogo": (jx, jy, jw, jh, 0, painel - fade, L, alt_jogo),
                "emenda": painel + int(estilo.get("titulo_desloca", 0))}
    if pl["modo"] == "facecam":
        x, y, w, h = pl["camera"]
        prop = min(1.9, max(1.3, w / float(h)))
        # trim the camera box to that shape, around the face when we know it
        if w / float(h) > prop:
            nw = int(h * prop)
            centro = (pl["rosto"][0] + pl["rosto"][2] / 2) if pl["rosto"] else x + w / 2
            x = int(min(max(x, centro - nw / 2), x + w - nw))
            w = nw
        else:
            nh = int(w / prop)
            centro = (pl["rosto"][1] + pl["rosto"][3] * 0.55) if pl["rosto"] else y + h / 2
            y = int(min(max(y, centro - nh * 0.45), y + h - nh))
            h = nh
        alt_topo = int(round(L / prop / 2) * 2)
        alt_jogo = A - alt_topo
        jw = int(H * L / float(alt_jogo))
        jx = (W - jw) // 2
        cam_cx = x + w / 2
        if x < jx + jw and x + w > jx:  # the camera sits inside the middle of the game: slide the game crop away from it
            jx = min(W - jw, x + w) if cam_cx < W / 2 else max(0, x - jw)
        return {"topo": (x, y, w, h, 0, 0, L, alt_topo), "jogo": (jx, 0, jw, H, 0, alt_topo, L, alt_jogo), "emenda": alt_topo}
    if pl["modo"] == "cheia":
        cw = int(H * L / float(A))
        cx = pl["rosto"][0] + pl["rosto"][2] / 2
        x = int(min(max(0, cx - cw / 2), W - cw))
        return {"jogo": (x, 0, cw, H, 0, 0, L, A), "emenda": int(A * 0.16)}
    alt = int(L * H / float(W) / 2) * 2
    return {"fundo": True, "jogo": (0, 0, W, H, 0, (A - alt) // 2, L, alt), "emenda": (A - alt) // 2 - 70}


# ---------- the words on screen ----------

def limpar(p):
    # tira aspas e qualquer letra fora do alfabeto latino (o Whisper às vezes solta um caractere chinês/cirílico no meio)
    p = "".join(ch for ch in p if ord(ch) < 0x0250 or 0x2010 <= ord(ch) <= 0x206F)
    return re.sub(r"[\"“”]", "", p).strip()


def grupos_de_legenda(palavras, estilo):
    grupos, atual = [], []
    for p in palavras:
        w = limpar(p["w"])
        if not w:
            continue
        txt = w.upper() if estilo["maiusculas"] else w
        item = {"w": txt.rstrip(",.;:"), "s": p["s"], "e": p["e"]}
        if not item["w"]:
            continue
        letras = sum(len(x["w"]) for x in atual) + len(item["w"])
        if atual and (len(atual) >= estilo["palavras_por_legenda"] or letras > estilo["letras_por_legenda"]
                      or p["s"] - atual[-1]["e"] > 0.5 or atual[-1].get("fim_de_frase")):
            grupos.append(atual)
            atual = []
        item["fim_de_frase"] = bool(re.search(r"[.!?]$", w))
        atual.append(item)
    if atual:
        grupos.append(atual)
    for i, g in enumerate(grupos):
        proximo = grupos[i + 1][0]["s"] if i + 1 < len(grupos) else g[-1]["e"] + 0.6
        g[-1]["mostra_ate"] = min(proximo, g[-1]["e"] + 0.6)
    return grupos


def imagem_da_legenda(grupo, ativo, estilo):
    tam = estilo["tamanho_legenda"]
    while True:
        f = fonte(tam, FONTES_LEGENDA)
        espaco = f.getlength(" ")
        larguras = [f.getlength(x["w"]) for x in grupo]
        total = sum(larguras) + espaco * (len(grupo) - 1)
        if total <= L - 120 or tam <= 40:
            break
        tam -= 6
    borda = max(6, tam // 10)
    img = Image.new("RGBA", (int(total) + 4 * borda, int(tam * 1.5) + 4 * borda), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x = 2 * borda
    for i, pal in enumerate(grupo):
        d.text((x, 2 * borda), pal["w"], font=f, fill=cor(estilo["cor_destaque"] if i == ativo else estilo["cor_legenda"]) + (255,),
               stroke_width=borda, stroke_fill=cor(estilo["cor_contorno"]) + (255,))
        x += larguras[i] + espaco
    return np.array(img)


def imagem_do_titulo(texto, estilo):
    texto = texto.upper() if estilo["maiusculas"] else texto
    tam = estilo["tamanho_titulo"]
    while True:
        f = fonte(tam)
        linhas, atual = [], ""
        for p in texto.split():
            tenta = (atual + " " + p).strip()
            if f.getlength(tenta) <= L - 200 or not atual:
                atual = tenta
            else:
                linhas.append(atual)
                atual = p
        linhas.append(atual)
        if len(linhas) <= 2 or tam <= 40:
            break
        tam -= 4
    alt_linha = int(tam * 1.28)
    larg = int(max(f.getlength(x) for x in linhas)) + 72
    alt = alt_linha * len(linhas) + 40
    img = Image.new("RGBA", (larg + 16, alt + 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((12, 12, larg + 12, alt + 12), radius=22, fill=(0, 0, 0, 110))        # a soft shadow
    d.rounded_rectangle((4, 4, larg + 4, alt + 4), radius=22, fill=cor(estilo["cor_destaque"]) + (255,))
    for i, linha in enumerate(linhas):
        d.text((4 + (larg - f.getlength(linha)) / 2, 4 + 14 + i * alt_linha), linha, font=f, fill=cor(estilo["cor_titulo_texto"]) + (255,))
    return np.array(img)


def colar(tela, rgba, cx, cy, opacidade=1.0):
    """Paste an RGBA picture centred on (cx, cy) of the BGR canvas."""
    h, w = rgba.shape[:2]
    x0, y0 = int(cx - w / 2), int(cy - h / 2)
    x1, y1 = max(0, x0), max(0, y0)
    x2, y2 = min(tela.shape[1], x0 + w), min(tela.shape[0], y0 + h)
    if x2 <= x1 or y2 <= y1:
        return
    pedaco = rgba[y1 - y0:y2 - y0, x1 - x0:x2 - x0]
    alfa = pedaco[:, :, 3:4].astype(np.float32) / 255.0 * opacidade
    tela[y1:y2, x1:x2] = (tela[y1:y2, x1:x2] * (1 - alfa) + pedaco[:, :, 2::-1] * alfa).astype(np.uint8)


# ---------- the clip ----------

_ENCODERS = {}


def encoders_disponiveis():
    """A lista de encoders do FFmpeg, lida uma vez só por execução."""
    if "lista" not in _ENCODERS:
        _ENCODERS["lista"] = subprocess.run([comum.ffmpeg(), "-hide_banner", "-encoders"], capture_output=True, text=True,
                                            encoding="utf-8", errors="replace").stdout
    return _ENCODERS["lista"]


def parametros_gpu(nome, estilo):
    """H.264 na placa de vídeo, mirando a mesma qualidade visual do crf do libx264."""
    g = str(FPS * 2)
    if nome == "h264_amf":
        # QVBR da AMD: número MAIOR = melhor (45 ≈ SSIM 0,995 num trecho de GTA, ~2,5x mais rápido que o libx264 slow).
        # Não usar -rc cqp: travou o encoder no teste com a RX 9070 XT.
        return ["-c:v", "h264_amf", "-usage", "transcoding", "-quality", "quality", "-rc", "qvbr",
                "-qvbr_quality_level", str(int(estilo.get("qualidade_amf", 45))), "-profile:v", "high", "-g", g, "-preanalysis", "true", "-vbaq", "true"]
    q = str(int(estilo.get("qualidade_gpu", 18)))
    if nome == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p7", "-tune", "hq", "-rc", "vbr", "-cq", q, "-b:v", "0",
                "-profile:v", "high", "-g", g]
    return ["-c:v", "h264_qsv", "-preset", "veryslow", "-global_quality", q, "-profile:v", "high", "-g", g]


def gpu_funciona(nome):
    """O encoder aparece na lista mesmo sem a placa certa: codifica meio segundo de teste para ter certeza."""
    chave = "ok-" + nome
    if chave not in _ENCODERS:
        r = subprocess.run([comum.ffmpeg(), "-hide_banner", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=30",
                            "-t", "0.5"] + parametros_gpu(nome, ESTILO) + ["-pix_fmt", "yuv420p", "-f", "null", "-"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        _ENCODERS[chave] = r.returncode == 0
    return _ENCODERS[chave]


def codificador(estilo=None):
    """Encode de alta qualidade: o YouTube recomprime no upload, então o arquivo precisa chegar com sobra de detalhe.
    Com estilo["gpu"] (ou --gpu) usa a placa de vídeo que funcionar; se nenhuma funcionar, volta ao libx264."""
    estilo = estilo or ESTILO
    r = encoders_disponiveis()
    if estilo.get("gpu"):
        for nome in ("h264_amf", "h264_nvenc", "h264_qsv"):
            if nome in r and gpu_funciona(nome):
                return parametros_gpu(nome, estilo)
        if not _ENCODERS.get("avisou"):
            print("    aviso: nenhuma placa de vídeo codificou o teste; usando o processador (libx264).", flush=True)
            _ENCODERS["avisou"] = True
    if "libx264" in r:
        return ["-c:v", "libx264", "-preset", str(estilo.get("preset", "slow")), "-crf", str(estilo.get("crf", 16)),
                "-profile:v", "high", "-level", "4.2", "-g", str(FPS * 2), "-bf", "2"]
    if "h264_videotoolbox" in r:
        return ["-c:v", "h264_videotoolbox", "-b:v", "16M", "-profile:v", "high"]
    return ["-c:v", "mpeg4", "-q:v", "2"]


def afiar(img, forca):
    """Nitidez leve (unsharp mask) na facecam depois da ampliação. Não cria detalhe, só tira o aspecto lavado."""
    if forca <= 0:
        return img
    borrada = cv2.GaussianBlur(img, (0, 0), 1.2)
    return cv2.addWeighted(img, 1.0 + forca, borrada, -forca, 0)


_MASCARAS = {}


def mascara_fade(w, h, fade):
    """Alfa 1 no painel da facecam, caindo suave (smoothstep) até 0 nos últimos `fade` px."""
    chave = (w, h, fade)
    if chave not in _MASCARAS:
        col = np.ones(h, np.float32)
        if fade:
            t = np.linspace(1.0, 0.0, fade, dtype=np.float32)
            col[h - fade:] = t * t * (3 - 2 * t)
        _MASCARAS[chave] = np.repeat(col[:, None], w, axis=1)
    return _MASCARAS[chave]


def montar(trecho, t0, dur, pls, grupos, titulo, estilo, saida, folha, coment=None):
    """coment: {"abre": {"arquivo", "dur", "grupos"}, "fecha": {...}}: the person's own voice before and after the cut,
    over the first and the last picture of the cut, held still and darkened."""
    coment = coment or {}
    cap = cv2.VideoCapture(para_cv(trecho))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    W, H = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    rcs = [recortes(s["pl"], W, H, estilo) for s in pls]  # one framing per stretch of the cut
    n_corte = int(dur * FPS)
    n_abre = int(coment["abre"]["dur"] * FPS) if "abre" in coment else 0
    n_fecha = int(coment["fecha"]["dur"] * FPS) if "fecha" in coment else 0
    total = n_abre + n_corte + n_fecha
    fim_card = encerramento(estilo, total / float(FPS))  # o card final vale para o fim do vídeo inteiro
    k_card = int(round(fim_card["inicio"] * FPS)) if fim_card else total + 1
    k_saida = total - int(round(fim_card["fade_saida"] * FPS)) if fim_card else total + 1
    # the sound: [the opening comment] + the cut + [the closing comment], each brought to the same loudness, then joined
    entradas, filtros, juntar = [], [], []
    nivel = "loudnorm=I=%d:TP=-1.5:LRA=11,aresample=48000,aformat=channel_layouts=stereo" % estilo["volume"]

    def entra(args, extra=""):
        entradas.extend(args)
        i = len(juntar) + 1
        filtros.append("[%d:a]%s%s[a%d]" % (i, extra, nivel, i))
        juntar.append("[a%d]" % i)

    if n_abre:
        entra(["-t", "%.3f" % (n_abre / float(FPS)), "-i", str(coment["abre"]["arquivo"])])
    entra(["-ss", "%.3f" % t0, "-t", "%.3f" % (n_corte / float(FPS)), "-i", str(trecho)],
          "afade=t=in:d=0.04,afade=t=out:st=%.3f:d=0.1," % max(0.0, n_corte / float(FPS) - 0.1))
    if n_fecha:
        entra(["-t", "%.3f" % (n_fecha / float(FPS)), "-i", str(coment["fecha"]["arquivo"])])
    filtro = ";".join(filtros) + ";" + "".join(juntar) + "concat=n=%d:v=0:a=1,loudnorm=I=%d:TP=-1.5:LRA=11%s[som]" % (
        len(juntar), estilo["volume"],
        (",afade=t=out:st=%.3f:d=%.3f" % (total / float(FPS) - fim_card["fade_saida"], fim_card["fade_saida"]))
        if fim_card and fim_card["fade_saida"] > 0 else "")
    cmd = [comum.ffmpeg(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "%dx%d" % (L, A), "-r", str(FPS), "-i", "-"] + entradas + [
           "-filter_complex", filtro, "-map", "0:v", "-map", "[som]"] + codificador(estilo) + [
           "-pix_fmt", "yuv420p", "-ar", "48000", "-c:a", "aac", "-b:a", "%dk" % estilo.get("audio_kbps", 256), "-movflags", "+faststart", "-shortest", str(saida)]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    img_titulo = imagem_do_titulo(titulo, estilo) if (estilo["titulo"] and titulo) else None
    cache = {}
    cor_barra = cor(estilo.get("cor_barra", estilo["cor_destaque"]))[::-1]
    alt_barra = int(estilo.get("altura_barra", 12))
    estilo_meu = dict(estilo, cor_destaque=estilo["cor_comentario"])  # the person's own words in another colour
    guardar = {int(total * (i + 0.5) / 6): None for i in range(6)}

    def compor(quadro, rc):
        tela = np.zeros((A, L, 3), np.uint8)
        if rc.get("fundo"):
            cw = int(H * L / float(A))
            f = cv2.resize(quadro[:, (W - cw) // 2:(W - cw) // 2 + cw], (L // 16, A // 16), interpolation=cv2.INTER_AREA)
            tela[:] = (cv2.resize(cv2.GaussianBlur(f, (0, 0), 3), (L, A), interpolation=cv2.INTER_LINEAR) * 0.45).astype(np.uint8)
        for chave in ("jogo", "topo"):
            if chave in rc:
                sx, sy, sw, sh, dx, dy, dw, dh = rc[chave]
                img = cv2.resize(quadro[sy:sy + sh, sx:sx + sw], (dw, dh),
                                 interpolation=cv2.INTER_AREA if dw < sw else cv2.INTER_LANCZOS4)
                if chave == "topo" and dw > sw:
                    img = afiar(img, float(estilo.get("nitidez_camera", 0)))
                f = rc.get("fade", 0) if chave == "topo" else 0
                if f:
                    # gradiente vertical: a base da facecam some aos poucos e revela a gameplay embaixo
                    alfa = mascara_fade(dw, dh, f)[:, :, None]
                    fundo = tela[dy:dy + dh, dx:dx + dw].astype(np.float32)
                    img = (img.astype(np.float32) * alfa + fundo * (1 - alfa)).astype(np.uint8)
                tela[dy:dy + dh, dx:dx + dw] = img
        return tela

    def legenda(tela, lista, t, est, marca):
        for gi, g in enumerate(lista):
            if g[0]["s"] - 0.03 <= t < g[-1]["mostra_ate"]:
                ativo = max([i for i, p in enumerate(g) if p["s"] - 0.03 <= t] or [0])
                if (marca, gi, ativo) not in cache:
                    cache[(marca, gi, ativo)] = imagem_da_legenda(g, ativo, est)
                colar(tela, cache[(marca, gi, ativo)], L / 2, A * estilo["altura_legenda"])
                return

    lido, quadro, parado = -1, None, None
    atual, mini_antes = 0, None  # which stretch we are in; the last picture, small, to see a hard change of screen
    for k in range(total):
        kc = min(max(k - n_abre, 0), n_corte - 1)  # which picture of the cut this frame shows
        alvo = int(round(t0 * fps + kc * fps / FPS))
        while lido < alvo:
            ok, q = cap.read()
            if not ok:
                break
            quadro, lido = q, lido + 1
        if quadro is None:
            break
        if atual + 1 < len(pls) and n_abre <= k < n_abre + n_corte:
            seg, prox = kc / float(FPS), pls[atual + 1]
            mini = cv2.resize(cv2.cvtColor(quadro, cv2.COLOR_BGR2GRAY), (64, 36), interpolation=cv2.INTER_AREA).astype(np.float32)
            virou = mini_antes is not None and seg > prox["entre"] and float(np.abs(mini - mini_antes).mean()) > 22
            mini_antes = mini
            if virou or seg >= prox["de"]:  # the screen changed here (or, with a soft change, at the look that saw it)
                atual += 1
        rc = rcs[atual]
        if n_abre <= k < n_abre + n_corte:
            tela = compor(quadro, rc)
            if k < k_card:
                legenda(tela, grupos, kc / float(FPS), estilo, "c")
            parado = None
        else:
            if parado is None:
                parado = (compor(quadro, rc) * 0.4).astype(np.uint8)  # held still and darkened while the person speaks
            tela = parado.copy()
            if k < n_abre:
                legenda(tela, coment["abre"]["grupos"], k / float(FPS), estilo_meu, "a")
            elif k < k_card:
                legenda(tela, coment["fecha"]["grupos"], (k - n_abre - n_corte) / float(FPS), estilo_meu, "f")
        if img_titulo is not None and k < k_card:
            colar(tela, img_titulo, L / 2, rc["emenda"])
        if k >= k_card:
            tela = aplicar_encerramento(tela, (k - k_card) / float(FPS), fim_card)
        if k >= k_saida:
            tela = (tela * ((total - k) / float(max(1, total - k_saida)))).astype(np.uint8)
        if estilo["barra"]:
            tela[A - alt_barra:A, :int(L * (k + 1) / float(total))] = cor_barra
        if k in guardar:
            guardar[k] = cv2.resize(tela, (360, 640), interpolation=cv2.INTER_AREA)
        enc.stdin.write(tela.tobytes())
    cap.release()
    enc.stdin.close()
    enc.wait()
    minis = [m for m in guardar.values() if m is not None]
    if minis:
        gravar_jpg(folha, np.hstack(minis), 88)
    return enc.returncode == 0



def _tempo_ass(segundos):
    cent = max(0, int(round(float(segundos) * 100)))
    h, r = divmod(cent, 360000)
    m, r = divmod(r, 6000)
    return "%d:%02d:%02d.%02d" % (h, m, r // 100, r % 100)


def _cor_ass(hex_rgb):
    r, g, b = cor(hex_rgb)
    return "&H00%02X%02X%02X" % (b, g, r)


def _salvar_ass(grupos, estilo, destino, ate=None):
    """Legendagem palavra a palavra via libass, sem editar 30/60 frames por segundo em Python."""
    normal = _cor_ass(estilo["cor_legenda"])
    forte = _cor_ass(estilo["cor_destaque"])
    outline = _cor_ass(estilo["cor_contorno"])
    alto = int(A * float(estilo["altura_legenda"]))
    fonte_ass = "Arial"
    linhas = ["[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "ScaledBorderAndShadow: yes",
              "", "[V4+ Styles]", "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
              "Style: Texto,%s,%d,%s,%s,%s,&H80000000,-1,0,0,0,100,100,0,0,1,5,1,5,32,32,32,1" %
              (fonte_ass, estilo["tamanho_legenda"], normal, forte, outline), "", "[Events]",
              "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text"]
    eventos = []
    for grupo in grupos:
        for i, palavra in enumerate(grupo):
            inicio = max(0, palavra["s"] - 0.03)
            fim = (grupo[i + 1]["s"] if i + 1 < len(grupo) else grupo[-1]["mostra_ate"])
            palavras = []
            for j, item in enumerate(grupo):
                txt = item["w"].replace("{", "(").replace("}", ")").replace("\\", "")
                palavras.append(r"{\c%s}%s" % (forte if j == i else normal, txt))
            eventos.append([inicio, fim, r"{\an5\pos(540,%d)}" % alto + " ".join(palavras)])
    eventos.sort(key=lambda ev: ev[0])
    for k, (inicio, fim, texto) in enumerate(eventos):
        if k + 1 < len(eventos):
            fim = min(fim, eventos[k + 1][0])  # nunca duas legendas na tela ao mesmo tempo (palavras sobrepostas)
        if ate is not None:  # a legenda some quando o encerramento começa
            fim = min(fim, ate)
        if fim - inicio < 0.01:
            continue
        linhas.append("Dialogue: 0,%s,%s,Texto,,0,0,0,,%s" % (_tempo_ass(inicio), _tempo_ass(fim), texto))
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")


def montar_rapido(trecho, t0, dur, pls, grupos, titulo, estilo, saida, folha):
    """Via FFmpeg, só no plano gamer com facecam estável. Demais cenas usam o render anterior."""
    if len(pls) != 1 or pls[0]["pl"]["modo"] != "facecam" or estilo.get("layout") != "gamer":
        return False
    cap = cv2.VideoCapture(para_cv(trecho))
    W, H = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    if W < 1 or H < 1:
        return False
    rc = recortes(pls[0]["pl"], W, H, estilo)
    if "fade" not in rc:
        return False
    sx, sy, sw, sh, dx, dy, dw, dh = rc["topo"]
    gx, gy, gw, gh, _, gy_out, _, gh_out = rc["jogo"]
    if min(sw, sh, gw, gh, dw, dh) < 2:
        return False
    dur = max(0.2, dur)
    nitidez = float(estilo.get("nitidez_camera", 0))
    with tempfile.TemporaryDirectory(prefix="render-gamer-", dir=saida.parent) as td:
        pasta_tmp = Path(td)
        arquivo_ass = pasta_tmp / "legendas.ass"
        fim_card = encerramento(estilo, dur)
        _salvar_ass(grupos, estilo, arquivo_ass, ate=fim_card["inicio"] if fim_card else None)
        # máscara do gradiente: facecam opaca no topo, sumindo suave sobre a gameplay
        Image.fromarray((mascara_fade(dw, dh, rc["fade"]) * 255).astype(np.uint8), mode="L").save(pasta_tmp / "mascara.png")
        partes = [
            "[0:v]fps=%d,split=2[face0][jogo0]" % FPS,
            "[jogo0]crop=%d:%d:%d:%d,scale=%d:%d:flags=lanczos,setsar=1,pad=%d:%d:0:%d:black[jogo]" % (gw, gh, gx, gy, L, gh_out, L, A, gy_out),
            "[face0]crop=%d:%d:%d:%d,scale=%d:%d:flags=lanczos,setsar=1%s,format=rgba[facergba]" % (
                sw, sh, sx, sy, dw, dh, (",unsharp=7:7:%.2f:7:7:0" % nitidez) if nitidez > 0 and dw > sw else ""),
            "[1:v]format=gray[mascara]",
            "[facergba][mascara]alphamerge[face]",
            "[jogo][face]overlay=%d:%d:shortest=1:format=auto[tela]" % (dx, dy),
        ]
        entradas = ["-ss", "%.3f" % t0, "-t", "%.3f" % dur, "-i", str(Path(trecho).resolve()),
                    "-loop", "1", "-framerate", str(FPS), "-i", "mascara.png"]
        n_entrada = 2
        if fim_card:
            # encerramento: o vídeo desfoca e escurece (entrando em 0,4 s), só nos últimos segundos
            te = fim_card["inicio"]
            liga = "enable='gte(t\\,%.3f)'" % (te - 0.1)
            partes += ["[tela]split=2[base][desf0]",
                       "[desf0]gblur=sigma=%.1f:%s,colorchannelmixer=rr=%.3f:gg=%.3f:bb=%.3f:%s,format=yuva420p,"
                       "fade=t=in:st=%.3f:d=0.4:alpha=1[desf]" % (fim_card["blur"], liga, fim_card["escurecer"],
                                                                fim_card["escurecer"], fim_card["escurecer"], liga, te),
                       "[base][desf]overlay=0:0:format=auto[tela2]"]
            partes.append("[tela2]format=yuv420p,ass=filename=legendas.ass[legendado]")
        else:
            partes.append("[tela]format=yuv420p,ass=filename=legendas.ass[legendado]")
        ultimo = "[legendado]"
        if estilo.get("titulo") and titulo:
            titulo_png = pasta_tmp / "titulo.png"
            Image.fromarray(imagem_do_titulo(titulo, estilo), mode="RGBA").save(titulo_png)
            entradas += ["-loop", "1", "-framerate", str(FPS), "-i", "titulo.png"]
            so_antes = (":enable='lt(t\\,%.3f)'" % fim_card["inicio"]) if fim_card else ""
            partes.append("[legendado][%d:v]overlay=(W-w)/2:%d-h/2:shortest=1%s[titulado]" % (n_entrada, rc["emenda"], so_antes))
            n_entrada += 1
            ultimo = "[titulado]"
        if fim_card:
            # o card entra com fade + zoom leve (ease-out) e fica centrado em centro_y
            Image.fromarray(card_rgba(fim_card), mode="RGBA").save(pasta_tmp / "card.png")
            entradas += ["-loop", "1", "-framerate", str(FPS), "-i", "card.png"]
            ch, cw = card_rgba(fim_card).shape[:2]
            e = "(1-pow(1-clip((t-%.3f)/%.3f\\,0\\,1)\\,3))" % (fim_card["inicio"], fim_card["entrada"])
            z = "(%.3f+%.3f*%s)" % (fim_card["zoom_de"], 1 - fim_card["zoom_de"], e)
            partes.append("[%d:v]format=rgba,scale=w='trunc(%d*%s/2)*2':h='trunc(%d*%s/2)*2':eval=frame,"
                          "fade=t=in:st=%.3f:d=%.3f:alpha=1[card]" % (n_entrada, cw, z, ch, z, fim_card["inicio"], fim_card["entrada"]))
            partes.append("%s[card]overlay=x='(W-w)/2':y='%d-h/2':shortest=1:enable='gte(t\\,%.3f)'[comcard]" %
                          (ultimo, fim_card["centro_y"], fim_card["inicio"]))
            n_entrada += 1
            ultimo = "[comcard]"
        if estilo.get("barra"):
            # Barra de progresso igual à do modo compatível: entra pela esquerda e enche a largura até o fim do corte.
            alt_barra = int(estilo.get("altura_barra", 12))
            partes.append("color=c=%s:s=%dx%d:r=%d[barra]" %
                          (estilo.get("cor_barra", estilo["cor_destaque"]).replace("#", "0x"), L, alt_barra, FPS))
            partes.append("%s[barra]overlay=x='-W+W*min(1\\,(t+%.4f)/%.4f)':y=%d:shortest=1[final]" %
                          (ultimo, 1.0 / FPS, dur, A - alt_barra))
            ultimo = "[final]"
        som = "loudnorm=I=%d:TP=-1.5:LRA=11" % estilo["volume"]
        if fim_card and fim_card["fade_saida"] > 0:
            fs = fim_card["fade_saida"]
            partes.append("%sfade=t=out:st=%.3f:d=%.3f[saida]" % (ultimo, dur - fs, fs))
            ultimo = "[saida]"
            som += ",afade=t=out:st=%.3f:d=%.3f" % (dur - fs, fs)
        comando = [comum.ffmpeg(), "-hide_banner", "-v", "error", "-y"] + entradas + [
            "-filter_complex", ";".join(partes), "-map", ultimo, "-map", "0:a:0",
            "-af", som,
            "-t", "%.3f" % dur, "-r", str(FPS)] + codificador(estilo) + [
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "%dk" % estilo.get("audio_kbps", 256), "-ar", "48000",
            "-movflags", "+faststart", str(saida.resolve())]
        r = subprocess.run(comando, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=td)
        if r.returncode:
            print("    FFmpeg rápido indisponível (%s); usando modo compatível." % (r.stderr or "erro")[-320:], flush=True)
            saida.unlink(missing_ok=True)
            return False
    # Gera a folha de conferência sem recodificar o vídeo final.
    cap = cv2.VideoCapture(para_cv(saida))
    duracao = cap.get(cv2.CAP_PROP_FRAME_COUNT) / max(1, cap.get(cv2.CAP_PROP_FPS))
    imagens = []
    for i in range(6):
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0, duracao * (i + 0.5) / 6) * 1000)
        ok, quadro = cap.read()
        if ok:
            imagens.append(cv2.resize(quadro, (360, 640), interpolation=cv2.INTER_AREA))
    cap.release()
    if imagens:
        gravar_jpg(folha, np.hstack(imagens), 88)
    return True

def folha_previa(quadros, t_live, cada, destino, n=6):
    """trechos/NN-previa.jpg: seis quadros da fonte espalhados pelo momento, com o horário da live em cada um,
    para conferir a ação ANTES de gastar tempo com o render."""
    if not quadros:
        return
    idx = sorted({int(round(i * (len(quadros) - 1) / float(max(1, n - 1)))) for i in range(n)})
    minis = []
    for i in idx:
        q = quadros[i]
        h, w = q.shape[:2]
        mini = cv2.resize(q, (480, max(2, int(480 * h / float(w)))), interpolation=cv2.INTER_AREA)
        texto = comum.relogio(t_live + i * cada)
        org = (mini.shape[1] - 130, mini.shape[0] - 14)  # canto de baixo, longe da facecam
        cv2.putText(mini, texto, org, cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(mini, texto, org, cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
        minis.append(mini)
    altura = min(m.shape[0] for m in minis)
    minis = [m[:altura] for m in minis]
    linhas = [np.hstack(minis[i:i + 3] + [np.zeros_like(minis[0])] * (3 - len(minis[i:i + 3]))) for i in range(0, len(minis), 3)]
    gravar_jpg(destino, np.vstack(linhas), 85)


def palavras_gravadas(frases, ini, fim):
    """As palavras com tempo próprio que o ouvir.py já guardou (transcrição versão 3), relativas a `ini`.
    None quando a transcrição é antiga e não tem palavra por palavra."""
    if not any("p" in f for f in frases):
        return None
    out = []
    for f in frases:
        if f["e"] <= ini or f["s"] >= fim:
            continue
        for w in f.get("p", []):
            meio = (w["s"] + w["e"]) / 2.0
            if ini <= meio < fim:
                out.append({"w": w["w"], "s": round(max(0.0, w["s"] - ini), 2), "e": round(min(fim, w["e"]) - ini, 2)})
    return out


def palavras_da_transcricao(frases, ini, fim):
    """Palavras com tempo (relativo a `ini`) tiradas das frases da transcrição da live, quando o trecho não tem as suas.
    Cada frase espalha as palavras por igual dentro do seu tempo."""
    out = []
    for f in frases:
        if f["e"] <= ini or f["s"] >= fim:
            continue
        ws = f["t"].split()
        if not ws:
            continue
        s, e = max(f["s"], ini), min(f["e"], fim)
        passo = max(0.12, (e - s) / len(ws))
        for i, w in enumerate(ws):
            ws_ini = s + i * passo
            if ws_ini >= fim:
                break
            out.append({"w": w, "s": round(ws_ini - ini, 2), "e": round(min(fim, ws_ini + passo) - ini, 2)})
    return out


def juntar_numeros(palavras):
    out = []
    for w in palavras:
        if out and re.match(r"^[.,]\d", w["w"]):  # "209" + ".8": one number
            out[-1] = {"w": out[-1]["w"] + w["w"], "s": out[-1]["s"], "e": w["e"]}
        else:
            out.append(w)
    return out


def comentarios(pasta, n, lingua, estilo):
    """The person's own recordings for cut n: comentarios/NN-abre.* plays before the cut, comentarios/NN-fecha.* after it."""
    achados = {}
    for lado in ("abre", "fecha"):
        arqs = [p for p in sorted((pasta / "comentarios").glob("%02d-%s.*" % (n, lado))) if p.suffix.lower() in
                (".m4a", ".mp3", ".wav", ".aac", ".ogg", ".opus", ".flac", ".aiff", ".aif", ".mp4", ".mov", ".webm")]
        if not arqs:
            continue
        som = comum.audio(arqs[0])
        if len(som) < comum.TAXA * 0.5:
            continue
        segs, _ = comum.transcrever(som, lingua=lingua, palavras=True)
        palavras = juntar_numeros([w for s in segs for w in s.get("p", [])])
        achados[lado] = {"arquivo": arqs[0], "dur": len(som) / float(comum.TAXA) + 0.25, "grupos": grupos_de_legenda(palavras, estilo),
                         "texto": " ".join(w["w"] for w in palavras)}
    return achados


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pasta")
    ap.add_argument("--so", type=int, default=0, help="só o momento com este número")
    ap.add_argument("--cookies", default="")
    ap.add_argument("--camera", default="", help="a caixa da câmera na tela da live: x,y,largura,altura")
    ap.add_argument("--modo", default="", choices=["", "facecam", "cheia", "sem"])
    ap.add_argument("--layout", choices=["gamer", "classico"], default="", help="gamer prioriza gameplay e preserva a facecam")
    ap.add_argument("--fonte-max-altura", type=int, default=2160, help="resolução máxima da fonte remota (padrão: a melhor, até 4K)")
    ap.add_argument("--fps", type=int, choices=[30, 60], default=30, help="30 = rápido; 60 = mais fluidez")
    ap.add_argument("--whisper-trecho", action="store_true",
                    help="transcreve cada trecho de novo para a legenda (padrão: usa as palavras já gravadas pelo ouvir.py)")
    ap.add_argument("--previa", action="store_true",
                    help="só baixa os trechos e monta trechos/NN-previa.jpg (6 quadros do momento) para conferir antes do render")
    ap.add_argument("--gpu", action="store_true", help="codifica na placa de vídeo (AMD AMF, NVIDIA NVENC ou Intel QSV), bem mais rápido")
    a = ap.parse_args()
    global FPS
    FPS = a.fps
    pasta = Path(a.pasta)
    info = comum.ler_json(pasta / "info.json")
    dado = comum.ler_json(pasta / "momentos-conferidos.json")
    if not info or not dado:
        sys.exit("Rode antes o ouvir.py e o conferir.py nessa pasta.")
    estilo = dict(ESTILO)
    proprio = dict(comum.ler_json(pasta / "estilo.json", {}) or {})
    if "encerramento" in proprio:  # false desliga; um objeto muda só as chaves que trouxer
        enc = proprio.pop("encerramento")
        estilo["encerramento"] = dict(estilo.get("encerramento") or {}, **enc) if isinstance(enc, dict) else {"ativo": bool(enc)}
    estilo.update(proprio)
    if a.layout:
        estilo["layout"] = a.layout
    if a.gpu:
        estilo["gpu"] = True
    if estilo.get("layout") not in ("gamer", "classico"):
        sys.exit("layout inválido: escolha gamer ou classico")
    # na pasta da hora (hora-N/) o áudio fica na pasta da live, um nível acima
    fontes_audio = [p for d in (pasta, pasta.parent) for p in d.glob("audio.*") if p.suffix not in (".part", ".ytdl")]
    if info.get("arquivo_audio") and Path(info["arquivo_audio"]).exists():
        fontes_audio.insert(0, Path(info["arquivo_audio"]))
    audio_da_live = Path(info["arquivo_local"]) if info.get("arquivo_local") else (fontes_audio[0] if fontes_audio else None)
    if audio_da_live is None or not audio_da_live.exists():
        sys.exit("Não achei o áudio da live. Rode ouvir.py primeiro.")
    transcricao = comum.ler_json(pasta / "transcricao.json")
    lingua = transcricao.get("lingua")
    frases_live = transcricao.get("frases", [])
    trechos, cortes = pasta / "trechos", pasta / "shorts"
    trechos.mkdir(exist_ok=True)
    cortes.mkdir(exist_ok=True)
    tempos = comum.Tempos(pasta)
    escolhidos = [m for m in dado["momentos"] if (m["n"] == a.so if a.so else m.get("manter"))]
    if not escolhidos:
        sys.exit("Nenhum momento marcado para o corte.")
    forcada = [int(v) for v in a.camera.split(",")] if a.camera else None
    rostos = Rostos()
    tempos.comeca("cortar")
    feitos = comum.ler_json(cortes / "cortes.json", [])

    # first pass: download, align and look for the camera in every clip, so clips of one stream can agree on it
    prontos = []
    for m in escolhidos:
        n = m["n"]
        print("momento %d: %s a %s (%s)" % (n, m["inicio"], m["fim"], m.get("titulo", "")), flush=True)
        trecho = baixar_trecho(info, trechos, n, m["inicio_s"], m["fim_s"], a.cookies, a.fonte_max_altura)
        pedido = max(0.0, m["inicio_s"] - MARGEM)
        comeco, som, certeza = alinhar(trecho, audio_da_live, pedido)
        t0 = m["inicio_s"] - comeco
        dur = m["fim_s"] - m["inicio_s"]
        if t0 < 0 or t0 + dur > len(som) / comum.TAXA + 0.5:
            t0, certeza = min(MARGEM, m["inicio_s"]), 0.0
        print("    trecho baixado; começa em %s da live (%s)" % (comum.relogio(comeco, True), "som conferido" if certeza >= 6 else "sem conferir pelo som"))
        cada = max(0.8, dur / 36.0)  # no máximo ~37 quadros na análise; memória sob controle
        quadros, achados = amostrar(trecho, t0, dur, rostos, cada)
        if not quadros:
            sys.exit("Não consegui ler o vídeo do trecho %d." % n)
        gravar_jpg(trechos / ("%02d-quadro.jpg" % n), quadros[len(quadros) // 2], 90)
        folha_previa(quadros, m["inicio_s"], cada, trechos / ("%02d-previa.jpg" % n))
        pls = planos(quadros, achados, a.modo, forcada, cada)
        del quadros
        prontos.append({"m": m, "trecho": trecho, "t0": t0, "dur": dur, "som": som, "pls": pls})
    com_camera = [s["pl"]["camera"] for p in prontos for s in p["pls"] if s["pl"]["modo"] == "facecam"]
    if com_camera and not forcada and not a.modo:
        # a webcam não muda de lugar na live: as horas anteriores ajudam a achar a câmera inteira
        ref_live = pasta.parent / "camera-live.json" if (pasta.parent / "audio.mp4").exists() or pasta.name.startswith("hora-") else None
        vistas = (comum.ler_json(ref_live, {}) or {}).get("caixas", []) if ref_live else []
        comum_ = caixa_dominante(com_camera + vistas)
        if ref_live:
            comum.escrever_json(ref_live, {"caixa": comum_, "caixas": (vistas + [comum_])[-12:]})
        for p in prontos:
            for s in p["pls"]:
                if s["pl"]["modo"] == "sem":  # no face found here, but the stream has a camera: use its place
                    s["pl"] = {"modo": "facecam", "camera": comum_, "rosto": None}
                elif s["pl"]["modo"] == "facecam" and (dentro(s["pl"]["camera"], comum_) or sobre(s["pl"]["camera"], comum_) >= 0.5):
                    # detecção pegou só um pedaço da webcam: usa a câmera inteira (mesma proporção do OBS, menos zoom)
                    s["pl"] = dict(s["pl"], camera=list(comum_))
    comum.escrever_json(pasta / "camera.json", {str(p["m"]["n"]): [dict(s["pl"], de=s["de"]) for s in p["pls"]] for p in prontos})
    if a.previa:
        print("\nPrévia pronta (nada foi renderizado). Abra cada uma e confira se a ação prometida aparece:")
        for p in prontos:
            print("  %s  %s" % (trechos / ("%02d-previa.jpg" % p["m"]["n"]), p["m"].get("titulo", "")))
        print("Depois rode o cortar.py sem --previa (os trechos já baixados são reaproveitados).")
        return
    # second pass: the words and the clip
    for p in prontos:
        m, n = p["m"], p["m"]["n"]
        gravadas = None if a.whisper_trecho else palavras_gravadas(frases_live, m["inicio_s"], m["fim_s"])
        if gravadas is not None:
            # a transcrição da hora já tem o tempo de cada palavra: não precisa rodar o Whisper de novo
            palavras = juntar_numeros(gravadas)
            reserva = []
        else:
            a0 = int(p["t0"] * comum.TAXA)
            segs, _ = comum.transcrever(p["som"][a0:a0 + int(p["dur"] * comum.TAXA)], lingua=lingua, palavras=True)
            palavras = juntar_numeros([w for s in segs for w in s.get("p", [])])
            reserva = palavras_da_transcricao(frases_live, m["inicio_s"], m["fim_s"])
        if len(reserva) >= 8 and len(palavras) < 0.4 * len(reserva):
            # o Whisper do trecho perdeu a fala (às vezes só pega o NPC): usa a transcrição da hora,
            # com as palavras distribuídas dentro do tempo de cada frase
            print("    legenda: a transcrição do trecho veio com %d palavras e a da hora tem %d; usando a da hora"
                  % (len(palavras), len(reserva)), flush=True)
            palavras = reserva
        grupos = grupos_de_legenda(palavras, estilo)
        coment = comentarios(pasta, n, lingua, estilo)
        base = "%02d-%s" % (n, nome_de_arquivo(m.get("titulo", "")))
        if coment:
            base += "-comentado"
        # Versões novas não sobrescrevem exports que a pessoa já avaliou.
        stem = base
        v = 2
        while (cortes / (base + ".mp4")).exists():
            base = "%s-v%d" % (stem, v)
            v += 1
        saida = cortes / (base + ".mp4")
        modos = " + ".join(dict.fromkeys(s["pl"]["modo"] for s in p["pls"]))
        folha = cortes / (base + "-conferir.jpg")
        ok = False
        if not coment:
            ok = montar_rapido(p["trecho"], p["t0"], p["dur"], p["pls"], grupos, m.get("titulo", ""), estilo, saida, folha)
        if not ok:
            ok = montar(p["trecho"], p["t0"], p["dur"], p["pls"], grupos, m.get("titulo", ""), estilo, saida, folha, coment)
        if not ok:
            sys.exit("O ffmpeg não fechou o corte %d." % n)
        link = ("%s (início: %s)" % (info["link"], m["inicio"])) if info.get("arquivo_local") else (
            info["link"] + ("&" if "?" in info["link"] else "?") + "t=%ds" % int(m["inicio_s"]))
        meu = "".join("\n\nO SEU COMENTÁRIO (%s)\n%s" % ("antes" if lado == "abre" else "depois", coment[lado]["texto"]) for lado in ("abre", "fecha") if lado in coment)
        (cortes / (base + ".txt")).write_text(
            "TÍTULO\n%s\n\nLEGENDA DO POST\n%s\n\nHASHTAGS\n%s\n\nDE ONDE VEIO\n%s, %s a %s\n%s\n\nO QUE É DITO\n%s%s\n" % (
                m.get("titulo", ""), m.get("legenda", ""), " ".join(m.get("hashtags", [])), info["canal"], m["inicio"], m["fim"], link,
                " ".join(w["w"] for w in palavras), meu), encoding="utf-8")
        total_s = p["dur"] + sum(c["dur"] for c in coment.values())
        feitos = [f for f in feitos if f["arquivo"] != saida.name]
        feitos.append({"n": n, "arquivo": saida.name, "comentario": sorted(coment), "titulo": m.get("titulo", ""), "inicio": m["inicio"], "fim": m["fim"],
                       "duracao": round(total_s, 1), "modo": modos, "nota": m.get("nota"), "link": link})
        print("    corte pronto: %s (%.0f s, %s, %d palavras%s)" % (saida.name, total_s, modos, len(palavras),
              ", com o seu comentário " + " e ".join("antes" if x == "abre" else "depois" for x in sorted(coment)) if coment else ""), flush=True)
    comum.escrever_json(cortes / "cortes.json", sorted(feitos, key=lambda f: f["n"]))
    levou = tempos.termina()
    print("\n%d cortes em %s: %s" % (len(prontos), comum.duracao_falada(levou), cortes))
    print("Abra cada NN-...-conferir.jpg e veja: a câmera inteira em cima, o jogo embaixo, o título e a legenda legíveis.")


if __name__ == "__main__":
    main()
