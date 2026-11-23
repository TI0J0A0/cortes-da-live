#!/usr/bin/env python3
"""Entrega os shorts de uma hora (ou de uma live inteira) prontos para postar.

Uso:
  python entregar.py "lives/<id>/hora-1"
  python entregar.py "lives/<id>/hora-1" --destino "D:/Postar"

Para cada corte, pega a versão MAIS RECENTE em shorts/ (NN-titulo-v3.mp4 ganha da -v2 e da original) e põe o .mp4
e o .txt (como hard link: o vídeo aparece nas duas pastas mas ocupa o disco uma vez só) em:
  Shorts prontos para postar/<id da live>/hora-N/NN-titulo.mp4   (sem o sufixo -vN)
e escreve LEIA-ME.txt com título, duração, nota, motivo, legenda do post e hashtags de cada um.
Uma nova entrega da mesma hora substitui a anterior (os arquivos antigos dessa hora saem da pasta de entrega).
Depois de entregar, apaga de shorts/ as versões antigas (-vN superadas) e os cortes descartados na revisão;
use --manter-tudo para guardar tudo.
"""
import argparse
import os
import re
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comum  # noqa: E402

VERSAO = re.compile(r"-v(\d+)$")


def versao(nome):
    m = VERSAO.search(Path(nome).stem)
    return int(m.group(1)) if m else 1


def sem_versao(nome):
    return VERSAO.sub("", Path(nome).stem)


def escolher(cortes, pasta_shorts):
    """O corte mais recente de cada número: o arquivo renderizado por último ganha
    (também quando o título mudou e o nome não tem -vN); empate: maior -vN."""
    melhor = {}
    for c in cortes:
        arq = pasta_shorts / c["arquivo"]
        if not arq.exists():
            continue
        chave = (arq.stat().st_mtime, versao(arq.name))
        if c["n"] not in melhor or chave > melhor[c["n"]][0]:
            melhor[c["n"]] = (chave, c)
    return [melhor[n][1] for n in sorted(melhor)]


def ligar(origem, destino):
    """Põe o arquivo na entrega sem duplicar no disco (hard link); em outro disco, copia."""
    if destino.exists():
        destino.unlink()
    try:
        os.link(origem, destino)
        return "link"
    except OSError:
        shutil.copy2(origem, destino)
        return "copia"


def limpar_shorts(pasta_shorts, manter):
    """Apaga de shorts/ as versões antigas e os cortes descartados (mp4, txt e -conferir.jpg).
    `manter` = nomes (sem extensão) dos cortes entregues. Devolve (arquivos, bytes) apagados."""
    apagados, liberado = 0, 0
    for arq in list(pasta_shorts.iterdir()):
        if arq.suffix.lower() not in (".mp4", ".txt", ".jpg"):
            continue
        base = arq.stem[:-len("-conferir")] if arq.stem.endswith("-conferir") else arq.stem
        if not re.match(r"^\d+-", base) or base in manter:
            continue
        liberado += arq.stat().st_size if arq.suffix.lower() == ".mp4" else 0
        arq.unlink()
        apagados += 1
    return apagados, liberado


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pasta", help="lives/<id>/hora-N (ou lives/<id> para uma live processada inteira)")
    ap.add_argument("--destino", default="Shorts prontos para postar")
    ap.add_argument("--manter-tudo", action="store_true",
                    help="não apaga de shorts/ as versões antigas nem os cortes descartados")
    a = ap.parse_args()
    pasta = Path(a.pasta)
    info = comum.ler_json(pasta / "info.json")
    cortes = comum.ler_json(pasta / "shorts" / "cortes.json", [])
    if not info or not cortes:
        sys.exit("Nada para entregar: rode o cortar.py em %s antes." % pasta)
    momentos = {m["n"]: m for m in (comum.ler_json(pasta / "momentos-conferidos.json", {}) or {}).get("momentos", [])}
    hora = info.get("hora")
    nome_hora = re.fullmatch(r"hora-(\d+)", pasta.resolve().name)
    if not hora and nome_hora:  # pastas hora-N feitas antes do ouvir.py --hora
        hora = int(nome_hora.group(1))
        info.setdefault("hora_inicio", (hora - 1) * 3600)
        info.setdefault("hora_fim", hora * 3600)
    destino = Path(a.destino) / str(info["id"]) / (("hora-%d" % hora) if hora else "live-inteira")
    destino.mkdir(parents=True, exist_ok=True)
    for velho in destino.iterdir():  # a entrega desta hora é sempre a lista atual
        if velho.is_file():
            velho.unlink()

    escolhidos = escolher(cortes, pasta / "shorts")
    if momentos:  # só os que continuam aprovados no momentos-conferidos.json (descartados na revisão ficam de fora)
        escolhidos = [c for c in escolhidos if momentos.get(c["n"], {}).get("manter")]
    nomes = {}  # numeração da entrega: 01, 02, 03... na ordem da live, sem buracos
    for i, c in enumerate(sorted(escolhidos, key=lambda c: momentos.get(c["n"], {}).get("inicio_s", c["n"])), 1):
        nomes[c["n"]] = "%02d-%s" % (i, re.sub(r"^\d+-", "", sem_versao(c["arquivo"])))
    escolhidos.sort(key=lambda c: nomes[c["n"]])
    linhas = ["SHORTS PRONTOS PARA POSTAR", "%s | %s" % (info.get("canal", ""), info.get("titulo", "")),
              ("Hora %d da live: %s a %s" % (hora, comum.relogio(info["hora_inicio"]), comum.relogio(info["hora_fim"])))
              if hora else "Live inteira", "Link: %s" % info.get("link", ""),
              "Entregue em %s: %d shorts" % (time.strftime("%d/%m/%Y %H:%M"), len(escolhidos)), "", "=" * 60]
    total = 0.0
    modos = set()
    for c in escolhidos:
        origem = pasta / "shorts" / c["arquivo"]
        base = nomes[c["n"]]
        modos.add(ligar(origem, destino / (base + ".mp4")))
        txt = origem.with_suffix(".txt")
        if txt.exists():
            ligar(txt, destino / (base + ".txt"))
        m = momentos.get(c["n"], {})
        total += float(c.get("duracao") or 0)
        linhas += ["", "%s.mp4" % base,
                   "  Título:    %s" % c.get("titulo", ""),
                   "  Duração:   %.0f s   Nota: %s   Tipo: %s" % (float(c.get("duracao") or 0), c.get("nota", "?"), m.get("tipo", "?")),
                   "  Na live:   %s a %s" % (c.get("inicio", ""), c.get("fim", "")),
                   "  Por quê:   %s" % m.get("motivo", ""),
                   "  Legenda:   %s" % m.get("legenda", ""),
                   "  Hashtags:  %s" % " ".join(m.get("hashtags", []))]
    linhas += ["", "=" * 60, "Total: %d shorts, %s de vídeo." % (len(escolhidos), comum.duracao_falada(total))]
    if len(escolhidos) < 8:
        linhas.append("Abaixo da meta de ~10 por hora: só estes momentos tinham qualidade para virar short.")
    (destino / "LEIA-ME.txt").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    comum.escrever_json(pasta / "entrega.json", {"quando": time.strftime("%Y-%m-%d %H:%M:%S"), "destino": str(destino.resolve()),
                                                 "arquivos": [nomes[c["n"]] + ".mp4" for c in escolhidos],
                                                 # usado pelo desempenho.py para cruzar com as métricas dos posts
                                                 "shorts": [{"arquivo": nomes[c["n"]] + ".mp4", "titulo": c.get("titulo", ""),
                                                             "tipo": momentos.get(c["n"], {}).get("tipo", ""),
                                                             "duracao": c.get("duracao"), "nota": c.get("nota"),
                                                             "inicio": c.get("inicio", ""),
                                                             "legenda": momentos.get(c["n"], {}).get("legenda", "")}
                                                            for c in escolhidos]})
    print("%d shorts entregues em %s" % (len(escolhidos), destino.resolve()))
    for c in escolhidos:
        print("  %s  (%.0f s, nota %s)" % (nomes[c["n"]] + ".mp4", float(c.get("duracao") or 0), c.get("nota", "?")))
    if "copia" in modos:
        print("  (outro disco: os vídeos foram copiados, não ligados)")
    if not a.manter_tudo and escolhidos:
        apagados, liberado = limpar_shorts(pasta / "shorts", {Path(c["arquivo"]).stem for c in escolhidos})
        if apagados:
            print("  limpeza: %d arquivos antigos/descartados apagados de shorts/ (%.1f GB liberados)"
                  % (apagados, liberado / 1e9))


if __name__ == "__main__":
    main()
