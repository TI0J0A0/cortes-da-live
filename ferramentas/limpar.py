#!/usr/bin/env python3
"""Libera espaço em disco apagando o que só serve para refazer cortes de horas já entregues.

Uso:
  python limpar.py                      # só MOSTRA o que seria apagado (nada é apagado)
  python limpar.py --dias 7 --apagar    # apaga trechos/ das horas entregues há mais de 7 dias
  python limpar.py --audio --apagar     # também o audio.* baixado das lives com TODAS as horas entregues

O que pode sair:
  lives/<id>/hora-N/trechos/   os pedaços da live baixados para o corte (~600 MB por hora)
  lives/<id>/audio.*           o áudio baixado da live (só com --audio, e só quando a live inteira foi entregue)
Nunca apaga: os shorts (lives/<id>/hora-N/shorts/ e "Shorts prontos para postar/"), as transcrições, os
momentos, nem uma gravação original do OBS (arquivo_local). Sem --apagar, nada sai do disco.
"""
import argparse
import math
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comum  # noqa: E402


def tamanho(p):
    p = Path(p)
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def entregue_ha(pasta_hora):
    """Dias desde a entrega da hora, ou None se ela não foi entregue."""
    entrega = comum.ler_json(pasta_hora / "entrega.json")
    if not entrega:
        return None
    try:
        quando = time.mktime(time.strptime(entrega["quando"], "%Y-%m-%d %H:%M:%S"))
    except (KeyError, ValueError):
        quando = (pasta_hora / "entrega.json").stat().st_mtime
    return (time.time() - quando) / 86400.0


def candidatos(pasta_lives, dias, com_audio):
    """[(caminho, bytes, motivo)] do que pode ser apagado."""
    saida = []
    for raiz in sorted(Path(pasta_lives).iterdir()) if Path(pasta_lives).is_dir() else []:
        if not raiz.is_dir():
            continue
        info = comum.ler_json(raiz / "info.json", {}) or {}
        horas = sorted(p for p in raiz.glob("hora-*") if p.is_dir())
        idades = {}
        for h in horas:
            idade = entregue_ha(h)
            idades[h.name] = idade
            if idade is not None and idade >= dias and (h / "trechos").is_dir():
                saida.append((h / "trechos", tamanho(h / "trechos"), "%s entregue há %.0f dia(s)" % (h.name, idade)))
        if com_audio and not info.get("arquivo_local"):
            total = int(math.ceil((info.get("duracao") or 0) / 3600.0))
            todas = total and all(idades.get("hora-%d" % k) is not None and idades["hora-%d" % k] >= dias
                                  for k in range(1, total + 1))
            if todas:
                for audio in raiz.glob("audio.*"):
                    saida.append((audio, tamanho(audio), "todas as %d horas entregues" % total))
    return saida


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pasta", default="lives")
    ap.add_argument("--dias", type=float, default=7, help="só horas entregues há pelo menos tantos dias")
    ap.add_argument("--audio", action="store_true", help="inclui o áudio baixado das lives totalmente entregues")
    ap.add_argument("--apagar", action="store_true", help="apaga de verdade (sem isso, só lista)")
    a = ap.parse_args()
    lista = candidatos(a.pasta, a.dias, a.audio)
    if not lista:
        print("Nada para limpar (horas entregues há %.0f dia(s) ou mais, com trechos guardados)." % a.dias)
        return
    total = 0
    for caminho, bytes_, motivo in lista:
        total += bytes_
        print("%s  %7.1f MB  (%s)" % ("APAGANDO" if a.apagar else "apagaria", bytes_ / 1e6, caminho), "-", motivo)
        if a.apagar:
            if caminho.is_dir():
                shutil.rmtree(caminho)
            else:
                caminho.unlink()
    if a.apagar:
        print("\n%.2f GB liberados." % (total / 1e9))
    else:
        print("\n%.2f GB podem ser liberados. Rode de novo com --apagar para apagar." % (total / 1e9))


if __name__ == "__main__":
    main()
