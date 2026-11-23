#!/usr/bin/env python3
"""Toca a fila da live hora por hora e mostra em que pé cada hora está.

Uso:
  python pipeline.py ouvir "LINK" [--lingua pt] [--de 1] [--ate 5] [--modelo small] [--cookies chrome] [--chat arq.json]
  python pipeline.py status "lives/<id>"

ouvir   transcreve as horas UMA DEPOIS DA OUTRA (hora 1, 2, 3...) num processo só: rode em segundo plano uma vez
        e cada hora aparece pronta em lives/<id>/hora-N/ enquanto você escolhe, corta e entrega as anteriores.
        Em sequência, e não em paralelo, porque o Whisper já usa todos os núcleos do processador.
        O áudio e o chat são baixados uma vez só. Horas já transcritas são puladas.
        O andamento fica em lives/<id>/fila.json.
status  uma linha por hora: transcrita, momentos escolhidos, conferidos, cortados, entregue, e o próximo passo.
"""
import argparse
import math
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comum  # noqa: E402

AQUI = Path(__file__).resolve().parent


def transcrita(pasta, hora):
    t = comum.ler_json(pasta / "transcricao.json", {}) or {}
    return bool(t.get("completa")) and t.get("hora", 0) == hora


def estado_da_hora(pasta):
    """O que já foi feito numa pasta hora-N/ (ou na pasta da live inteira)."""
    nome = pasta.name
    hora = int(nome.split("-")[1]) if nome.startswith("hora-") and nome.split("-")[1].isdigit() else 0
    conferidos = (comum.ler_json(pasta / "momentos-conferidos.json", {}) or {}).get("momentos", [])
    cortes = comum.ler_json(pasta / "shorts" / "cortes.json", []) or []
    entrega = comum.ler_json(pasta / "entrega.json", {}) or {}
    e = {
        "hora": hora,
        "transcrita": transcrita(pasta, hora),
        "momentos": len((comum.ler_json(pasta / "momentos.json", {}) or {}).get("momentos", [])),
        "conferidos": sum(1 for m in conferidos if m.get("manter")),
        "cortados": len({c["n"] for c in cortes if (pasta / "shorts" / c["arquivo"]).exists()}),
        "entregues": len(entrega.get("arquivos", [])) if entrega else None,
    }
    if not e["transcrita"]:
        e["proximo"] = "esperar a transcrição (pipeline.py ouvir)"
    elif not e["momentos"]:
        e["proximo"] = "ler janelas/ e escrever momentos.json"
    elif not conferidos:
        e["proximo"] = "conferir.py"
    elif not e["cortados"]:
        e["proximo"] = "cortar.py --previa, revisar, cortar.py"
    elif e["entregues"] is None:
        e["proximo"] = "revisar -conferir.jpg e entregar.py"
    else:
        e["proximo"] = "pronta"
    return e


def status(raiz):
    raiz = Path(raiz)
    info = comum.ler_json(raiz / "info.json", {}) or {}
    if not info:
        sys.exit("Não achei %s" % (raiz / "info.json"))
    total = int(math.ceil((info.get("duracao") or 0) / 3600.0)) or 1
    fila = comum.ler_json(raiz / "fila.json", {}) or {}
    print("%s | %s | %s | %d hora(s)" % (info.get("canal", ""), info.get("titulo", ""),
                                         comum.duracao_falada(info.get("duracao") or 0), total))
    print("hora | transcrita | momentos | conferidos | cortados | entregues | próximo passo")
    linhas = []
    for h in range(1, total + 1):
        pasta = raiz / ("hora-%d" % h)
        if pasta.is_dir():
            e = estado_da_hora(pasta)
        else:
            e = {"hora": h, "transcrita": False, "momentos": 0, "conferidos": 0, "cortados": 0, "entregues": None,
                 "proximo": "esperar a transcrição (pipeline.py ouvir)"}
        andamento = (fila.get("horas", {}) or {}).get(str(h), {}).get("estado")
        if not e["transcrita"] and andamento:
            e["proximo"] = "transcrição: %s" % andamento
        linhas.append(e)
        print("%4d | %-10s | %8d | %10d | %8d | %9s | %s" % (
            h, "sim" if e["transcrita"] else "não", e["momentos"], e["conferidos"], e["cortados"],
            "-" if e["entregues"] is None else e["entregues"], e["proximo"]))
    feitas = sum(1 for e in linhas if e["entregues"] is not None)
    print("\n%d de %d horas entregues, %d shorts no total." % (feitas, total, sum(e["entregues"] or 0 for e in linhas)))
    return linhas


def ouvir(a):
    import ouvir as ouv  # importado aqui: ele prepara o ambiente do skill ao ser carregado
    info, raiz = ouv.baixar_info(a.link, a.pasta, a.cookies, a.canal)
    total = int(math.ceil((info.get("duracao") or 0) / 3600.0)) or 1
    ate = min(a.ate or total, total)
    arq_fila = raiz / "fila.json"
    fila = comum.ler_json(arq_fila, {}) or {}
    fila.setdefault("horas", {})

    def marca(h, estado):
        fila["horas"][str(h)] = {"estado": estado, "quando": time.strftime("%Y-%m-%d %H:%M:%S")}
        comum.escrever_json(arq_fila, fila)

    print("Fila: %s | horas %d a %d de %d" % (info.get("titulo", ""), a.de, ate, total), flush=True)
    for h in range(a.de, ate + 1):
        if transcrita(raiz / ("hora-%d" % h), h):
            print("hora %d: já transcrita, pulando" % h, flush=True)
            marca(h, "pronta")
            continue
        marca(h, "transcrevendo")
        cmd = [sys.executable, str(AQUI / "ouvir.py"), a.link, "--pasta", a.pasta, "--hora", str(h)]
        for opcao, valor in (("--lingua", a.lingua), ("--modelo", a.modelo), ("--cookies", a.cookies),
                             ("--canal", a.canal), ("--chat", a.chat if h == a.de else "")):
            if valor:
                cmd += [opcao, valor]
        if a.sem_chat:
            cmd.append("--sem-chat")
        print("\n=== hora %d de %d ===" % (h, total), flush=True)
        r = subprocess.call(cmd)
        if r:
            marca(h, "erro (código %d)" % r)
            sys.exit("A hora %d falhou; as anteriores estão prontas. Veja o erro acima." % h)
        marca(h, "pronta")
        print("HORA %d PRONTA: %s" % (h, raiz / ("hora-%d" % h)), flush=True)
    print("\nFila terminada: horas %d a %d transcritas." % (a.de, ate))


def main():
    comum.no_ambiente()
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="acao", required=True)
    o = sub.add_parser("ouvir", help="transcreve as horas em sequência")
    o.add_argument("link")
    o.add_argument("--pasta", default="lives")
    o.add_argument("--lingua", default="")
    o.add_argument("--modelo", default="")
    o.add_argument("--cookies", default="")
    o.add_argument("--canal", default="")
    o.add_argument("--chat", default="", help="replay do chat baixado à mão (importado uma vez)")
    o.add_argument("--sem-chat", action="store_true")
    o.add_argument("--de", type=int, default=1, help="primeira hora")
    o.add_argument("--ate", type=int, default=0, help="última hora (0 = até o fim da live)")
    s = sub.add_parser("status", help="em que pé está cada hora")
    s.add_argument("raiz", help="lives/<id>")
    a = ap.parse_args()
    if a.acao == "status":
        status(a.raiz)
    else:
        ouvir(a)


if __name__ == "__main__":
    main()
