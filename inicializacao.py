"""Programas que abrem com o Windows. Ativa/desativa igual ao Gerenciador de Tarefas
(chaves StartupApproved), então nada é apagado e dá pra voltar atrás."""
import os
import struct
import time
import winreg

HKCU, HKLM = winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE
_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APROVADOS = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved"
_VISAO64 = winreg.KEY_WOW64_64KEY

FONTES = [
    dict(raiz=HKCU, chave=_RUN, aprov="Run", local="Registro (seu usuário)"),
    dict(raiz=HKLM, chave=_RUN, aprov="Run", local="Registro (todos os usuários)"),
    dict(raiz=HKLM, chave=r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run",
         aprov="Run32", local="Registro (todos, 32 bits)"),
    dict(raiz=HKCU, pasta=os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup"),
         aprov="StartupFolder", local="Pasta Inicializar (seu usuário)"),
    dict(raiz=HKLM, pasta=os.path.join(os.environ.get("PROGRAMDATA", ""), r"Microsoft\Windows\Start Menu\Programs\StartUp"),
         aprov="StartupFolder", local="Pasta Inicializar (todos)"),
]


def _valores(raiz, chave):
    try:
        k = winreg.OpenKey(raiz, chave, 0, winreg.KEY_READ | _VISAO64)
    except OSError:
        return {}
    valores = {}
    with k:
        i = 0
        while True:
            try:
                nome, valor, _ = winreg.EnumValue(k, i)
            except OSError:
                break
            valores[nome] = valor
            i += 1
    return valores


def _entradas(fonte):
    if "chave" in fonte:
        return {n: str(v) for n, v in _valores(fonte["raiz"], fonte["chave"]).items() if n}
    if not os.path.isdir(fonte["pasta"]):
        return {}
    return {n: os.path.join(fonte["pasta"], n) for n in os.listdir(fonte["pasta"])
            if n.lower() != "desktop.ini"}


def listar():
    itens = []
    for i, fonte in enumerate(FONTES):
        aprovados = _valores(fonte["raiz"], f"{_APROVADOS}\\{fonte['aprov']}")
        for nome, comando in _entradas(fonte).items():
            estado = aprovados.get(nome)
            # byte 0 ímpar (03, 07) = desativado; ausente ou par = ativo
            ativo = not (isinstance(estado, bytes) and estado and estado[0] & 1)
            itens.append(dict(id=f"{i}|{nome}", nome=os.path.splitext(nome)[0] if "pasta" in fonte else nome,
                              comando=comando, local=fonte["local"], ativo=ativo,
                              precisa_admin=fonte["raiz"] == HKLM))
    return sorted(itens, key=lambda x: x["nome"].lower())


def definir(item_id, ativo):
    indice, nome = item_id.split("|", 1)
    fonte = FONTES[int(indice)]
    if nome not in _entradas(fonte):
        raise ValueError("Item não encontrado")
    if ativo:
        dado = bytes([2] + [0] * 11)
    else:
        agora = int((time.time() + 11644473600) * 10_000_000)  # FILETIME
        dado = bytes([3, 0, 0, 0]) + struct.pack("<Q", agora)
    with winreg.CreateKeyEx(fonte["raiz"], f"{_APROVADOS}\\{fonte['aprov']}", 0,
                            winreg.KEY_SET_VALUE | _VISAO64) as k:
        winreg.SetValueEx(k, nome, 0, winreg.REG_BINARY, dado)
