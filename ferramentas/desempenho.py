#!/usr/bin/env python3
"""Cruza as métricas dos posts (Metricool) com os shorts entregues e mostra o que funciona no canal.

Uso:
  python desempenho.py desempenho/metricool-2026-11-23.json [mais arquivos...] [--pasta lives] [--saida desempenho/relatorio.md]

Cada arquivo é um JSON com uma lista de posts (ou {"posts": [...]}, {"data": [...]}), como os que o Claude salva
depois de puxar as métricas do Metricool. De cada post usa:
  texto:          titulo / title / text / texto / caption / description
  visualizações:  visualizacoes / views / videoViews / plays / impressions / reach
  retenção (opc): retencao / averageViewPercentage / retention / avgViewPercentage
Cada post é ligado ao short entregue de mesmo título (lives/*/hora-*/entrega.json) e o relatório agrupa
por tipo de momento e por faixa de duração. Use as conclusões para ajustar referencias/como-escolher.md.
"""
import argparse
import difflib
import re
import statistics
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comum  # noqa: E402

CHAVES_TEXTO = ("titulo", "title", "text", "texto", "caption", "description", "content")
CHAVES_VIEWS = ("visualizacoes", "views", "videoViews", "video_views", "plays", "impressions", "reach")
CHAVES_RETENCAO = ("retencao", "averageViewPercentage", "retention", "avgViewPercentage", "average_view_percentage")
CHAVES_SKIP = ("skip", "reelsSkipRate", "skipRate", "skip_rate")  # % que pulou nos 3 primeiros segundos (Instagram)
NUMEROS = {"um": "1", "uma": "1", "dois": "2", "duas": "2", "tres": "3", "quatro": "4", "cinco": "5", "seis": "6",
           "sete": "7", "oito": "8", "nove": "9", "dez": "10", "vi": "6"}


def normal(t):
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"#\w+", " ", t)
    t = re.sub(r"[^a-z0-9]+", " ", t).strip()
    return " ".join(NUMEROS.get(w, w) for w in t.split())  # "três dias" e "3 dias" viram a mesma coisa


def primeiro(d, chaves):
    for k in chaves:
        if d.get(k) not in (None, ""):
            return d[k]
    return None


def numero(v):
    try:
        return float(str(v).replace("%", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


def ler_posts(arquivos):
    posts = []
    for arq in arquivos:
        dado = comum.ler_json(arq)
        if isinstance(dado, dict):
            dado = dado.get("posts") or dado.get("data") or dado.get("items") or []
        for p in dado or []:
            if not isinstance(p, dict):
                continue
            views = numero(primeiro(p, CHAVES_VIEWS))
            texto = primeiro(p, CHAVES_TEXTO)
            if views is None or not texto:
                continue
            posts.append({"texto": str(texto), "views": views, "retencao": numero(primeiro(p, CHAVES_RETENCAO)),
                          "skip": numero(primeiro(p, CHAVES_SKIP))})
    return posts


def shorts_entregues(pasta_lives):
    out = []
    for entrega in sorted(Path(pasta_lives).glob("*/hora-*/entrega.json")) + sorted(Path(pasta_lives).glob("*/entrega.json")):
        lista = (comum.ler_json(entrega, {}) or {}).get("shorts")
        if lista is None:  # entrega feita antes do entregar.py guardar os metadados: monta a partir dos cortes
            pasta = entrega.parent
            momentos = {m["n"]: m for m in (comum.ler_json(pasta / "momentos-conferidos.json", {}) or {}).get("momentos", [])}
            lista = [dict(c, tipo=momentos.get(c["n"], {}).get("tipo", "")) for c in comum.ler_json(pasta / "shorts" / "cortes.json", []) or []
                     if momentos.get(c["n"], {}).get("manter", True)]
        for s in lista:
            if s.get("titulo"):
                out.append(dict(s, live=entrega.parent.parent.name if entrega.parent.name.startswith("hora-") else entrega.parent.name))
    return out


def parecido(titulo, texto):
    """0 a 1: o título dentro do texto do post (1), a parte das palavras do título presentes no começo do post,
    ou a semelhança das letras; vale o maior."""
    t = normal(titulo)
    if not t:
        return 0.0
    if t in texto:
        return 1.0
    palavras = [w for w in t.split() if len(w) > 2]
    inicio = set(texto.split()[:len(t.split()) + 12])
    sobra = sum(w in inicio for w in palavras) / float(len(palavras)) if palavras else 0.0
    return max(sobra, difflib.SequenceMatcher(None, t, texto[:len(t) + 20]).ratio())


def ligar(post, shorts):
    """O short cujo título (ou texto que foi postado, campo "postado" do entrega.json) bate com o post."""
    texto = normal(post["texto"])
    melhor, nota = None, 0.0
    for s in shorts:
        r = max([parecido(s["titulo"], texto)] + [parecido(x, texto) for x in s.get("postado") or []])
        if r > nota:
            melhor, nota = s, r
    return melhor if nota >= 0.8 else None


def faixa(dur):
    if dur is None:
        return "?"
    dur = float(dur)
    if dur < 30:
        return "até 30 s"
    if dur < 45:
        return "30–45 s"
    if dur < 60:
        return "45–60 s"
    return "60 s ou mais"


def tipo_base(t):
    return (str(t or "?").split("/")[0].strip().lower()) or "?"


def tabela(titulo, grupos):
    linhas = ["## %s" % titulo, "", "| grupo | shorts | views (mediana) | views (média) | retenção média | pulou em 3 s |",
              "|---|---|---|---|---|---|"]
    for nome, itens in sorted(grupos.items(), key=lambda kv: -statistics.median([i["views"] for i in kv[1]])):
        vs = [i["views"] for i in itens]
        ret = [i["retencao"] for i in itens if i["retencao"] is not None]
        skip = [i["skip"] for i in itens if i.get("skip") is not None]
        linhas.append("| %s | %d | %.0f | %.0f | %s | %s |" % (nome, len(itens), statistics.median(vs), statistics.mean(vs),
                                                              ("%.0f%%" % statistics.mean(ret)) if ret else "-",
                                                              ("%.0f%%" % statistics.mean(skip)) if skip else "-"))
    return linhas + [""]


def relatorio(posts, shorts):
    ligados = []
    for p in posts:
        s = ligar(p, shorts)
        if s:
            ligados.append(dict(p, _post=p, **{k: s.get(k) for k in ("titulo", "tipo", "duracao", "nota", "live")}))
    soltos = [p for p in posts if not any(p is l.get("_post") for l in ligados)]
    linhas = ["# Desempenho dos shorts", "", "%d posts lidos, %d ligados a shorts entregues." % (len(posts), len(ligados)), ""]
    if not ligados:
        return linhas + ["Nenhum post bateu com os títulos entregues: confira se o texto do post traz o título do short."], ligados
    por_tipo, por_faixa = {}, {}
    for i in ligados:
        por_tipo.setdefault(tipo_base(i["tipo"]), []).append(i)
        por_faixa.setdefault(faixa(i["duracao"]), []).append(i)
    linhas += tabela("Por tipo de momento", por_tipo) + tabela("Por duração", por_faixa)
    notas = [(i["nota"], i["views"]) for i in ligados if i.get("nota") is not None]
    if len(notas) >= 5:
        altas = [v for n, v in notas if n >= 80]
        baixas = [v for n, v in notas if n < 80]
        if altas and baixas:
            linhas += ["## A nota prevê o resultado?", "",
                       "Nota 80+: mediana de %.0f views (%d shorts). Abaixo de 80: %.0f views (%d shorts)." % (
                           statistics.median(altas), len(altas), statistics.median(baixas), len(baixas)), ""]
    if soltos:
        # posts sem short correspondente (de lives que já saíram de lives/, ou postados à mão) ainda mostram o canal
        linhas += ["## Posts sem short entregue correspondente", ""]
        for p in sorted(soltos, key=lambda x: -x["views"])[:10]:
            linhas.append("- %.0f views%s: %s" % (p["views"], (", pulou em 3 s: %.0f%%" % p["skip"]) if p.get("skip") is not None else "",
                                                  p["texto"].splitlines()[0][:80]))
        linhas.append("")
    linhas += ["## Os 5 melhores", ""]
    for i in sorted(ligados, key=lambda x: -x["views"])[:5]:
        linhas.append("- %.0f views: %s (%s, %s s)" % (i["views"], i["titulo"], i.get("tipo") or "?", i.get("duracao") or "?"))
    linhas += ["", "## Os 5 piores", ""]
    for i in sorted(ligados, key=lambda x: x["views"])[:5]:
        linhas.append("- %.0f views: %s (%s, %s s)" % (i["views"], i["titulo"], i.get("tipo") or "?", i.get("duracao") or "?"))
    return linhas, ligados


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("arquivos", nargs="+")
    ap.add_argument("--pasta", default="lives")
    ap.add_argument("--saida", default="desempenho/relatorio.md")
    a = ap.parse_args()
    posts = ler_posts(a.arquivos)
    shorts = shorts_entregues(a.pasta)
    if not shorts:
        sys.exit("Não achei shorts entregues com metadados (entrega.json com \"shorts\"). Reentregue com o entregar.py atual.")
    linhas, _ = relatorio(posts, shorts)
    saida = Path(a.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print("\n".join(linhas))
    print("\nRelatório salvo em %s" % saida)


if __name__ == "__main__":
    main()
