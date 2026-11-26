"""Testes básicos de regressão para o projeto gamer.

Execute após preparar ambiente: python -m unittest discover -s testes -v
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PASTA_FERRAMENTAS = Path(__file__).resolve().parents[1] / 'ferramentas'
sys.path.insert(0, str(PASTA_FERRAMENTAS))
import comum  # noqa: E402
comum.no_ambiente = lambda: None  # os testes usam o Python de execução, não fazem bootstrap
import conferir  # noqa: E402
import cortar  # noqa: E402
import ouvir  # noqa: E402
import entregar  # noqa: E402
import limpar  # noqa: E402
import desempenho  # noqa: E402
import pipeline  # noqa: E402
import time  # noqa: E402
import numpy as np  # noqa: E402


class ProjetoGamer(unittest.TestCase):
    def test_facecam_largura_total_com_fade(self):
        # referencias/layout-facecam-fade.md: facecam em cima, crop proporcional, gradiente sobre a gameplay
        cam = {'modo': 'facecam', 'camera': [20, 20, 300, 180], 'rosto': [80, 30, 100, 100]}
        plano = cortar.recortes(cam, 1280, 720, cortar.ESTILO)
        sx, sy, sw, sh, dx, dy, dw, dh = plano['topo']
        self.assertEqual((dx, dy, dw), (0, 0, 1080))
        self.assertAlmostEqual(sw / sh, dw / dh, delta=0.02)  # sem esticar o rosto
        self.assertTrue(20 <= sx and sx + sw <= 320 and 20 <= sy and sy + sh <= 200)  # só dentro da câmera
        fade = plano['fade']
        self.assertGreaterEqual(fade, 60)
        jy, jh = plano['jogo'][5], plano['jogo'][7]
        self.assertEqual(jy, dh - fade)  # a gameplay começa por baixo do gradiente
        self.assertEqual(jy + jh, 1920)
        m = cortar.mascara_fade(dw, dh, fade)
        self.assertEqual(m[0, 0], 1.0)
        self.assertLess(m[-1, 0], 0.01)

    def test_limite_qualidade_e_sobreposicao(self):
        with tempfile.TemporaryDirectory() as td:
            pasta = Path(td)
            frases = []
            momentos = []
            for i in range(16):
                ini = i * 90
                frases.append({'s': ini + 0.2, 'e': ini + 20.5, 't': 'O boss chegou, agora é a luta final.'})
                momentos.append({'inicio': ini, 'fim': ini + 20, 'nota': 80 if i < 14 else 59,
                                 'titulo': 'Boss e gameplay', 'tipo': 'boss', 'motivo': 'luta',
                                 'legenda': 'Boss', 'hashtags': ['#jogo']})
            # Concorrente pior aparece antes do melhor e não pode bloqueá-lo.
            momentos.insert(0, {'inicio': 0, 'fim': 18, 'nota': 72, 'titulo': 'Corte pior',
                                'tipo': 'boss', 'motivo': 'luta', 'legenda': 'Boss', 'hashtags': ['#jogo']})
            (pasta / 'transcricao.json').write_text(json.dumps({'frases': frases}), encoding='utf-8')
            (pasta / 'momentos.json').write_text(json.dumps({'momentos': momentos}), encoding='utf-8')
            (pasta / 'sinais.json').write_text(json.dumps({'gritos': [], 'chat': []}), encoding='utf-8')
            cmd = [sys.executable, str(PASTA_FERRAMENTAS / 'conferir.py'), str(pasta), '--manter', '12', '--nota-minima', '70']
            r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(r.returncode, 0, r.stderr)
            dados = json.loads((pasta / 'momentos-conferidos.json').read_text(encoding='utf-8'))['momentos']
            aprovados = [m for m in dados if m['manter']]
            self.assertEqual(len(aprovados), 12)
            self.assertNotIn('Corte pior', [m['titulo'] for m in aprovados])
            self.assertTrue(all(m['nota'] >= 70 for m in aprovados))

    def test_pistas_gamer_nao_sao_fatos_visuais(self):
        self.assertIn('boss', ouvir.sinais_gamer('Chegou o boss!'))
        self.assertIn('jogada', ouvir.sinais_gamer('Foi um clutch inacreditável'))
        self.assertEqual(ouvir.sinais_gamer('Hoje choveu bastante'), [])

    def test_ass_legivel(self):
        with tempfile.TemporaryDirectory() as td:
            arq = Path(td) / 'legendas.ass'
            grupo = [{'w': 'QUE', 's': 0., 'e': 0.5}, {'w': 'BOSS', 's': 0.5, 'e': 1.0, 'mostra_ate': 1.2}]
            cortar._salvar_ass([grupo], cortar.ESTILO, arq)
            texto = arq.read_text(encoding='utf-8')
            self.assertIn('[Events]', texto)
            self.assertIn('Dialogue: 0,', texto)
            self.assertIn('BOSS', texto)


class TestRegrasNovas(unittest.TestCase):
    def test_entrega_escolhe_versao_mais_recente(self):
        with tempfile.TemporaryDirectory() as td:
            pasta = Path(td)
            for nome in ('01-a.mp4', '01-a-v2.mp4', '01-a-v3.mp4', '02-b.mp4'):
                (pasta / nome).write_bytes(b'x')
            cortes = [{'n': 1, 'arquivo': '01-a.mp4'}, {'n': 1, 'arquivo': '01-a-v3.mp4'},
                      {'n': 1, 'arquivo': '01-a-v2.mp4'}, {'n': 2, 'arquivo': '02-b.mp4'}]
            escolhidos = entregar.escolher(cortes, pasta)
            self.assertEqual([c['arquivo'] for c in escolhidos], ['01-a-v3.mp4', '02-b.mp4'])
            self.assertEqual(entregar.sem_versao('01-a-v3.mp4'), '01-a')

    def test_encerramento_encolhe_em_corte_curto(self):
        estilo = dict(cortar.ESTILO)
        enc = cortar.encerramento(estilo, 60)
        self.assertIsNotNone(enc)
        self.assertAlmostEqual(enc['seg'], 5.0)
        self.assertAlmostEqual(enc['inicio'], 55.0)
        curto = cortar.encerramento(estilo, 10)
        self.assertAlmostEqual(curto['seg'], 4.0)  # no máximo 40% do corte
        self.assertIsNone(cortar.encerramento(dict(estilo, encerramento={'ativo': False}), 60))

    def test_camera_inteira_dominante(self):
        # detecções parciais da webcam viram a câmera inteira; uma detecção exagerada é ignorada
        cx = [[1582,132,317,273],[1611,191,243,211],[1405,132,494,273],[1405,133,449,272],[1406,133,492,272],[0,0,1920,1080]]
        self.assertEqual(cortar.caixa_dominante(cx), [1405,132,494,273])
        self.assertTrue(cortar.dentro([1611,191,243,211], [1405,132,494,273]))
        self.assertFalse(cortar.dentro([0,0,1920,1080], [1405,132,494,273]))

    def test_entrega_sem_duplicar_e_limpa(self):
        with tempfile.TemporaryDirectory() as d:
            sh = Path(d) / "shorts"; sh.mkdir()
            for nome in ("01-a", "01-a-v2", "02-b"):
                for ext in (".mp4", ".txt"):
                    (sh / (nome + ext)).write_bytes(b"x" * 10)
                (sh / (nome + "-conferir.jpg")).write_bytes(b"j")
            (sh / "cortes.json").write_text("[]")
            dest = Path(d) / "entrega"; dest.mkdir()
            entregar.ligar(sh / "01-a-v2.mp4", dest / "01-a.mp4")
            self.assertEqual((dest / "01-a.mp4").read_bytes(), b"x" * 10)
            self.assertEqual(os.stat(dest / "01-a.mp4").st_nlink, 2)  # mesmo arquivo no disco, não cópia
            apagados, _ = entregar.limpar_shorts(sh, {"01-a-v2"})
            self.assertEqual(apagados, 6)
            self.assertEqual(sorted(p.name for p in sh.iterdir()),
                             ["01-a-v2-conferir.jpg", "01-a-v2.mp4", "01-a-v2.txt", "cortes.json"])
            self.assertTrue((dest / "01-a.mp4").exists())

    def test_esqueleto_carregado(self):
        self.assertEqual(cortar.ESTILO['altura_painel_camera'], 608)  # 16:9 como a webcam 1280x720
        self.assertEqual(cortar.ESTILO['fade_camera'], 90)
        self.assertAlmostEqual(cortar.ESTILO['altura_legenda'], 1574 / 1920.0)


class TestMelhorias(unittest.TestCase):
    def test_chat_twitch_downloader_e_youtube(self):
        with tempfile.TemporaryDirectory() as td:
            pasta = Path(td)
            (pasta / 'chat-twitch.json').write_text(json.dumps(
                {'video': {}, 'comments': [{'content_offset_seconds': 12.5}, {'content_offset_seconds': 3}]}), encoding='utf-8')
            linha = json.dumps({'replayChatItemAction': {'actions': [{'addChatItemAction': {}}], 'videoOffsetTimeMsec': '7000'}})
            (pasta / 'chat.live_chat.json').write_text(linha + '\n', encoding='utf-8')
            self.assertEqual(ouvir.tempos_do_chat(pasta), [3.0, 7.0, 12.5])
            self.assertTrue(ouvir.tem_chat(pasta))

    def test_trava_espera_o_outro_processo(self):
        with tempfile.TemporaryDirectory() as td:
            with comum.Trava(td, 'audio'):
                self.assertTrue((Path(td) / '.trava-audio').exists())
                with self.assertRaises(TimeoutError):
                    with comum.Trava(td, 'audio', espera=0.5):
                        pass
            self.assertFalse((Path(td) / '.trava-audio').exists())
            # trava esquecida por um processo que morreu é ignorada
            velha = Path(td) / '.trava-audio'
            velha.write_text('1')
            os.utime(velha, (time.time() - 99999, time.time() - 99999))
            with comum.Trava(td, 'audio', espera=1):
                pass

    def test_mediana_rapida_igual_ao_laco(self):
        x = np.random.default_rng(1).normal(size=2000)
        lento = np.array([np.median(x[max(0, i - 15): i + 16]) for i in range(len(x))])
        self.assertTrue(np.allclose(ouvir.mediana_que_anda(x, 15, bloco=300), lento))
        self.assertTrue(np.allclose(ouvir.mediana_que_anda(x[:10], 15), [np.median(x[:10])] * 10))

    def test_palavras_gravadas_relativas_ao_corte(self):
        frases = [{'s': 99, 'e': 103, 't': 'olha o boss', 'p': [{'w': 'olha', 's': 99.0, 'e': 99.6},
                  {'w': 'o', 's': 100.2, 'e': 100.4}, {'w': 'boss', 's': 100.5, 'e': 101.0}]}]
        ws = cortar.palavras_gravadas(frases, 100.0, 110.0)
        self.assertEqual([w['w'] for w in ws], ['o', 'boss'])
        self.assertAlmostEqual(ws[0]['s'], 0.2)
        self.assertIsNone(cortar.palavras_gravadas([{'s': 0, 'e': 1, 't': 'x'}], 0, 1))  # transcrição antiga

    def test_conferir_padrao_por_hora_e_maximo_60(self):
        with tempfile.TemporaryDirectory() as td:
            pasta = Path(td)
            frases = [{'s': 0.2, 'e': 30, 't': 'Olha o boss chegando.'}, {'s': 100.2, 'e': 170, 't': 'Agora a luta longa.'}]
            momentos = [{'inicio': 0, 'fim': 30, 'nota': 66, 'titulo': 'Curto e bom'},
                        {'inicio': 100, 'fim': 170, 'nota': 90, 'titulo': 'Longo demais'}]
            (pasta / 'transcricao.json').write_text(json.dumps({'frases': frases}), encoding='utf-8')
            (pasta / 'momentos.json').write_text(json.dumps({'momentos': momentos}), encoding='utf-8')
            r = subprocess.run([sys.executable, str(PASTA_FERRAMENTAS / 'conferir.py'), str(pasta)],
                               capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(r.returncode, 0, r.stderr)
            dados = {m['titulo']: m for m in json.loads((pasta / 'momentos-conferidos.json').read_text(encoding='utf-8'))['momentos']}
            self.assertTrue(dados['Curto e bom']['manter'])   # nota 66 passa no padrão 65
            self.assertFalse(dados['Longo demais']['manter'])  # 70 s passa do teto de 60

    def test_limpar_so_lista_sem_apagar(self):
        with tempfile.TemporaryDirectory() as td:
            raiz = Path(td) / 'lives' / 'v1'
            (raiz / 'hora-1' / 'trechos').mkdir(parents=True)
            (raiz / 'hora-1' / 'trechos' / '01.mp4').write_bytes(b'x' * 100)
            (raiz / 'audio.mp4').write_bytes(b'a' * 50)
            (raiz / 'info.json').write_text(json.dumps({'duracao': 3000}), encoding='utf-8')
            (raiz / 'hora-1' / 'info.json').write_text('{}', encoding='utf-8')
            (raiz / 'hora-1' / 'entrega.json').write_text(json.dumps({'quando': '2020-01-01 10:00:00'}), encoding='utf-8')
            em_corte = Path(td) / 'lives' / 'v2'  # live ainda sem entrega: não é tocada
            (em_corte / 'hora-1').mkdir(parents=True)
            (em_corte / 'audio.mp4').write_bytes(b'a')
            lista = limpar.candidatos_trabalho(Path(td) / 'lives')
            self.assertEqual(sorted(p.name for p, _, _ in lista), ['audio.mp4', 'trechos'])
            self.assertTrue((raiz / 'hora-1' / 'trechos' / '01.mp4').exists())  # listar não apaga
            self.assertIn('v2', [p.name for p, _, _ in limpar.candidatos_trabalho(Path(td) / 'lives', sem_entrega=True)])

    def test_desempenho_liga_posts_aos_shorts(self):
        shorts = [{'titulo': 'Achei um laboratório de caranguejo mutante', 'tipo': 'descoberta / reação', 'duracao': 38, 'nota': 85},
                  {'titulo': 'Esse boss não me deu chance', 'tipo': 'boss', 'duracao': 55, 'nota': 70}]
        posts = [{'text': 'ACHEI UM LABORATÓRIO DE CARANGUEJO MUTANTE #gta6 #tiojoaoyt', 'views': 12000},
                 {'title': 'Esse boss não me deu chance', 'videoViews': '800', 'averageViewPercentage': '61%'},
                 {'text': 'post sem relação', 'views': 5}]
        with tempfile.TemporaryDirectory() as td:
            arq = Path(td) / 'm.json'
            arq.write_text(json.dumps({'data': posts}), encoding='utf-8')
            lidos = desempenho.ler_posts([arq])
        self.assertEqual(len(lidos), 3)
        linhas, ligados = desempenho.relatorio(lidos, shorts)
        self.assertEqual(len(ligados), 2)
        self.assertIn('| descoberta | 1 | 12000 |', '\n'.join(linhas))
        self.assertEqual(desempenho.faixa(38), '30–45 s')

    def test_desempenho_liga_por_numero_e_texto_postado(self):
        shorts = [{'titulo': 'Fui abduzido e sumi por três dias', 'tipo': 'história'},
                  {'titulo': 'A Lúcia meteu uma chave de braço', 'tipo': 'reação', 'postado': ['A Lúcia meteu um mata leão!']}]
        abduzido = {'texto': 'FUI ABDUZIDO E SUMI POR 3 DIAS! 🛸 A nave levou a gente', 'views': 1312, 'retencao': None, 'skip': 30.0}
        lucia = {'texto': 'A Lúcia meteu um mata leão! 💀 kkkk #GTA6', 'views': 1452, 'retencao': None, 'skip': 21.1}
        outro = {'texto': 'Post de outra live', 'views': 10, 'retencao': None, 'skip': 50.0}
        self.assertEqual(desempenho.ligar(abduzido, shorts)['tipo'], 'história')
        self.assertEqual(desempenho.ligar(lucia, shorts)['tipo'], 'reação')
        self.assertIsNone(desempenho.ligar(outro, shorts))
        linhas, ligados = desempenho.relatorio([abduzido, lucia, outro], shorts)
        texto = '\n'.join(linhas)
        self.assertEqual(len(ligados), 2)
        self.assertIn('pulou em 3 s', texto)
        self.assertIn('Post de outra live', texto)  # posts soltos aparecem à parte

    def test_pipeline_status_por_hora(self):
        with tempfile.TemporaryDirectory() as td:
            h = Path(td) / 'hora-2'
            (h / 'shorts').mkdir(parents=True)
            (h / 'transcricao.json').write_text(json.dumps({'completa': True, 'hora': 2}), encoding='utf-8')
            (h / 'momentos.json').write_text(json.dumps({'momentos': [{}, {}]}), encoding='utf-8')
            e = pipeline.estado_da_hora(h)
            self.assertTrue(e['transcrita'])
            self.assertEqual(e['momentos'], 2)
            self.assertEqual(e['proximo'], 'conferir.py')

    def test_gpu_desligada_usa_libx264(self):
        params = cortar.codificador(dict(cortar.ESTILO, gpu=False))
        self.assertIn(params[1], ('libx264', 'h264_videotoolbox', 'mpeg4'))
        self.assertIn('-qvbr_quality_level', cortar.parametros_gpu('h264_amf', cortar.ESTILO))


class TestEntregaOrganizada(unittest.TestCase):
    def _hora(self, raiz, h, titulos):
        p = raiz / ('hora-%d' % h)
        (p / 'shorts').mkdir(parents=True)
        (p / 'info.json').write_text(json.dumps({'id': 'v123', 'site': 'TwitchVod', 'duracao': 9000, 'hora': h,
                                                 'canal': 'tiojoaoyt', 'titulo': 'live', 'link': 'x'}), encoding='utf-8')
        cortes, momentos = [], []
        for n, t in enumerate(titulos, 1):
            arq = '%02d-corte.mp4' % n
            (p / 'shorts' / arq).write_bytes(b'v' * 10)
            (p / 'shorts' / arq.replace('.mp4', '.txt')).write_text('TÍTULO\n%s\n' % t, encoding='utf-8')
            cortes.append({'n': n, 'arquivo': arq, 'titulo': t, 'duracao': 30, 'nota': 70, 'inicio': '0:0%d:00' % n})
            momentos.append({'n': n, 'manter': True, 'inicio_s': n * 60, 'titulo': t, 'tipo': 'humor',
                             'legenda': 'leg', 'hashtags': ['#GTA6']})
        (p / 'shorts' / 'cortes.json').write_text(json.dumps(cortes), encoding='utf-8')
        (p / 'momentos-conferidos.json').write_text(json.dumps({'momentos': momentos}), encoding='utf-8')
        return p

    def test_uma_pasta_legivel_por_live(self):
        with tempfile.TemporaryDirectory() as td:
            raiz = Path(td) / 'lives' / 'v123'
            h1 = self._hora(raiz, 1, ['A Lúcia tá mentindo?', 'Bug: o carro voou'])
            h2 = self._hora(raiz, 2, ['O ET apareceu'])
            destino = Path(td) / 'entrega'
            for h in (h1, h2):
                r = subprocess.run([sys.executable, str(PASTA_FERRAMENTAS / 'entregar.py'), str(h), '--destino', str(destino),
                                    '--manter-tudo'], capture_output=True, text=True, encoding='utf-8')
                self.assertEqual(r.returncode, 0, r.stderr)
            pastas = [p for p in destino.iterdir() if p.is_dir()]
            self.assertEqual(len(pastas), 1)  # as duas horas na mesma pasta da live
            live = pastas[0]
            self.assertRegex(live.name, r'^\d{4}-\d\d-\d\d - Twitch - live de 2h30 \(v123\)$')
            self.assertEqual(sorted(p.name for p in live.glob('*.mp4')),
                             ['Hora 1 - 01 - A Lúcia tá mentindo.mp4', 'Hora 1 - 02 - Bug o carro voou.mp4',
                              'Hora 2 - 01 - O ET apareceu.mp4'])
            self.assertTrue((live / 'textos' / 'Hora 2 - 01 - O ET apareceu.txt').exists())
            leia = (live / 'LEIA-ME.txt').read_text(encoding='utf-8')
            self.assertIn('Hora 1: 2 shorts', leia)
            self.assertIn('Hora 2: 1 shorts', leia)
            # reentregar a hora 1 com outra lista troca só os arquivos da hora 1
            (h1 / 'shorts' / 'cortes.json').write_text(json.dumps([json.loads((h1 / 'shorts' / 'cortes.json').read_text(encoding='utf-8'))[0]]), encoding='utf-8')
            subprocess.run([sys.executable, str(PASTA_FERRAMENTAS / 'entregar.py'), str(h1), '--destino', str(destino), '--manter-tudo'],
                           capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(sorted(p.name for p in live.glob('*.mp4')),
                             ['Hora 1 - 01 - A Lúcia tá mentindo.mp4', 'Hora 2 - 01 - O ET apareceu.mp4'])
            self.assertEqual(entregar.titulo_de_arquivo('Que isso?! / "teste": ok.'), 'Que isso! teste ok')


class TestLegendaSoDoStreamer(unittest.TestCase):
    def test_fala_do_jogo_sai_da_legenda(self):
        # áudio de mentira: 1 s de 'português' (valor 1) e 1 s de 'inglês' (valor 2), alternando
        taxa = comum.TAXA
        som = np.concatenate([np.full(taxa * 2, 1, np.int16), np.full(taxa * 3, 2, np.int16), np.full(taxa * 2, 1, np.int16)])
        detector = lambda a: (('en', 0.9) if len(a) and a.mean() > 1.5 else ('pt', 0.95))
        trechos = [(0.0, 2.0), (2.0, 5.0), (5.0, 7.0), (6.5, 7.0)]  # o último é curto demais para medir: fica
        jogo = cortar.falas_do_jogo(trechos, som, 0.0, 'pt', detector=detector)
        self.assertEqual(jogo, [(2.0, 5.0, 'en')])
        palavras = [{'w': 'caraca', 's': 0.5, 'e': 1.0}, {'w': 'you', 's': 2.5, 'e': 3.0},
                    {'w': 'guys', 's': 4.0, 'e': 4.5}, {'w': 'mano', 's': 5.5, 'e': 6.0}]
        self.assertEqual([w['w'] for w in cortar.sem_falas_do_jogo(palavras, jogo)], ['caraca', 'mano'])
        fracao, idiomas = cortar.resumo_jogo(trechos[:3], jogo)
        self.assertAlmostEqual(fracao, 3 / 7.0)
        self.assertEqual(idiomas, ['en'])
        self.assertLess(fracao, cortar.ALERTA_JOGO)

    def test_alerta_quando_o_jogo_domina(self):
        jogo = [(0.0, 8.0, 'en')]
        fracao, _ = cortar.resumo_jogo([(0.0, 8.0), (8.0, 10.0)], jogo)
        self.assertGreaterEqual(fracao, cortar.ALERTA_JOGO)

    def test_trechos_de_fala_relativos_ao_corte(self):
        frases = [{'s': 98, 'e': 101, 't': 'a'}, {'s': 103, 'e': 120, 't': 'b'}, {'s': 130, 'e': 131, 't': 'fora'}]
        self.assertEqual(cortar.trechos_de_fala(frases, 100.0, 110.0), [(0.0, 1.0), (3.0, 10.0)])

    def test_mesmo_idioma_nunca_sai(self):
        som = np.zeros(comum.TAXA * 3, np.int16)
        self.assertEqual(cortar.falas_do_jogo([(0.0, 3.0)], som, 0.0, 'pt', detector=lambda a: ('pt', 0.99)), [])
        self.assertEqual(cortar.falas_do_jogo([(0.0, 3.0)], som, 0.0, 'pt', detector=lambda a: ('en', 0.3)), [])  # incerto: fica


class TestMelhorias2(unittest.TestCase):
    def test_texto_em_ingles_e_fala_do_jogo(self):
        for t in ['This is scary. You guys are in a world', 'Thank you for telling us.', 'What can I get you?']:
            self.assertTrue(comum.parece_fala_do_jogo(t), t)
        for t in ['Caraca, Lucia. Para de tratar o maluco', 'Okay, bebê', 'Mano, isso é scooter, boss', 'Oh my']:
            self.assertFalse(comum.parece_fala_do_jogo(t), t)

    def test_enquadrar_a_gameplay(self):
        self.assertEqual(cortar.posicao_do_jogo('direita', 100, 600, 1920), 1320)
        self.assertEqual(cortar.posicao_do_jogo('esquerda', 100, 600, 1920), 0)
        self.assertEqual(cortar.posicao_do_jogo(None, 100, 600, 1920), 100)
        self.assertEqual(cortar.posicao_do_jogo(0.5, 100, 600, 1920), 660)
        cam = {'modo': 'facecam', 'camera': [20, 20, 300, 180], 'rosto': [80, 30, 100, 100]}
        jx_dir = cortar.recortes(cam, 1920, 1080, dict(cortar.ESTILO, enquadrar='direita'))['jogo'][0]
        jw = cortar.recortes(cam, 1920, 1080, cortar.ESTILO)['jogo'][2]
        self.assertEqual(jx_dir, 1920 - jw)

    def test_agendar_horarios_livres_e_texto(self):
        import datetime as dt
        import agendar
        dia = dt.date.today() + dt.timedelta(days=3)
        tomados = [dt.datetime.combine(dia, dt.time(10)), dt.datetime.combine(dia, dt.time(16, 30))]
        livres = agendar.horarios_livres(tomados, dia, dia, 3)
        self.assertEqual([h.hour for h in livres], [13, 18, 21])  # 16h fica a 30 min de um post: pula
        post = agendar.montar_post({'titulo': 'Fui dormir e acordei numa nave', 'tipo': 'mistério / reação',
                                    'legenda': 'O que aconteceu?', 'hashtags': ['#GTA6', '#OVNI', '#TiojoaoYT']},
                                   'Hora 3 - 01 - x.mp4', livres[0], 'https://x/v.mp4')
        self.assertTrue(post['texto'].startswith('FUI DORMIR E ACORDEI NUMA NAVE! 👽'))
        self.assertEqual(post['titulo_youtube'], 'FUI DORMIR E ACORDEI NUMA NAVE! 👽 | GTA 6 #Shorts')
        self.assertIn('Lives TODOS OS DIAS', post['comentario_fixado'])

    def test_limpar_agendados_respeita_data_da_entrega(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            destino = base / 'entrega' / 'live'
            (destino / 'textos').mkdir(parents=True)
            video = destino / 'Hora 1 - 01 - A Lucia tá traindo o Jason.mp4'
            video.write_bytes(b'v')
            (destino / 'textos' / (video.stem + '.txt')).write_text('t', encoding='utf-8')
            h = base / 'lives' / 'v1' / 'hora-1'
            h.mkdir(parents=True)
            (h / 'info.json').write_text('{}', encoding='utf-8')
            (h / 'entrega.json').write_text(json.dumps({'quando': '2026-11-24 02:00:00', 'destino': str(destino),
                                                        'shorts': [{'arquivo': video.name, 'titulo': 'A Lucia tá traindo o Jason'}]}),
                                            encoding='utf-8')
            antigo = [{'creationDate': {'dateTime': '2026-11-21T00:38:00'}, 'text': 'A LUCIA TÁ TRAINDO O JASON?! 👀'}]
            novo = [{'creationDate': {'dateTime': '2026-11-25T10:00:00'}, 'text': 'A LUCIA TÁ TRAINDO O JASON?! 👀',
                     'youtubeData': {'title': 'A LUCIA TÁ TRAINDO O JASON?! 👀 | GTA 6 #Shorts'}}]
            self.assertEqual(limpar.candidatos_agendados(antigo, base / 'lives'), [])  # post de outra live, mais antigo
            achados = limpar.candidatos_agendados(novo, base / 'lives')
            self.assertEqual(sorted(p.suffix for p, _, _ in achados), ['.mp4', '.txt'])
            self.assertTrue(video.exists())  # listar não apaga


if __name__ == '__main__':
    unittest.main()
