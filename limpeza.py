"""Alvos de limpeza: temporários do Windows, lixeira, Chrome e Edge."""
import ctypes
import glob
import os
import stat
import subprocess

SEM_JANELA = subprocess.CREATE_NO_WINDOW

LOCAL = os.environ.get("LOCALAPPDATA", "")
WINDIR = os.environ.get("WINDIR", r"C:\Windows")
PROGRAMDATA = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
TEMP_USUARIO = os.environ.get("TEMP", os.path.join(LOCAL, "Temp"))

CHROME = os.path.join(LOCAL, "Google", "Chrome", "User Data")
EDGE = os.path.join(LOCAL, "Microsoft", "Edge", "User Data")

# Subpastas/arquivos dentro de cada perfil do navegador
CACHE_NAV = ["Cache", "Code Cache", "GPUCache",
             r"Service Worker\CacheStorage", r"Service Worker\ScriptCache"]
CACHE_NAV_RAIZ = ["ShaderCache", "GrShaderCache", "GraphiteDawnCache"]
HISTORICO_NAV = ["History", "History-journal", "Visited Links", "Top Sites",
                 "Top Sites-journal", "Shortcuts", "Shortcuts-journal"]
COOKIES_NAV = [r"Network\Cookies", r"Network\Cookies-journal"]

NAVEGADORES = {"chrome.exe": "Chrome", "msedge.exe": "Edge"}


def _perfis(base):
    """Pastas de perfil do navegador (Default, Profile 1, ...)."""
    if not os.path.isdir(base):
        return []
    return [os.path.join(base, n) for n in os.listdir(base)
            if n == "Default" or n.startswith("Profile ")]


def _navegador(grupo, prefixo, base, exe):
    def em_perfis(nomes):
        return lambda: [os.path.join(p, n) for p in _perfis(base) for n in nomes]

    return [
        dict(id=f"{prefixo}_cache", grupo=grupo, nome="Cache",
             desc="Imagens e arquivos de sites guardados. Os sites só carregam um pouco mais devagar na primeira visita.",
             padrao=True, processo=exe,
             pastas=lambda: em_perfis(CACHE_NAV)() + [os.path.join(base, n) for n in CACHE_NAV_RAIZ]),
        dict(id=f"{prefixo}_historico", grupo=grupo, nome="Histórico",
             desc="Sites visitados e atalhos da página inicial.",
             padrao=False, processo=exe, arquivos=em_perfis(HISTORICO_NAV)),
        dict(id=f"{prefixo}_cookies", grupo=grupo, nome="Cookies",
             desc="Atenção: você vai ser deslogado de todos os sites.",
             padrao=False, processo=exe, arquivos=em_perfis(COOKIES_NAV)),
    ]


ALVOS = [
    dict(id="temp_usuario", grupo="Windows", nome="Temporários do usuário",
         desc="Pasta %TEMP%: sobras de instaladores e programas.", padrao=True,
         pastas=lambda: [TEMP_USUARIO]),
    dict(id="temp_windows", grupo="Windows", nome="Temporários do Windows",
         desc="Pasta C:\\Windows\\Temp.", padrao=True,
         pastas=lambda: [os.path.join(WINDIR, "Temp")]),
    dict(id="windows_update", grupo="Windows", nome="Cache do Windows Update",
         desc="Instaladores de atualizações que já foram aplicadas.", padrao=True,
         pastas=lambda: [os.path.join(WINDIR, "SoftwareDistribution", "Download")]),
    dict(id="relatorios_erro", grupo="Windows", nome="Relatórios de erro",
         desc="Relatórios de travamento e dumps de programas.", padrao=True,
         pastas=lambda: [os.path.join(PROGRAMDATA, r"Microsoft\Windows\WER\ReportArchive"),
                         os.path.join(PROGRAMDATA, r"Microsoft\Windows\WER\ReportQueue"),
                         os.path.join(LOCAL, "CrashDumps")]),
    dict(id="miniaturas", grupo="Windows", nome="Cache de miniaturas",
         desc="Prévias de imagens do Explorer. São recriadas quando precisar.", padrao=False,
         arquivos=lambda: glob.glob(os.path.join(LOCAL, r"Microsoft\Windows\Explorer\thumbcache_*.db"))),
    dict(id="lixeira", grupo="Windows", nome="Lixeira",
         desc="Esvazia a lixeira de todos os discos. Não dá pra recuperar depois.", padrao=False,
         especial="lixeira"),
] + _navegador("Chrome", "chrome", CHROME, "chrome.exe") + _navegador("Edge", "edge", EDGE, "msedge.exe")


def publico():
    """Lista dos alvos sem as funções internas, pra mandar pra interface."""
    return [{k: a[k] for k in ("id", "grupo", "nome", "desc", "padrao")} for a in ALVOS]


def formatar(n):
    for unidade in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unidade}" if unidade == "B" else f"{n:.1f} {unidade}"
        n /= 1024
    return f"{n:.1f} TB"


def _por_id(ids):
    mapa = {a["id"]: a for a in ALVOS}
    return [mapa[i] for i in ids if i in mapa]


def _eh_link(caminho):
    return os.path.islink(caminho) or os.path.isjunction(caminho)


def _varrer(pasta):
    """Gera (caminho, tamanho) de cada arquivo, sem entrar em links/junções."""
    try:
        entradas = list(os.scandir(pasta))
    except OSError:
        return
    for e in entradas:
        try:
            if _eh_link(e.path):
                continue
            if e.is_dir(follow_symlinks=False):
                yield from _varrer(e.path)
            else:
                yield e.path, e.stat(follow_symlinks=False).st_size
        except OSError:
            pass


def _arquivos(alvo):
    for pasta in alvo.get("pastas", list)():
        if os.path.isdir(pasta) and not _eh_link(pasta):
            yield from _varrer(pasta)
    for caminho in alvo.get("arquivos", list)():
        try:
            if os.path.isfile(caminho) and not _eh_link(caminho):
                yield caminho, os.path.getsize(caminho)
        except OSError:
            pass


def _remover_pastas_vazias(pasta, raiz=True):
    """Apaga subpastas vazias, mantendo a pasta raiz."""
    try:
        entradas = list(os.scandir(pasta))
    except OSError:
        return
    for e in entradas:
        if not _eh_link(e.path) and e.is_dir(follow_symlinks=False):
            _remover_pastas_vazias(e.path, raiz=False)
    if not raiz:
        try:
            os.rmdir(pasta)
        except OSError:
            pass


def _apagar(alvo, ctl):
    liberado = falhas = 0
    for caminho, tamanho in list(_arquivos(alvo)):
        ctl.checar()
        try:
            os.remove(caminho)
        except FileNotFoundError:
            continue
        except PermissionError:
            try:
                os.chmod(caminho, stat.S_IWRITE)
                os.remove(caminho)
            except OSError:
                falhas += 1
                continue
        except OSError:
            falhas += 1
            continue
        liberado += tamanho
    for pasta in alvo.get("pastas", list)():
        if os.path.isdir(pasta) and not _eh_link(pasta):
            _remover_pastas_vazias(pasta)
    return liberado, falhas


# ---------- Lixeira ----------

class _InfoLixeira(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint32),
                ("i64Size", ctypes.c_int64),
                ("i64NumItems", ctypes.c_int64)]


def lixeira_info():
    info = _InfoLixeira()
    info.cbSize = ctypes.sizeof(info)
    if ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info)) != 0:
        return 0, 0
    return info.i64Size, info.i64NumItems


def esvaziar_lixeira():
    # sem confirmação, sem barra de progresso, sem som
    ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x7)
    return lixeira_info()[1] == 0


# ---------- Processos e serviços ----------

def processo_rodando(exe):
    saida = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {exe}", "/NH"],
                           capture_output=True, text=True, errors="replace",
                           creationflags=SEM_JANELA, timeout=30).stdout
    return exe.lower() in saida.lower()


def fechar(exe):
    if exe not in NAVEGADORES:
        return {"ok": False, "erro": "Processo não permitido"}
    subprocess.run(["taskkill", "/IM", exe, "/F", "/T"], capture_output=True, creationflags=SEM_JANELA, timeout=30)
    return {"ok": not processo_rodando(exe)}


# ---------- Análise e limpeza ----------

def analisar(ids):
    abertos = {}
    resultado = []
    for alvo in _por_id(ids):
        if alvo.get("especial") == "lixeira":
            tamanho, qtd = lixeira_info()
        else:
            tamanho = qtd = 0
            for _, t in _arquivos(alvo):
                tamanho += t
                qtd += 1
        exe = alvo.get("processo")
        if exe and exe not in abertos:
            abertos[exe] = processo_rodando(exe)
        resultado.append(dict(id=alvo["id"], bytes=tamanho, arquivos=qtd,
                              aberto=exe if exe and abertos[exe] else None))
    return resultado


def limpar(ids, linha, progresso, ctl):
    alvos = _por_id(ids)
    abertos = {}
    total = 0
    resumo = []
    for i, alvo in enumerate(alvos):
        ctl.checar()
        progresso(i / len(alvos) * 100)
        rotulo = f"{alvo['grupo']} › {alvo['nome']}"
        exe = alvo.get("processo")
        if exe:
            if exe not in abertos:
                abertos[exe] = processo_rodando(exe)
            if abertos[exe]:
                linha(f"{rotulo}: pulado, feche o {alvo['grupo']} primeiro.")
                resumo.append(dict(id=alvo["id"], bytes=0, falhas=0, pulado=True))
                continue

        linha(f"Limpando {rotulo}...")
        if alvo.get("especial") == "lixeira":
            tamanho, _ = lixeira_info()
            ok = esvaziar_lixeira()
            liberado, falhas = (tamanho, 0) if ok else (0, 1)
        else:
            liberado, falhas = _apagar(alvo, ctl)

        total += liberado
        extra = f" ({falhas} arquivo(s) em uso ficaram)" if falhas else ""
        linha(f"  {formatar(liberado)} liberados{extra}")
        resumo.append(dict(id=alvo["id"], bytes=liberado, falhas=falhas, pulado=False))
    progresso(100)
    return total, resumo
