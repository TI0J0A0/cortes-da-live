"""Hook UserPromptSubmit: avisa quando a mensagem traz um link de live já processado.

Procura links da Twitch, YouTube e Kick na mensagem e compara com as lives
já existentes em lives/<id>/ (pelo id da pasta e pelo "link" do info.json).
Não bloqueia nada: só mostra um aviso ao usuário e informa o Claude.
"""
import json
import os
import re
import sys
from pathlib import Path

sys.stdin.reconfigure(encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")

PADROES = [
    # Twitch: twitch.tv/videos/123  (yt-dlp usa id "v123")
    (re.compile(r"twitch\.tv/(?:[^/\s]+/)?(?:videos|v)/(\d+)", re.I), lambda m: "v" + m.group(1)),
    # YouTube: watch?v=ID, youtu.be/ID, /live/ID, /shorts/ID
    (re.compile(r"(?:youtube\.com/(?:watch\?(?:[^\s]*&)?v=|live/|shorts/)|youtu\.be/)([A-Za-z0-9_-]{11})", re.I),
     lambda m: m.group(1)),
    # Kick: kick.com/canal/videos/UUID
    (re.compile(r"kick\.com/[^/\s]+/videos/([A-Za-z0-9-]+)", re.I), lambda m: m.group(1)),
]


def ids_do_texto(texto):
    achados = []
    for padrao, conv in PADROES:
        for m in padrao.finditer(texto or ""):
            achados.append((conv(m), m.group(0)))
    return achados


def lives_existentes(raiz):
    """Mapa id -> dados da live, a partir de lives/*/info.json (ou hora-N/info.json)."""
    mapa = {}
    pasta = raiz / "lives"
    if not pasta.is_dir():
        return mapa
    for live in pasta.iterdir():
        if not live.is_dir():
            continue
        infos = [live / "info.json"] + sorted(live.glob("hora-*/info.json"))
        info = {}
        for arq in infos:
            if arq.is_file():
                try:
                    info = json.loads(arq.read_text(encoding="utf-8"))
                    break
                except Exception:
                    pass
        horas = sorted(p.name for p in live.glob("hora-*") if p.is_dir())
        entregues = sorted(p.parent.name for p in live.glob("hora-*/entrega.json"))
        dados = {"pasta": live.name, "info": info, "horas": horas, "entregues": entregues}
        chaves = {live.name, str(info.get("id") or "")}
        for padrao, conv in PADROES:
            m = padrao.search(str(info.get("link") or ""))
            if m:
                chaves.add(conv(m))
        for c in chaves:
            if c:
                mapa[c] = dados
    return mapa


def main():
    try:
        entrada = json.load(sys.stdin)
    except Exception:
        return
    achados = ids_do_texto(entrada.get("prompt", ""))
    if not achados:
        return
    raiz = Path(os.environ.get("CLAUDE_PROJECT_DIR") or entrada.get("cwd") or ".")
    # sobe até achar a pasta do projeto (a que tem lives/)
    for cand in [raiz, *raiz.parents, Path(__file__).resolve().parents[2]]:
        if (cand / "lives").is_dir():
            raiz = cand
            break
    mapa = lives_existentes(raiz)

    avisos = []
    vistos = set()
    for vid, link in achados:
        if vid in vistos or vid not in mapa:
            continue
        vistos.add(vid)
        d = mapa[vid]
        titulo = d["info"].get("titulo") or "(sem título)"
        horas = ", ".join(d["horas"]) or "nenhuma hora processada"
        entregues = ", ".join(d["entregues"]) or "nenhuma"
        avisos.append(
            f"⚠️ LINK REPETIDO: {link}\n"
            f"   Essa live já foi processada antes (lives/{d['pasta']}).\n"
            f"   Título: {titulo}\n"
            f"   Horas processadas: {horas} | Entregues: {entregues}"
        )
    if not avisos:
        return

    texto = "\n".join(avisos)
    print(json.dumps({
        "systemMessage": texto,
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": (
                texto + "\n\nAvise o usuário logo no começo da resposta que esse link de live já foi "
                "processado e pergunte se ele quer reprocessar mesmo assim antes de baixar ou cortar de novo."
            ),
        },
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
