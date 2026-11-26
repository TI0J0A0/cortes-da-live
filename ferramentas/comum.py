"""O que as ferramentas dividem: o ambiente, o ffmpeg, o yt-dlp, o Whisper e os tempos."""
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

CASA = Path(os.environ.get("CORTES_CASA", str(Path.home() / ".cortes-de-live")))
AMBIENTE = CASA / "ambiente"
MODELOS = CASA / "modelos"
SKILL = Path(__file__).resolve().parent.parent
TAXA = 16000  # samples per second of everything we analyse
WINDOWS = os.name == "nt"
PYTHON = "python" if WINDOWS else "python3"  # the command a person types to start a tool

# Windows: the console and the files default to an old code page. Everything here reads and writes UTF-8,
# and every program started from here (the environment's Python, yt-dlp) does the same.
os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"
for _saida in (sys.stdout, sys.stderr):
    try:
        _saida.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def python_do_ambiente():
    return AMBIENTE / ("Scripts/python.exe" if os.name == "nt" else "bin/python3")


def no_ambiente():
    """Run this same command inside the skill's own Python environment."""
    py = python_do_ambiente()
    if not py.exists():
        sys.exit("Falta preparar o computador. Rode: %s \"%s\"" % (PYTHON, SKILL / "ferramentas" / "preparar.py"))
    fora = Path(sys.prefix).resolve() != AMBIENTE.resolve()
    if fora or (WINDOWS and not sys.flags.utf8_mode):  # on Windows also start again in UTF-8 mode
        sys.exit(subprocess.call([str(py)] + sys.argv))


def chip_apple():
    return sys.platform == "darwin" and platform.machine() == "arm64"


def motor():
    """Which Whisper this computer uses: mlx-whisper on a Mac with an Apple chip, faster-whisper everywhere else
    (Windows, a Mac with an Intel chip, Linux). CORTES_MOTOR=faster or mlx forces one."""
    pedido = os.environ.get("CORTES_MOTOR", "")
    if pedido in ("mlx", "faster"):
        return pedido
    return "mlx" if chip_apple() else "faster"


def ffmpeg():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        sys.exit("ffmpeg não encontrado. Rode de novo o preparar.py.")


def ytdlp(*args, cookies="", captura=True, tempo=None):
    """Call yt-dlp from this environment. Returns the finished process."""
    cmd = [sys.executable, "-m", "yt_dlp", "--no-warnings", "--ffmpeg-location", ffmpeg()]
    if cookies:
        cmd += ["--cookies-from-browser", cookies]
    cmd += list(args)
    # YouTube needs a JavaScript runtime: the environment brings its own deno, in the folder of its Python
    amb = dict(os.environ, PATH=str(python_do_ambiente().parent) + os.pathsep + os.environ.get("PATH", ""))
    try:
        return subprocess.run(cmd, capture_output=captura, text=True, encoding="utf-8", errors="replace", timeout=tempo, env=amb)
    except subprocess.TimeoutExpired as e:
        return subprocess.CompletedProcess(cmd, 124, e.stdout or "", "tempo esgotado")


def segundos(t):
    """'1:02:03', '62:03' or 3723 -> seconds."""
    if isinstance(t, (int, float)):
        return float(t)
    partes = [float(p) for p in str(t).strip().split(":")]
    s = 0.0
    for p in partes:
        s = s * 60 + p
    return s


def relogio(s, decimos=False):
    s = max(0.0, float(s))
    h, r = divmod(int(s), 3600)
    m, seg = divmod(r, 60)
    base = "%d:%02d:%02d" % (h, m, seg)
    return base + (".%d" % int((s % 1) * 10)) if decimos else base


def duracao_falada(s):
    s = int(round(s))
    h, r = divmod(s, 3600)
    m, seg = divmod(r, 60)
    if h:
        return "%d h %02d min" % (h, m)
    if m:
        return "%d min %02d s" % (m, seg)
    return "%d s" % seg


# Palavras muito comuns em inglês que quase não existem no português falado (sem "a", "no", "do", "me", "se"...).
INGLES = set("""the you i i'm you're it's that's don't can't won't what this that it is are was were be been have has
get got just know want need gonna wanna yeah okay ok oh hey guys man dude bro fuck fucking shit damn with for of on at
they he she we my your our his her their them him us here there now why how where who when will would could should
right look come go going let's please thank thanks sorry wait stop help really something nothing everything""".split())


def parece_fala_do_jogo(texto, minimo=3, fracao=0.4):
    """True quando a frase parece diálogo do jogo em inglês (personagem, cinemática, rádio), não fala do streamer.
    Pista barata, só pelo texto: o turbo costuma escrever a fala do jogo em inglês. Frases curtas ficam de fora."""
    palavras = re.findall(r"[a-zA-Z']+", str(texto or "").lower())
    if len(palavras) < minimo:
        return False
    return sum(p in INGLES for p in palavras) / float(len(palavras)) >= fracao


# Marcas de fala espontânea em português (gíria, interjeição): o jogo, mesmo traduzido pelo Whisper, não fala assim.
GIRIAS = set("""mano manos caraca véi vei velho né tá tô pô po nossa gente cara bagulho maluco rapaziada vamo bora eita
oxe uai irmão kkk kkkk porra caralho mds poxa putz égua olha tipo""".split())


def tem_giria(texto):
    """True quando a frase tem marca de fala do streamer em português (\"mano\", \"caraca\", \"véi\", \"né\"...)."""
    return any(p in GIRIAS for p in re.findall(r"[\wáéíóúâêôãõç]+", str(texto or "").lower()))


def ler_json(p, padrao=None):
    p = Path(p)
    if not p.exists():
        return padrao
    return json.loads(p.read_text(encoding="utf-8"))


def escrever_json(p, dado):
    Path(p).write_text(json.dumps(dado, ensure_ascii=False, indent=1), encoding="utf-8")


class Trava:
    """Só um processo por vez faz a tarefa `nome` na pasta (ex.: baixar o áudio da live enquanto duas horas rodam
    em paralelo). Quem chega depois espera; uma trava velha (processo que morreu) é ignorada depois de `velha` s."""

    def __init__(self, pasta, nome, espera=3 * 3600, velha=3 * 3600):
        self.arquivo = Path(pasta) / (".trava-%s" % nome)
        self.espera, self.velha, self.dono = espera, velha, False

    def __enter__(self):
        limite, avisou = time.time() + self.espera, False
        while True:
            try:
                fd = os.open(str(self.arquivo), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                self.dono = True
                return self
            except FileExistsError:
                try:
                    if time.time() - self.arquivo.stat().st_mtime > self.velha:
                        self.arquivo.unlink(missing_ok=True)
                        continue
                except FileNotFoundError:
                    continue
                if time.time() > limite:
                    raise TimeoutError("esperei demais pela trava %s" % self.arquivo)
                if not avisou:
                    print("    esperando outro processo terminar (%s)..." % self.arquivo.name, flush=True)
                    avisou = True
                time.sleep(2)

    def __exit__(self, *_):
        if self.dono:
            self.arquivo.unlink(missing_ok=True)


class Tempos:
    """How long each step took, kept in tempos.json next to the stream."""

    def __init__(self, pasta):
        self.arquivo = Path(pasta) / "tempos.json"
        self.dado = ler_json(self.arquivo, {})
        self._t = None
        self._nome = None

    def comeca(self, nome):
        self._nome, self._t = nome, time.time()

    def termina(self):
        self.dado[self._nome] = round(time.time() - self._t, 1)
        escrever_json(self.arquivo, self.dado)
        return self.dado[self._nome]


def audio_em_blocos(arquivo, inicio=None, duracao=None, bloco=TAXA * 30, faixa=None):
    """Decode any audio or video file to 16 kHz mono and yield it in pieces (numpy int16).
    faixa: número da faixa de áudio (0, 1, 2...) numa gravação do OBS com várias faixas (ex.: só o microfone)."""
    import numpy as np
    cmd = [ffmpeg(), "-v", "error", "-nostdin"]
    if inicio is not None:
        cmd += ["-ss", "%.3f" % max(0.0, inicio)]
    cmd += ["-i", str(arquivo)]
    if faixa is not None:
        cmd += ["-map", "0:a:%d" % int(faixa)]
    if duracao is not None:
        cmd += ["-t", "%.3f" % duracao]
    cmd += ["-vn", "-ac", "1", "-ar", str(TAXA), "-f", "s16le", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        while True:
            dado = p.stdout.read(bloco * 2)
            if not dado:
                break
            yield np.frombuffer(dado[: len(dado) // 2 * 2], dtype=np.int16)
    finally:
        p.stdout.close()
        p.wait()


def audio(arquivo, inicio=None, duracao=None, faixa=None):
    import numpy as np
    partes = list(audio_em_blocos(arquivo, inicio, duracao, faixa=faixa))
    return np.concatenate(partes) if partes else np.zeros(0, dtype=np.int16)


_MOTOR = {}


def modelo_whisper(nome):
    """O faster-whisper carregado uma vez por execução (no processador)."""
    from faster_whisper import WhisperModel
    if nome not in _MOTOR:
        # on the processor, always: a video card only works here with extra libraries that most computers do not have
        _MOTOR[nome] = WhisperModel(nome, device="cpu", compute_type="int8", cpu_threads=max(4, (os.cpu_count() or 8) // 2))
    return _MOTOR[nome]


def lingua_da_fala(amostras, modelo=None):
    """O idioma falado num pedaço de áudio (numpy int16 a 16 kHz): ("pt", 0.97), ("en", 0.88)...
    Serve para separar a fala do streamer (português) do diálogo do jogo (inglês): o Whisper com língua fixa em
    português TRADUZ a fala em inglês dos personagens, e ela vazaria na legenda. (None, 0.0) quando não dá para medir."""
    import numpy as np
    if amostras is None or len(amostras) < TAXA * 0.5 or motor() == "mlx":
        return None, 0.0
    try:
        som = amostras.astype(np.float32) / 32768.0
        lingua, prob, _ = modelo_whisper(modelo or os.environ.get("CORTES_MODELO_IDIOMA") or "small").detect_language(audio=som)
        return lingua, float(prob)
    except Exception:
        return None, 0.0


def modelo_padrao():
    """large-v3-turbo nos dois motores: em PT-BR com gíria de jogo erra muito menos que o small e, no processador,
    ainda roda ~6x mais rápido que o tempo real (1 h de live em ~10 min). CORTES_MODELO=small troca por velocidade."""
    return os.environ.get("CORTES_MODELO") or "large-v3-turbo"


def transcrever(amostras, lingua=None, palavras=False, modelo=None):
    """Whisper on this computer. amostras: numpy int16 at 16 kHz.
    Returns (segments, language); a segment is {"s", "e", "t"} plus "p": [{"w", "s", "e"}] when palavras is on."""
    import numpy as np
    som = amostras.astype(np.float32) / 32768.0
    modelo = modelo or modelo_padrao()
    try:
        if motor() != "mlx":
            raise ImportError("this computer uses faster-whisper")
        import mlx_whisper
        repo = modelo if "/" in modelo else "mlx-community/whisper-" + modelo
        r = mlx_whisper.transcribe(som, path_or_hf_repo=repo, language=lingua, word_timestamps=palavras,
                                   condition_on_previous_text=False, verbose=None)
        segs = []
        for s in r["segments"]:
            item = {"s": float(s["start"]), "e": float(s["end"]), "t": s["text"].strip()}
            if palavras:
                item["p"] = [{"w": w["word"].strip(), "s": float(w["start"]), "e": float(w["end"])} for w in s.get("words", [])]
            segs.append(item)
        return segs, r.get("language") or lingua
    except ImportError:
        pass
    achados, info = modelo_whisper(modelo).transcribe(som, language=lingua, word_timestamps=palavras,
                                              condition_on_previous_text=False, vad_filter=True)
    segs = []
    for s in achados:
        item = {"s": float(s.start), "e": float(s.end), "t": s.text.strip()}
        if palavras:
            item["p"] = [{"w": w.word.strip(), "s": float(w.start), "e": float(w.end)} for w in (s.words or [])]
        segs.append(item)
    return segs, info.language
