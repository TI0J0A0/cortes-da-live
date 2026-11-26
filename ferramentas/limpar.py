#!/usr/bin/env python3
"""Libera espaço e deixa a pasta de entrega só com o que ainda falta postar.

Uso (sem --apagar, só MOSTRA o que sairia; nada é apagado):
  python limpar.py --agendados agenda.json       shorts entregues que já estão no Metricool (vídeo + texto)
  python limpar.py --trabalho                    arquivos de trabalho das lives já entregues
  python limpar.py --agendados agenda.json --trabalho --apagar     as duas coisas, de verdade

--agendados: agenda.json é a lista de posts que o getScheduledPosts do Metricool devolveu (pode juntar vários
  períodos numa lista só). Um short entregue sai quando um post tem o mesmo título (ou o texto registrado em
  "postado" no entrega.json) E foi criado depois que a hora foi entregue (assim um título repetido de outra live
  não apaga o short errado). O Metricool guarda a própria cópia do vídeo, então apagar daqui é seguro.
--trabalho: em lives/<id>/ ficam só info.json, pasta-entrega.txt e os hora-N/info.json e entrega.json (o aviso de
  link repetido e o desempenho.py usam). Saem trechos, áudio, transcrições, janelas, versões e shorts de trabalho.
  Só em lives com todas as horas entregues; a live que ainda está sendo cortada não é tocada.
--sem-entrega: também apaga lives/<id> que nunca tiveram nenhuma hora entregue.
"""
import argparse
import datetime as dt
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comum  # noqa: E402

MANTER = {"info.json", "pasta-entrega.txt", "entrega.json", "fonte-video.json"}


def tamanho(p):
    """Bytes que apagar `p` realmente libera (arquivo com outro hard link não libera nada)."""
    p = Path(p)
    arqs = [p] if p.is_file() else [f for f in p.rglob("*") if f.is_file()]
    return sum(f.stat().st_size for f in arqs if os.stat(f).st_nlink == 1)


def remover(p):
    """Apaga arquivo ou pasta. No Windows com OneDrive o Python às vezes não consegue remover a pasta vazia:
    tenta de novo pelo PowerShell."""
    p = Path(p)
    if p.is_file():
        p.unlink()
        return
    shutil.rmtree(p, ignore_errors=True)
    if p.exists() and comum.WINDOWS:
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Remove-Item -LiteralPath '%s' -Recurse -Force -ErrorAction SilentlyContinue" % str(p.resolve()).replace("'", "''")],
                       capture_output=True)


def lives_entregues(pasta_lives):
    """[(raiz, info, horas, entregues)] de cada live."""
    out = []
    for raiz in sorted(Path(pasta_lives).iterdir()) if Path(pasta_lives).is_dir() else []:
        if not raiz.is_dir():
            continue
        info = comum.ler_json(raiz / "info.json")
        if not info:
            achou = sorted(raiz.glob("hora-*/info.json"))
            info = comum.ler_json(achou[0]) if achou else {}
        horas = sorted(p for p in raiz.glob("hora-*") if p.is_dir())
        entregues = [h for h in horas if (h / "entrega.json").exists()]
        out.append((raiz, info or {}, horas, entregues))
    return out


def candidatos_trabalho(pasta_lives, sem_entrega=False):
    saida = []
    for raiz, info, horas, entregues in lives_entregues(pasta_lives):
        total = int(math.ceil((info.get("duracao") or 0) / 3600.0)) or len(horas)
        if not entregues:
            if sem_entrega:
                saida.append((raiz, tamanho(raiz), "live nunca entregue"))
            continue
        if len(entregues) < min(total, len(horas)):
            continue  # ainda está sendo cortada
        for item in raiz.iterdir():
            if item.is_dir() and item.name.startswith("hora-"):
                for sub in item.iterdir():
                    if sub.name not in MANTER:
                        saida.append((sub, tamanho(sub), "trabalho de %s/%s" % (raiz.name, item.name)))
            elif item.name not in MANTER:
                saida.append((item, tamanho(item), "trabalho de %s" % raiz.name))
    for log in Path(pasta_lives).glob("*.log"):
        saida.append((log, tamanho(log), "log"))
    return saida


def textos_do_post(p):
    """Os textos que identificam um post do Metricool: 1ª linha do texto, títulos do YouTube e do TikTok."""
    t = [(p.get("text") or "").splitlines()[0] if p.get("text") else ""]
    t.append((p.get("youtubeData") or {}).get("title", ""))
    t.append((p.get("tiktokData") or {}).get("title", ""))
    return [re.sub(r"\s*\|.*$|#\w+", "", x).strip() for x in t if x]


def candidatos_agendados(agenda, pasta_lives="lives"):
    import desempenho
    posts = agenda.get("data", agenda) if isinstance(agenda, dict) else agenda
    saida = []
    for raiz, info, horas, entregues in lives_entregues(pasta_lives):
        for h in entregues:
            e = comum.ler_json(h / "entrega.json", {}) or {}
            destino = Path(e.get("destino", ""))
            try:
                entregue_em = dt.datetime.fromisoformat(e["quando"]) if e.get("quando") else None
            except ValueError:
                entregue_em = None
            for s in e.get("shorts", []):
                video = destino / s.get("arquivo", "")
                if not video.exists():
                    continue
                titulo = desempenho.normal(s.get("titulo") or re.sub(r"^Hora \d+ - \d+ - ", "", video.stem))
                postados = {desempenho.normal(x) for x in s.get("postado", [])}
                for p in posts or []:
                    criado = (p.get("creationDate") or {}).get("dateTime", "")
                    if entregue_em and criado and dt.datetime.fromisoformat(criado[:19]) < entregue_em - dt.timedelta(hours=1):
                        continue  # post criado antes desta entrega: é de outra live com título parecido
                    textos = [desempenho.normal(x) for x in textos_do_post(p)]
                    if any(x in postados for x in textos) or max(
                            [desempenho.parecido(titulo, x) for x in textos] + [desempenho.parecido(x, titulo) for x in textos] + [0]) >= 0.9:
                        txt = destino / "textos" / (video.stem + ".txt")
                        saida.append((video, video.stat().st_size, "já no Metricool: %s" % textos[0][:50]))
                        if txt.exists():
                            saida.append((txt, txt.stat().st_size, "texto do short agendado"))
                        break
    return saida


def refazer_leia_me(pasta_lives="lives"):
    import entregar
    for raiz, info, horas, entregues in lives_entregues(pasta_lives):
        nome = raiz / "pasta-entrega.txt"
        if entregues and nome.exists():
            destino = Path("Shorts prontos para postar") / nome.read_text(encoding="utf-8").strip()
            if destino.is_dir():
                entregar.escrever_leia_me(raiz, destino, info)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pasta", default="lives")
    ap.add_argument("--agendados", default="", help="JSON com os posts do Metricool (getScheduledPosts)")
    ap.add_argument("--trabalho", action="store_true", help="arquivos de trabalho das lives já entregues")
    ap.add_argument("--sem-entrega", action="store_true", help="também lives que nunca foram entregues")
    ap.add_argument("--apagar", action="store_true", help="apaga de verdade (sem isso, só lista)")
    a = ap.parse_args()
    if not a.agendados and not a.trabalho:
        sys.exit("Diga o que limpar: --agendados agenda.json e/ou --trabalho (veja o topo do arquivo).")
    lista = []
    if a.agendados:
        lista += candidatos_agendados(comum.ler_json(a.agendados, []), a.pasta)
    if a.trabalho:
        lista += candidatos_trabalho(a.pasta, a.sem_entrega)
    if not lista:
        print("Nada para limpar.")
        return
    total = 0
    for caminho, bytes_, motivo in lista:
        total += bytes_
        print("%s %8.1f MB  %s  (%s)" % ("APAGANDO" if a.apagar else "apagaria", bytes_ / 1e6, caminho, motivo))
        if a.apagar:
            remover(caminho)
    if a.apagar:
        refazer_leia_me(a.pasta)
        print("\n%.2f GB liberados. LEIA-ME das lives refeitos." % (total / 1e9))
    else:
        print("\n%.2f GB podem ser liberados. Rode de novo com --apagar para apagar." % (total / 1e9))


if __name__ == "__main__":
    main()
