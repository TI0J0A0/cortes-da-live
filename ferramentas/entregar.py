#!/usr/bin/env python3
"""Entrega os shorts de uma hora (ou de uma live inteira) prontos para postar.

Uso:
  python entregar.py "lives/<id>/hora-1"
  python entregar.py "lives/<id>/hora-1" --destino "D:/Postar"

Cada live ganha UMA pasta com nome legível, e os vídeos ficam soltos nela, já na ordem de postar:

  Shorts prontos para postar/
    2026-11-24 - Twitch - live de 4h28 (v2938905930)/
      Hora 1 - 01 - Entrei na mansão de um rapper.mp4
      Hora 1 - 02 - O cachorro do rapper apareceu do nada.mp4
      ...
      LEIA-ME.txt          título, legenda, hashtags, duração e nota de cada short, hora por hora
      textos/              o .txt de cada short (mesmo nome do vídeo)

Para cada corte, pega a versão MAIS RECENTE em shorts/ (NN-titulo-v3.mp4 ganha da -v2 e da original) e põe o .mp4
como hard link (aparece nas duas pastas mas ocupa o disco uma vez só; em outro disco, copia).
Uma nova entrega da mesma hora substitui só os arquivos daquela hora ("Hora N - ...").
O nome da pasta da live é escolhido na primeira entrega e guardado em lives/<id>/pasta-entrega.txt.
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
SITES = {"TwitchVod": "Twitch", "Twitch": "Twitch", "Youtube": "YouTube", "Kick": "Kick", "Local": "OBS"}
PROIBIDO = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


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


def titulo_de_arquivo(titulo, limite=80):
    """O título como nome de arquivo do Windows: com acento e espaço, sem os caracteres proibidos."""
    t = PROIBIDO.sub("", str(titulo or "")).replace("\n", " ")
    t = re.sub(r"\s+", " ", t).strip().rstrip(". ")
    return t[:limite].rstrip(". ") or "corte"


def nome_do_short(hora, i, titulo):
    return ("Hora %d - %02d - %s" % (hora, i, titulo_de_arquivo(titulo))) if hora else (
        "%02d - %s" % (i, titulo_de_arquivo(titulo)))


def duracao_curta(seg):
    m = int(round((seg or 0) / 60.0))
    return "%dh%02d" % (m // 60, m % 60) if m >= 60 else "%d min" % m


def raiz_da_live(pasta):
    """lives/<id> (a pasta da live) a partir de lives/<id>/hora-N ou da própria lives/<id>."""
    pasta = Path(pasta).resolve()
    return pasta.parent if re.fullmatch(r"hora-\d+", pasta.name) else pasta


def pasta_da_live(raiz, info):
    """'2026-11-24 - Twitch - live de 4h28 (v2938905930)'. Escolhido uma vez e guardado, para as próximas horas
    da mesma live caírem na mesma pasta."""
    guardado = raiz / "pasta-entrega.txt"
    if guardado.exists():
        nome = guardado.read_text(encoding="utf-8").strip()
        if nome:
            return nome
    data = time.strftime("%Y-%m-%d", time.localtime(raiz.stat().st_ctime))
    site = SITES.get(info.get("site") or "", info.get("site") or "Live")
    nome = titulo_de_arquivo("%s - %s - live de %s (%s)" % (data, site, duracao_curta(info.get("duracao")), info["id"]), 120)
    guardado.write_text(nome + "\n", encoding="utf-8")
    return nome


def escrever_leia_me(raiz, destino, info):
    """LEIA-ME.txt da live inteira, montado com o entrega.json de cada hora já entregue."""
    linhas = ["SHORTS PRONTOS PARA POSTAR", "%s | %s" % (info.get("canal", ""), info.get("titulo", "")),
              "Link: %s" % info.get("link", ""), "Duração da live: %s" % comum.duracao_falada(info.get("duracao") or 0), ""]
    total, n_total = 0.0, 0
    horas = sorted(raiz.glob("hora-*/entrega.json"), key=lambda p: int(p.parent.name.split("-")[1]))
    if (raiz / "entrega.json").exists():
        horas.insert(0, raiz / "entrega.json")
    for arq in horas:
        e = comum.ler_json(arq, {}) or {}
        shorts = e.get("shorts") or []
        nome_h = arq.parent.name.replace("hora-", "Hora ") if arq.parent != raiz else "Live inteira"
        linhas += ["=" * 60, "%s: %d shorts (entregue em %s)" % (nome_h, len(shorts), e.get("quando", "?")), "=" * 60]
        for s in shorts:
            dur = float(s.get("duracao") or 0)
            total += dur
            n_total += 1
            linhas += ["", s.get("arquivo", ""),
                       "  Título:    %s" % s.get("titulo", ""),
                       "  Duração:   %.0f s   Nota: %s   Tipo: %s" % (dur, s.get("nota", "?"), s.get("tipo", "?")),
                       "  Na live:   %s" % s.get("inicio", ""),
                       "  Legenda:   %s" % s.get("legenda", ""),
                       "  Hashtags:  %s" % " ".join(s.get("hashtags") or [])]
        linhas.append("")
    linhas += ["Total: %d shorts, %s de vídeo." % (n_total, comum.duracao_falada(total)),
               "O texto completo de cada short (título, legenda, hashtags, de onde veio) está na pasta textos/."]
    (destino / "LEIA-ME.txt").write_text("\n".join(linhas) + "\n", encoding="utf-8")


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
    raiz = raiz_da_live(pasta)
    destino = Path(a.destino) / pasta_da_live(raiz, comum.ler_json(raiz / "info.json") or info)
    textos = destino / "textos"
    textos.mkdir(parents=True, exist_ok=True)
    prefixo = ("Hora %d - " % hora) if hora else ""
    for velho in list(destino.iterdir()) + list(textos.iterdir()):  # a entrega desta hora é sempre a lista atual
        if velho.is_file() and velho.suffix.lower() in (".mp4", ".txt") and velho.name != "LEIA-ME.txt" and (
                velho.name.startswith(prefixo) if prefixo else re.match(r"^\d\d - ", velho.name)):
            velho.unlink()

    escolhidos = escolher(cortes, pasta / "shorts")
    if momentos:  # só os que continuam aprovados no momentos-conferidos.json (descartados na revisão ficam de fora)
        escolhidos = [c for c in escolhidos if momentos.get(c["n"], {}).get("manter")]
    escolhidos.sort(key=lambda c: momentos.get(c["n"], {}).get("inicio_s", c["n"]))  # na ordem da live
    nomes = {c["n"]: nome_do_short(hora, i, c.get("titulo") or sem_versao(c["arquivo"])) for i, c in enumerate(escolhidos, 1)}
    modos, total, shorts = set(), 0.0, []
    for c in escolhidos:
        origem = pasta / "shorts" / c["arquivo"]
        base = nomes[c["n"]]
        modos.add(ligar(origem, destino / (base + ".mp4")))
        txt = origem.with_suffix(".txt")
        if txt.exists():
            ligar(txt, textos / (base + ".txt"))
        m = momentos.get(c["n"], {})
        total += float(c.get("duracao") or 0)
        shorts.append({"arquivo": base + ".mp4", "titulo": c.get("titulo", ""), "tipo": m.get("tipo", ""),
                       "duracao": c.get("duracao"), "nota": c.get("nota"), "inicio": c.get("inicio", ""),
                       "motivo": m.get("motivo", ""), "legenda": m.get("legenda", ""), "hashtags": m.get("hashtags", [])})
    # usado pelo desempenho.py para cruzar com as métricas dos posts, e pelo LEIA-ME da live
    comum.escrever_json(pasta / "entrega.json", {"quando": time.strftime("%Y-%m-%d %H:%M:%S"), "destino": str(destino.resolve()),
                                                 "arquivos": [s["arquivo"] for s in shorts], "shorts": shorts})
    escrever_leia_me(raiz, destino, comum.ler_json(raiz / "info.json") or info)
    print("%d shorts entregues em %s" % (len(escolhidos), destino.resolve()))
    for c in escolhidos:
        print("  %s  (%.0f s, nota %s)" % (nomes[c["n"]] + ".mp4", float(c.get("duracao") or 0), c.get("nota", "?")))
    if len(escolhidos) < 8 and hora:
        print("  (abaixo da meta de ~10 por hora: só estes momentos tinham qualidade para virar short)")
    if "copia" in modos:
        print("  (outro disco: os vídeos foram copiados, não ligados)")
    if not a.manter_tudo and escolhidos:
        apagados, liberado = limpar_shorts(pasta / "shorts", {Path(c["arquivo"]).stem for c in escolhidos})
        if apagados:
            print("  limpeza: %d arquivos antigos/descartados apagados de shorts/ (%.1f GB liberados)"
                  % (apagados, liberado / 1e9))


if __name__ == "__main__":
    main()
