#!/usr/bin/env python3
"""Prepara o agendamento dos shorts no Metricool e arruma tudo depois que eles estão agendados.

O Metricool só é acessado pelo Claude (conector MCP). Este script faz o resto:

  1. planejar: escolhe horários livres, sobe os vídeos e monta os textos no padrão do canal.
     python agendar.py planejar "Shorts prontos para postar/<pasta da live>" --shorts "Hora 2 - 02" "Hora 5 - 03" \
         --agenda agenda.json --de 2026-11-26 --ate 2026-11-27 [--sem-subir]
       agenda.json = a lista de posts que o getScheduledPosts devolveu (os horários ocupados).
       Escreve plano-agendamento.json: para cada short, a data, o texto, os títulos do YouTube/TikTok, as tags,
       o comentário fixado e o link público do vídeo (litterbox.catbox.moe, 72 h; o Metricool copia o vídeo
       para o servidor dele no momento do agendamento, então o link pode expirar depois).
     O Claude manda cada item do plano para o createScheduledPost.

  2. concluir: depois de agendados, registra o texto postado no entrega.json (para o desempenho.py), apaga o vídeo
     e o .txt da pasta de entrega (o Metricool já tem a cópia) e refaz o LEIA-ME.txt da live.
     python agendar.py concluir plano-agendamento.json [--manter-arquivos]

Padrão de texto (memória do projeto): gancho em MAIÚSCULAS + emoji, a legenda com pergunta ao público, hashtags do
JOGO DA LIVE + #TiojoaoYT; título do YouTube "TÍTULO! emoji | <Jogo> #Shorts"; comentário fixado das lives.
Horários (fuso da marca, America/New_York): 10h, 16h, 18h; extras 13h, 21h; se o dia estiver cheio, 12h, 20h, 19h, 15h.
"""
import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comum  # noqa: E402

HORARIOS = [10, 16, 18, 13, 21, 12, 20, 19, 15]
FOLGA_MIN = 60  # minutos mínimos entre dois posts
COMENTARIO = "🔴 Lives TODOS OS DIAS na Twitch, Kick e YouTube!\n💬 Cola na próxima live e vem fazer parte da resenha! ❤️"
EMOJIS = [("ovni", "👽"), ("mistério", "👀"), ("susto", "😱"), ("terror", "😱"), ("boss", "🔥"), ("ação", "🔥"),
          ("jogada", "🔥"), ("bug", "💀"), ("falha", "💀"), ("erro", "💀"), ("debate", "👀"), ("história", "👀"),
          ("descoberta", "😳"), ("humor", "😂"), ("reação", "😂")]
JOGOS = {"#gta6": "GTA 6", "#gtavi": "GTA 6", "#phantombladezero": "Phantom Blade Zero"}


def emoji_do(tipo, hashtags):
    alvo = (str(tipo) + " " + " ".join(hashtags)).lower()
    for chave, e in EMOJIS:
        if chave in alvo:
            return e
    return "😂"


def jogo_do(hashtags):
    for h in hashtags:
        if h.lower() in JOGOS:
            return JOGOS[h.lower()]
    return None


def ocupados(agenda):
    """Horários já agendados, como datetime 'ingênuo' no fuso da marca."""
    lista = agenda.get("data", agenda) if isinstance(agenda, dict) else agenda
    out = []
    for p in lista or []:
        d = (p.get("publicationDate") or {}).get("dateTime")
        if d:
            out.append(dt.datetime.fromisoformat(d[:19]))
    return out


def horarios_livres(tomados, de, ate, quantos):
    """Os próximos `quantos` horários livres entre as datas `de` e `ate` (inclusive), no padrão do canal."""
    livres, tomados = [], list(tomados)
    dia = de
    while dia <= ate and len(livres) < quantos:
        for h in HORARIOS:
            quando = dt.datetime.combine(dia, dt.time(h))
            if quando < dt.datetime.now() + dt.timedelta(minutes=30):
                continue
            if all(abs((quando - t).total_seconds()) >= FOLGA_MIN * 60 for t in tomados):
                livres.append(quando)
                tomados.append(quando)
                if len(livres) >= quantos:
                    break
        dia += dt.timedelta(days=1)
    return sorted(livres)


def subir(arquivo):
    """Sobe o vídeo num host temporário e devolve o link público.

    Primeiro o litterbox (72 h); se ele falhar (fora do ar, 500/412), o uguu.se (3 h). O Metricool copia o vídeo
    no momento do agendamento, então 3 h bastam. O curl recebe uma cópia com nome ASCII: o litterbox recusa
    (412) nomes com acento."""
    import shutil
    import tempfile
    tmp = Path(tempfile.gettempdir()) / ("short-%d.mp4" % abs(hash(str(arquivo))))
    shutil.copyfile(arquivo, tmp)
    try:
        r = subprocess.run(["curl", "-s", "--max-time", "180", "-F", "reqtype=fileupload", "-F", "time=72h",
                            "-F", "fileToUpload=@%s" % tmp, "https://litterbox.catbox.moe/resources/internals/api.php"],
                           capture_output=True, text=True)
        link = (r.stdout or "").strip()
        if link.startswith("https://"):
            return link
        print("  litterbox falhou (%s); tentando uguu.se" % link[:60].replace("\n", " "))
        r = subprocess.run(["curl", "-s", "--max-time", "600", "-F", "files[]=@%s" % tmp, "https://uguu.se/upload"],
                           capture_output=True, text=True)
        try:
            link = json.loads(r.stdout)["files"][0]["url"]
        except Exception:
            link = ""
        if not link.startswith("https://"):
            sys.exit("Falhou o upload de %s: %s" % (arquivo, (r.stderr or r.stdout)[-300:]))
        return link
    finally:
        tmp.unlink(missing_ok=True)


def metadados(pasta_entrega, arquivo):
    """O item do short no entrega.json da live (título, tipo, legenda, hashtags) e o caminho desse entrega.json."""
    for entrega in Path("lives").glob("*/hora-*/entrega.json"):
        e = comum.ler_json(entrega, {}) or {}
        if Path(e.get("destino", "")).name != pasta_entrega.name:
            continue
        for s in e.get("shorts", []):
            if s.get("arquivo") == arquivo:
                return s, entrega
    return {}, None


def montar_post(s, arquivo, quando, link):
    titulo = s.get("titulo") or re.sub(r"^Hora \d+ - \d+ - ", "", Path(arquivo).stem)
    hashtags = s.get("hashtags") or ["#TiojoaoYT"]
    emoji = emoji_do(s.get("tipo", ""), hashtags)
    gancho = titulo.upper().rstrip("!?. ") + ("?! " if titulo.strip().endswith("?") else "! ") + emoji
    jogo = jogo_do(hashtags)
    texto = "%s\n\n%s\n\n%s" % (gancho, s.get("legenda", "").strip(), " ".join(hashtags))
    yt = "%s | %s #Shorts" % (gancho, jogo) if jogo else "%s #Shorts" % gancho
    tags = [jogo, jogo.replace("6", "VI") if jogo and "6" in jogo else None, (jogo + " Brasil") if jogo else None, "TiojoaoYT"]
    return {"arquivo": arquivo, "quando": quando.strftime("%Y-%m-%dT%H:%M:%S"), "fuso": "America/New_York",
            "texto": texto, "titulo_youtube": yt[:100], "titulo_tiktok": "%s %s" % (titulo.rstrip("!?. "), emoji),
            "tags_youtube": [t for t in tags if t], "comentario_fixado": COMENTARIO, "midia": link,
            "redes": ["instagram", "tiktok", "youtube"]}


def planejar(a):
    pasta = Path(a.pasta)
    videos = sorted(pasta.glob("*.mp4"))
    escolhidos = []
    for pedido in a.shorts:
        achou = [v for v in videos if v.stem.startswith(pedido) or pedido.lower() in v.stem.lower()]
        if len(achou) != 1:
            sys.exit("'%s' bateu com %d vídeos em %s; seja mais específico." % (pedido, len(achou), pasta))
        escolhidos.append(achou[0])
    agenda = comum.ler_json(a.agenda, []) if a.agenda else []
    de = dt.date.fromisoformat(a.de) if a.de else dt.date.today()
    ate = dt.date.fromisoformat(a.ate) if a.ate else de + dt.timedelta(days=7)
    horas = horarios_livres(ocupados(agenda), de, ate, len(escolhidos))
    if len(horas) < len(escolhidos):
        sys.exit("Só achei %d horários livres entre %s e %s para %d shorts." % (len(horas), de, ate, len(escolhidos)))
    plano = []
    for video, quando in zip(escolhidos, horas):
        s, _ = metadados(pasta, video.name)
        link = "" if a.sem_subir else subir(video)
        plano.append(montar_post(s, video.name, quando, link))
        print("%s  %s  %s" % (quando.strftime("%d/%m %H:%M"), video.name, link or "(sem upload)"))
    comum.escrever_json(a.saida, {"pasta": str(pasta.resolve()), "posts": plano})
    print("\nPlano em %s. Mande cada post para o createScheduledPost e depois rode: agendar.py concluir %s" % (a.saida, a.saida))


def concluir(a):
    plano = comum.ler_json(a.plano)
    pasta = Path(plano["pasta"])
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import entregar
    raizes = set()
    for p in plano["posts"]:
        s, entrega = metadados(pasta, p["arquivo"])
        if entrega:
            e = comum.ler_json(entrega)
            for item in e.get("shorts", []):
                if item.get("arquivo") == p["arquivo"]:
                    item.setdefault("postado", []).append(p["texto"].splitlines()[0])
                    item["agendado_para"] = p["quando"]
            comum.escrever_json(entrega, e)
            raizes.add(entrega.parent.parent)
        if not a.manter_arquivos:
            (pasta / p["arquivo"]).unlink(missing_ok=True)
            (pasta / "textos" / (Path(p["arquivo"]).stem + ".txt")).unlink(missing_ok=True)
        print("ok  %s  -> %s" % (p["arquivo"], p["quando"]))
    for raiz in raizes:
        info = comum.ler_json(raiz / "info.json") or comum.ler_json(sorted(raiz.glob("hora-*/info.json"))[0])
        entregar.escrever_leia_me(raiz, pasta, info)
    print("%d shorts concluídos; %d continuam na pasta para agendar." % (len(plano["posts"]), len(list(pasta.glob("*.mp4")))))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="acao", required=True)
    p = sub.add_parser("planejar")
    p.add_argument("pasta", help="Shorts prontos para postar/<pasta da live>")
    p.add_argument("--shorts", nargs="+", required=True, help='começo do nome, ex.: "Hora 2 - 02"')
    p.add_argument("--agenda", default="", help="JSON do getScheduledPosts (horários já ocupados)")
    p.add_argument("--de", default="")
    p.add_argument("--ate", default="")
    p.add_argument("--sem-subir", action="store_true", help="não sobe os vídeos (só para conferir o plano)")
    p.add_argument("--saida", default="plano-agendamento.json")
    c = sub.add_parser("concluir")
    c.add_argument("plano")
    c.add_argument("--manter-arquivos", action="store_true", help="não apaga os vídeos já agendados")
    a = ap.parse_args()
    planejar(a) if a.acao == "planejar" else concluir(a)


if __name__ == "__main__":
    main()
