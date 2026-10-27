"""PC Estribado: limpeza, saúde e atualizações do Windows numa janela só."""
import ctypes
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import winreg
from concurrent.futures import ThreadPoolExecutor

import webview

import atualizacoes
import atualizador
import automatico
import diagnostico
import estado
import hardware
import inicializacao
import limpeza
import sistema

VERSAO = "1.0.0"
_PORCENTAGEM = re.compile(r"\d+(?:[.,]\d+)?\s*%")


def _recurso(*partes):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *partes)


def eh_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def pedir_admin():
    """Reabre o programa como administrador. True se a nova instância foi aberta."""
    if getattr(sys, "frozen", False):
        parametros = subprocess.list2cmdline(sys.argv[1:])
    else:
        parametros = subprocess.list2cmdline([os.path.abspath(__file__), *sys.argv[1:]])
    return ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, parametros, None, 1) > 32


def _versao_windows():
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as k:
            nome = winreg.QueryValueEx(k, "ProductName")[0]
            versao = winreg.QueryValueEx(k, "DisplayVersion")[0]
            build = int(winreg.QueryValueEx(k, "CurrentBuildNumber")[0])
    except OSError:
        return "Windows"
    if build >= 22000:  # o registro do Windows 11 ainda diz "Windows 10"
        nome = nome.replace("Windows 10", "Windows 11")
    return f"{nome} {versao}"


def _seguro(funcao, *args):
    """Chama a função e devolve {ok, dados} ou {ok: False, erro} pra interface."""
    try:
        return {"ok": True, "dados": funcao(*args)}
    except Exception as e:
        return {"ok": False, "erro": str(e) or e.__class__.__name__}


class Api:
    def __init__(self):
        self._janela = None
        self._trava = threading.Lock()
        self._ctl = None  # tarefa em andamento

    def _enviar(self, tipo, **dados):
        if self._janela:
            self._janela.evaluate_js(f"window.receber({json.dumps(dict(tipo=tipo, **dados))})")

    def _tarefa(self, titulo, funcao, ao_concluir=None):
        """Roda uma tarefa demorada em segundo plano, mandando a saída ao vivo pra tela.
        A função recebe (linha, progresso, ctl) e deve chamar ctl.checar() de vez em quando."""
        with self._trava:
            if self._ctl:
                return {"ok": False, "erro": f"Já tem uma tarefa rodando ({self._ctl.titulo}). Espera ela terminar ou cancela."}
            ctl = self._ctl = sistema.Controle(titulo)

        def atual():
            return self._ctl is ctl

        # no log, linhas de progresso ("45% concluído") ficam só a última de cada sequência
        progresso_pendente = []

        def gravar_pendente():
            if progresso_pendente:
                estado.log(progresso_pendente.pop())

        def linha(texto):
            if _PORCENTAGEM.search(texto):
                progresso_pendente[:] = [texto]
            else:
                gravar_pendente()
                estado.log(texto)
            if atual():
                self._enviar("linha", texto=texto)

        def progresso(valor):
            if atual():
                self._enviar("progresso", valor=valor)

        def rodar():
            estado.log(f"===== {titulo} =====")
            self._enviar("inicio", titulo=titulo)
            ok, cancelado, resultado = True, False, None
            try:
                resultado = funcao(linha, progresso, ctl)
                if ao_concluir:
                    ao_concluir(resultado)
            except sistema.Cancelado:
                ok, cancelado = False, True
                linha("Cancelado.")
            except Exception as e:
                ok = False
                linha(f"Erro: {e}")
            gravar_pendente()
            self._encerrar(ctl, ok, cancelado, resultado)

        threading.Thread(target=rodar, daemon=True).start()
        return {"ok": True}

    def _encerrar(self, ctl, ok, cancelado, resultado=None):
        with self._trava:
            if self._ctl is not ctl:
                return  # já foi liberada pelo cancelar
            self._ctl = None
        self._enviar("fim", titulo=ctl.titulo, ok=ok, cancelado=cancelado, resultado=resultado)

    def cancelar(self):
        ctl = self._ctl
        if not ctl:
            return {"ok": False, "erro": "Nada rodando."}
        estado.log(f"Cancelando: {ctl.titulo}")
        threading.Thread(target=ctl.cancelar, daemon=True).start()

        def vigiar():
            # se a tarefa não parar sozinha em 8s, libera a tela mesmo assim
            time.sleep(8)
            self._encerrar(ctl, False, True)
        threading.Thread(target=vigiar, daemon=True).start()
        return {"ok": True}

    # ---------- Início ----------

    def info(self):
        return dict(admin=eh_admin(), windows=_versao_windows(), pc=os.environ.get("COMPUTERNAME", ""),
                    usuario=os.environ.get("USERNAME", "").capitalize(), versao=VERSAO)

    def reabrir_admin(self):
        if pedir_admin():
            self._janela.destroy()

    def hardware(self):
        return _seguro(hardware.info)

    def metricas(self):
        return hardware.metricas()

    def resumo_saude(self):
        """Tudo que entra na nota de saúde do PC, buscado em paralelo."""
        with ThreadPoolExecutor(4) as ex:
            defender = ex.submit(_seguro, sistema.defender_status)
            discos = ex.submit(_seguro, sistema.discos_saude)
            auto = ex.submit(_seguro, automatico.status)
            startup = ex.submit(_seguro, inicializacao.listar)
        c = hardware.discos()
        sistema_disco = next((d for d in c if d["letra"].upper() == sistema.UNIDADE.upper()), c[0] if c else None)
        return dict(
            estado=estado.ler(), agora=time.time(),
            defender=defender.result(), discos=discos.result(), auto=auto.result(),
            startup_ativos=sum(1 for i in startup.result().get("dados", []) if i["ativo"]),
            reinicio=sistema.reinicio_pendente(), disco=sistema_disco,
        )

    # ---------- Registro (log) e diagnóstico ----------

    def log_ler(self):
        return diagnostico.ler_log(800)

    def log_copiar(self):
        texto = "\n".join(diagnostico.ler_log(800))
        subprocess.run(["clip"], input=texto.encode("utf-16-le"), creationflags=sistema.SEM_JANELA, timeout=15)
        return {"ok": True}

    def log_limpar(self):
        estado.limpar_log()

    def log_pasta(self):
        os.makedirs(estado.PASTA, exist_ok=True)
        os.startfile(estado.PASTA)

    def problemas(self):
        return diagnostico.problemas(eh_admin())

    def resolver_tudo(self, passos):
        """Roda em sequência os reparos escolhidos na tela de início. Um passo que falha não para os outros."""
        etapas = {
            "limpeza": ("Limpeza", lambda l, p, c: limpeza.limpar([a["id"] for a in limpeza.ALVOS if a["padrao"]], l, p, c)),
            "antivirus": ("Antivírus", lambda l, p, c: sistema.rodar_acao("defender_atualizar", l, p, c)),
            "checagem": ("Checagem do sistema", lambda l, p, c: [sistema.rodar_acao(a, l, p, c) for a in ("dism", "sfc")]),
            "programas": ("Programas", lambda l, p, c: atualizacoes.winget_atualizar(None, l, p, c)),
            "windows": ("Windows Update", lambda l, p, c: atualizacoes.wu_instalar_tudo(False, l, p, c)),
            "automatico": ("Manutenção automática", lambda l, p, c: automatico.ativar("sexta", "12:00")),
        }
        passos = [p for p in passos if p in etapas]
        if not passos:
            return {"ok": False, "erro": "Nada escolhido."}

        def f(linha, progresso, ctl):
            for i, passo in enumerate(passos, 1):
                ctl.checar()
                nome, funcao = etapas[passo]
                linha(f"━━━ {i}/{len(passos)}: {nome} ━━━")
                try:
                    funcao(linha, progresso, ctl)
                    marcas = {"limpeza": "ultima_limpeza", "checagem": "ultima_checagem"}
                    if passo in marcas:
                        estado.marcar(marcas[passo])
                    if passo == "checagem":
                        diagnostico.marcar_resolvido("dism_sfc")
                except sistema.Cancelado:
                    raise
                except Exception as e:
                    linha(f"⚠ {nome} deu erro: {e}. Seguindo pro próximo.")
            linha("Tudo feito! Se alguma atualização pediu, reinicie o PC.")
        return self._tarefa("Resolver tudo", f)

    def ponto_restauracao(self):
        return self._tarefa("Ponto de restauração", lambda linha, progresso, ctl: sistema.ponto_restauracao(linha, ctl))

    # ---------- Limpeza ----------

    def alvos(self):
        return limpeza.publico()

    def analisar(self, ids):
        return limpeza.analisar(ids)

    def fechar_navegador(self, exe):
        return limpeza.fechar(exe)

    def limpar(self, ids):
        def f(linha, progresso, ctl):
            total, itens = limpeza.limpar(ids, linha, progresso, ctl)
            linha(f"Pronto! {limpeza.formatar(total)} liberados no total.")
            return dict(total=total, itens=itens)
        return self._tarefa("Limpeza", f, lambda _: estado.marcar("ultima_limpeza"))

    # ---------- Saúde e ferramentas ----------

    def acao(self, qual):
        """Roda ferramentas do sistema.ACOES/REPAROS ('tudo' = DISM + SFC + CHKDSK, 'dism_sfc' = DISM + SFC)."""
        acoes = {"tudo": ["dism", "sfc", "chkdsk"], "dism_sfc": ["dism", "sfc"]}.get(qual, [qual])
        if any(a not in sistema.ACOES and a not in sistema.REPAROS for a in acoes):
            return {"ok": False, "erro": "Ação inválida"}

        def f(linha, progresso, ctl):
            return [sistema.rodar_acao(a, linha, progresso, ctl) for a in acoes]

        def concluir(codigos):
            if {"sfc", "dism"} & set(acoes):
                estado.marcar("ultima_checagem")
            if any(a.startswith("defender_") and a != "defender_atualizar" for a in acoes):
                estado.marcar("ultima_verificacao_virus")
            if "componentes" in acoes:
                estado.marcar("ultima_limpeza_profunda")
            if "otimizar" in acoes:
                estado.marcar("ultima_otimizacao")
            if all(c == 0 for c in codigos):
                diagnostico.marcar_resolvido(qual)

        nomes = {"tudo": "Checagem completa", "dism_sfc": "DISM + SFC"}
        titulo = nomes.get(qual) or (sistema.ACOES.get(qual) or sistema.REPAROS[qual])[0]
        return self._tarefa(titulo, f, concluir)

    def defender_status(self):
        return _seguro(sistema.defender_status)

    def discos_saude(self):
        return _seguro(sistema.discos_saude)

    # ---------- Atualizações ----------

    def winget_listar(self):
        r = _seguro(atualizacoes.winget_listar)
        if r["ok"]:
            estado.marcar("pendentes_programas", len(r["dados"]))
        return r

    def winget_atualizar(self, pacote=None):
        titulo = f"Atualizando {pacote}" if pacote else "Atualizando todos os programas"
        return self._tarefa(titulo, lambda linha, progresso, ctl: atualizacoes.winget_atualizar(pacote, linha, progresso, ctl))

    def wu_buscar(self, drivers=False):
        r = _seguro(atualizacoes.wu_buscar, drivers)
        if r["ok"]:
            estado.marcar("pendentes_drivers" if drivers else "pendentes_windows", len(r["dados"]))
        return r

    def wu_historico(self):
        return _seguro(atualizacoes.wu_historico)

    def wu_instalar(self, ids, criar_ponto):
        def f(linha, progresso, ctl):
            if criar_ponto:
                linha("Criando ponto de restauração antes...")
                sistema.ponto_restauracao(linha, ctl)
            return atualizacoes.wu_instalar(ids, linha, progresso, ctl)
        return self._tarefa("Instalando atualizações", f)

    def wu_instalar_tudo(self, drivers, criar_ponto):
        def f(linha, progresso, ctl):
            if criar_ponto:
                linha("Criando ponto de restauração antes...")
                sistema.ponto_restauracao(linha, ctl)
            return atualizacoes.wu_instalar_tudo(drivers, linha, progresso, ctl)
        return self._tarefa("Instalando atualizações", f)

    def reinicio_pendente(self):
        return sistema.reinicio_pendente()

    def reiniciar(self):
        estado.log("Reinicialização pedida pelo usuário.")
        sistema.reiniciar()

    def drivers_problemas(self):
        return _seguro(atualizacoes.dispositivos_problema)

    def drivers_principais(self):
        return _seguro(atualizacoes.drivers_principais)

    def pesquisar_driver(self, nome):
        os.startfile("https://www.google.com/search?q=" + urllib.parse.quote(f"driver {nome} download site oficial"))

    # ---------- Inicialização ----------

    def startup_listar(self):
        return inicializacao.listar()

    def startup_definir(self, item_id, ativo):
        try:
            inicializacao.definir(item_id, ativo)
            estado.log(f"Inicialização: {item_id} -> {'ativado' if ativo else 'desativado'}")
            return {"ok": True}
        except PermissionError:
            return {"ok": False, "erro": "Precisa abrir o PC Estribado como administrador pra mudar esse item."}
        except Exception as e:
            return {"ok": False, "erro": str(e)}

    # ---------- Atualização do próprio programa ----------

    def atualizacao_verificar(self, automatico=False):
        r = _seguro(atualizador.verificar, VERSAO, automatico)
        if r["ok"]:
            r["dados"]["auto"] = estado.ler().get("atualizacao_auto", True)
        return r

    def abrir_projeto(self):
        os.startfile(f"https://github.com/{atualizador.REPOSITORIO}")

    def atualizacao_config(self, auto):
        estado.marcar("atualizacao_auto", bool(auto))

    def atualizacao_instalar(self):
        def f(linha, progresso, ctl):
            linha("Conferindo a última versão publicada...")
            info = atualizador.verificar(VERSAO)
            if not info.get("nova"):
                linha(f"Você já está na versão mais nova ({VERSAO}).")
                return
            caminho = atualizador.baixar(info, linha, progresso, ctl)
            linha("Abrindo o instalador. O PC Estribado vai fechar e abrir de novo sozinho em alguns segundos...")
            time.sleep(2)
            atualizador.instalar(caminho)
            self._janela.destroy()
        return self._tarefa("Atualizando o PC Estribado", f)

    # ---------- Manutenção automática ----------

    def auto_status(self):
        return _seguro(automatico.status)

    def auto_ativar(self, dia, hora):
        return _seguro(automatico.ativar, dia, hora)

    def auto_desativar(self):
        return _seguro(automatico.desativar)


def main():
    if "--auto" in sys.argv:
        automatico.rodar()
        return
    if "--desinstalar" in sys.argv:  # chamado pelo desinstalador
        automatico.desativar()
        return
    if not eh_admin() and "--sem-admin" not in sys.argv and pedir_admin():
        return
    if getattr(sys, "frozen", False):
        threading.Thread(target=lambda: _seguro(automatico.corrigir_caminho), daemon=True).start()
    api = Api()
    janela = webview.create_window("PC Estribado", _recurso("web", "index.html"), js_api=api,
                                   width=1240, height=820, min_size=(1000, 660), background_color="#0b0f15")
    api._janela = janela
    webview.start()


if __name__ == "__main__":
    main()
