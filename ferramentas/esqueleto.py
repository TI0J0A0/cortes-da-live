#!/usr/bin/env python3
"""Desenha o esqueleto da tela padrão dos Shorts (referencias/esqueleto-tela.json).

Uso:
  python esqueleto.py                                   # só o wireframe com as zonas e medidas
  python esqueleto.py --quadro "lives/<id>/trechos/01-quadro.jpg" --camera 1406,133,493,274
  python esqueleto.py --quadro ... --camera ... --sem-guias --titulo "Um tigre apareceu"

Com --quadro, monta a tela de verdade a partir de um quadro da live (mesmos recortes, fade, título e legenda do
cortar.py), útil para conferir o layout antes de renderizar todos os cortes. A câmera vem de --camera ou do
camera.json da pasta da live (o primeiro corte com facecam).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cortar  # noqa: E402  (entra no ambiente do skill)
from cortar import A, L, ESTILO, cv2, np  # noqa: E402

CORES = {"camera": (170, 80, 160), "fade": (120, 120, 200), "jogo": (70, 140, 60), "texto": (255, 255, 255)}


def guia(tela, y, rotulo, cor=(255, 255, 255), ry=None):
    for x in range(0, L, 28):
        cv2.line(tela, (x, y), (min(L, x + 14), y), cor, 2)
    ry = max(26, y - 10) if ry is None else ry
    cv2.putText(tela, rotulo, (16, ry), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 5, cv2.LINE_AA)
    cv2.putText(tela, rotulo, (16, ry), cv2.FONT_HERSHEY_SIMPLEX, 0.8, cor, 2, cv2.LINE_AA)


def caixa_rotulo(tela, texto, cx, cy):
    (w, h), _ = cv2.getTextSize(texto, cv2.FONT_HERSHEY_SIMPLEX, 1.4, 3)
    cv2.putText(tela, texto, (int(cx - w / 2), int(cy + h / 2)), cv2.FONT_HERSHEY_SIMPLEX, 1.4, CORES["texto"], 3, cv2.LINE_AA)


def wireframe(estilo):
    painel, fade = int(estilo["altura_painel_camera"]), int(estilo["fade_camera"])
    tela = np.zeros((A, L, 3), np.uint8)
    tela[painel - fade:] = CORES["jogo"]
    cam = np.zeros((painel, L, 3), np.uint8)
    cam[:] = CORES["camera"]
    alfa = cortar.mascara_fade(L, painel, fade)[:, :, None]
    tela[:painel] = (cam * alfa + tela[:painel] * (1 - alfa)).astype(np.uint8)
    caixa_rotulo(tela, "FACECAM  1080 x %d" % painel, L / 2, (painel - fade) / 2)
    caixa_rotulo(tela, "crop proporcional, sem esticar", L / 2, (painel - fade) / 2 + 60)
    caixa_rotulo(tela, "GAMEPLAY  1080 x %d" % (A - painel + fade), L / 2, (painel + A) / 2 - 120)
    return tela


def tela_real(estilo, quadro, camera):
    H, W = quadro.shape[:2]
    pl = {"modo": "facecam", "camera": camera, "rosto": None}
    rc = cortar.recortes(pl, W, H, estilo)
    tela = np.zeros((A, L, 3), np.uint8)
    for chave in ("jogo", "topo"):
        sx, sy, sw, sh, dx, dy, dw, dh = rc[chave]
        img = cv2.resize(quadro[sy:sy + sh, sx:sx + sw], (dw, dh), interpolation=cv2.INTER_LANCZOS4)
        if chave == "topo" and dw > sw:
            img = cortar.afiar(img, float(estilo.get("nitidez_camera", 0)))
        if chave == "topo" and rc.get("fade"):
            alfa = cortar.mascara_fade(dw, dh, rc["fade"])[:, :, None]
            img = (img * alfa + tela[dy:dy + dh, dx:dx + dw] * (1 - alfa)).astype(np.uint8)
        tela[dy:dy + dh, dx:dx + dw] = img
    zoom = L / float(rc["topo"][2])
    return tela, zoom


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quadro", default="", help="um quadro 16:9 da live (ex.: trechos/01-quadro.jpg)")
    ap.add_argument("--camera", default="", help="x,y,largura,altura da facecam no quadro")
    ap.add_argument("--estilo", default="", help="estilo.json da live, se houver")
    ap.add_argument("--titulo", default="Tomando debuff de direção com a Lucia")
    ap.add_argument("--legenda", default="QUE FOI SEM")
    ap.add_argument("--sem-guias", action="store_true")
    ap.add_argument("--saida", default="esqueleto-tela.png")
    a = ap.parse_args()

    estilo = dict(ESTILO)
    if a.estilo:
        estilo.update(cortar.comum.ler_json(Path(a.estilo), {}))
    painel, fade = int(estilo["altura_painel_camera"]), int(estilo["fade_camera"])
    zoom = None
    if a.quadro:
        quadro = cv2.imdecode(np.frombuffer(Path(a.quadro).read_bytes(), np.uint8), cv2.IMREAD_COLOR)
        if quadro is None:
            sys.exit("Não consegui abrir o quadro %s" % a.quadro)
        camera = [int(v) for v in a.camera.split(",")] if a.camera else None
        if camera is None:
            cam_json = cortar.comum.ler_json(Path(a.quadro).resolve().parent.parent / "camera.json", {})
            camera = next((s["camera"] for pls in cam_json.values() for s in pls if s.get("modo") == "facecam"), None)
        if camera is None:
            sys.exit("Passe --camera x,y,largura,altura (não achei camera.json).")
        tela, zoom = tela_real(estilo, quadro, camera)
    else:
        tela = wireframe(estilo)

    emenda = painel + int(estilo.get("titulo_desloca", 0))
    alt_barra = int(estilo.get("altura_barra", 12))
    ly = int(A * estilo["altura_legenda"])
    if not a.sem_guias:  # as guias vão por baixo do título e da legenda
        guia(tela, painel - fade, "inicio do fade / gameplay  y=%d" % (painel - fade), (120, 230, 255))
        guia(tela, painel, "fim da facecam / centro do titulo  y=%d" % painel, (0, 214, 255), ry=emenda + 110)
        guia(tela, ly, "centro da legenda  y=%d" % ly, (255, 255, 255), ry=ly - 80)
        guia(tela, A - alt_barra, "barra de progresso  %d px" % alt_barra, (0, 214, 255))
    cortar.colar(tela, cortar.imagem_do_titulo(a.titulo, estilo), L / 2, emenda)
    palavras = [{"w": w} for w in (a.legenda.upper() if estilo["maiusculas"] else a.legenda).split()]
    cortar.colar(tela, cortar.imagem_da_legenda(palavras, min(1, len(palavras) - 1), estilo), L / 2, ly)
    tela[A - alt_barra:, :int(L * 0.4)] = cortar.cor(estilo.get("cor_barra", estilo["cor_destaque"]))[::-1]

    if not a.sem_guias:
        if zoom:
            cv2.putText(tela, "zoom da facecam: %.2fx" % zoom, (16, A - 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 5, cv2.LINE_AA)
            cv2.putText(tela, "zoom da facecam: %.2fx" % zoom, (16, A - 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
    cortar.gravar_jpg(a.saida, tela, 92) if a.saida.lower().endswith(".jpg") else Path(a.saida).write_bytes(cv2.imencode(".png", tela)[1].tobytes())
    print("Esqueleto salvo em %s" % Path(a.saida).resolve())


if __name__ == "__main__":
    main()
