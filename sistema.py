"""Comandos do Windows (verificação, antivírus, discos, rede), cancelamento de tarefas
e ponto de restauração."""
import base64
import ctypes
import json
import os
import re
import subprocess
import threading
import winreg

SEM_JANELA = subprocess.CREATE_NO_WINDOW
WINDIR = os.environ.get("WINDIR", r"C:\Windows")
# Python 32 bits enxerga o SysWOW64 no lugar do System32; Sysnative contorna isso
SYSTEM32 = os.path.join(WINDIR, "Sysnative" if os.path.isdir(os.path.join(WINDIR, "Sysnative")) else "System32")
UNIDADE = os.environ.get("SystemDrive", "C:")
DEFENDER = os.path.join(os.environ.get("ProgramW6432", os.environ.get("ProgramFiles", r"C:\Program Files")),
                        "Windows Defender", "MpCmdRun.exe")

_OEM = f"cp{ctypes.windll.kernel32.GetOEMCP()}"
_PORCENTAGEM = re.compile(r"(\d{1,3}(?:[.,]\d+)?)\s*%")


def _s32(exe, *args):
    return [os.path.join(SYSTEM32, exe), *args]


# id: (nome, [comandos em sequência])
ACOES = {
    "dism": ("DISM (repara a imagem do Windows)", [_s32("Dism.exe", "/Online", "/Cleanup-Image", "/RestoreHealth")]),
    "sfc": ("SFC (verifica arquivos do sistema)", [_s32("sfc.exe", "/scannow")]),
    "chkdsk": (f"CHKDSK (checa o disco {UNIDADE})", [_s32("chkdsk.exe", UNIDADE, "/scan")]),
    "componentes": ("Limpeza profunda de componentes do Windows",
                    [_s32("Dism.exe", "/Online", "/Cleanup-Image", "/StartComponentCleanup")]),
    "otimizar": (f"Otimizar unidade {UNIDADE}", [_s32("defrag.exe", UNIDADE, "/O", "/U", "/V")]),
    "hardware": ("Procurar hardware novo", [_s32("pnputil.exe", "/scan-devices")]),
    "dns": ("Limpar cache de DNS",[_s32("ipconfig.exe", "/flushdns")]),
    "rede": ("Resetar configurações de rede", [_s32("netsh.exe", "winsock", "reset"),
                                               _s32("netsh.exe", "int", "ip", "reset")]),
    "defender_atualizar": ("Atualizar definições do antivírus", [[DEFENDER, "-SignatureUpdate"]]),
    "defender_rapida": ("Verificação rápida de vírus", [[DEFENDER, "-Scan", "-ScanType", "1"]]),
    "defender_completa": ("Verificação completa de vírus", [[DEFENDER, "-Scan", "-ScanType", "2"]]),
}


class Cancelado(Exception):
    pass


class Controle:
    """Acompanha a tarefa em andamento pra dar pra cancelar (inclusive matando o comando rodando)."""

    def __init__(self, titulo):
        self.titulo = titulo
        self.evento = threading.Event()
        self.proc = None

    @property
    def cancelado(self):
        return self.evento.is_set()

    def checar(self):
        if self.evento.is_set():
            raise Cancelado()

    def cancelar(self):
        self.evento.set()
        proc = self.proc
        if proc and proc.poll() is None:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True,
                           creationflags=SEM_JANELA, timeout=20)


def powershell(script):
    """Monta a chamada do PowerShell com o script codificado (evita dor de cabeça com aspas)."""
    script = "[Console]::OutputEncoding=[Text.Encoding]::UTF8\n$ProgressPreference='SilentlyContinue'\n" + script
    codificado = base64.b64encode(script.encode("utf-16-le")).decode()
    return _s32(r"WindowsPowerShell\v1.0\powershell.exe",
                "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", codificado)


def powershell_json(script, timeout=120):
    """Roda um script que imprime JSON e devolve o objeto."""
    proc = subprocess.run(powershell(script), capture_output=True, creationflags=SEM_JANELA, timeout=timeout)
    saida = proc.stdout.decode("utf-8", "replace").strip()
    inicio = min([i for i in (saida.find("{"), saida.find("[")) if i >= 0], default=-1)
    if inicio < 0:
        erro = proc.stderr.decode("utf-8", "replace").strip() or saida
        raise RuntimeError(erro or "O comando não devolveu nada")
    return json.loads(saida[inicio:])


_ACENTOS = set("áéíóúâêôãõçàÁÉÍÓÚÂÊÔÃÕÇÀ")


def _decodificar(bruto, codificacao):
    if codificacao:
        return bruto.decode(codificacao, "replace")
    if b"\x00" in bruto:  # o sfc escreve em UTF-16 quando a saída é redirecionada
        return bruto.replace(b"\x00", b"").decode("cp1252", "replace")
    # cada ferramenta do Windows usa uma página de código (OEM ou ANSI); fica a que formar mais acento de verdade
    opcoes = [bruto.decode(c, "replace") for c in (_OEM, "cp1252")]
    return max(opcoes, key=lambda t: sum(ch in _ACENTOS for ch in t))


def executar(cmd, linha, progresso=None, codificacao=None, ctl=None):
    """Roda um comando repassando a saída linha a linha. Devolve o código de saída."""
    if ctl:
        ctl.checar()
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, creationflags=SEM_JANELA)
    except OSError as e:
        linha(f"Não deu pra iniciar: {e}")
        return -1
    if ctl:
        ctl.proc = proc

    def emitir(bruto):
        texto = _decodificar(bruto, codificacao).strip()
        if not texto:
            return
        linha(texto)
        if progresso:
            achados = _PORCENTAGEM.findall(texto)
            if achados:
                progresso(min(100.0, float(achados[-1].replace(",", "."))))

    resto = b""
    while bloco := proc.stdout.read1(4096):
        resto += bloco
        partes = re.split(rb"[\r\n]", resto)
        resto = partes.pop()
        for parte in partes:
            emitir(parte)
    emitir(resto)
    codigo = proc.wait()
    if ctl:
        ctl.proc = None
        ctl.checar()
    return codigo


LETRA = UNIDADE.rstrip(":")

# Plano B do CHKDSK: em alguns PCs (anticheat, antivírus) o chkdsk.exe é bloqueado,
# mas o Repair-Volume faz a mesma verificação por outro caminho
_VERIFICAR_VOLUME = f"""
$r = Repair-Volume -DriveLetter {LETRA} -Scan -ErrorAction Stop
if ("$r" -eq 'NoErrorsFound') {{ 'Nenhum erro encontrado no disco.' }}
else {{ "ERROS NO DISCO: resultado $r. Use 'Reparar disco' pra corrigir." }}
"""

_REPARAR_VOLUME = f"""
$r = Repair-Volume -DriveLetter {LETRA} -SpotFix -ErrorAction Stop
"Resultado: $r"
'Se o Windows pedir, reinicie o PC pra terminar o reparo.'
"""

_ATIVAR_PROTECAO = f"""
Enable-ComputerRestore -Drive '{LETRA}:\\' -ErrorAction Stop
'Proteção do Sistema ligada no disco {LETRA}:.'
Checkpoint-Computer -Description 'PC Estribado' -RestorePointType MODIFY_SETTINGS -ErrorAction Stop
'Primeiro ponto de restauração criado.'
"""

# Reset clássico do Windows Update: para os serviços (com prazo), renomeia os caches e religa
_REPARAR_WU = r"""
$servicos = 'wuauserv', 'bits', 'cryptsvc'
foreach ($s in $servicos) {
  "Parando $s..."
  Stop-Service -Name $s -Force -NoWait -ErrorAction SilentlyContinue
  $fim = (Get-Date).AddSeconds(40)
  while ((Get-Service $s).Status -ne 'Stopped' -and (Get-Date) -lt $fim) { Start-Sleep -Milliseconds 500 }
  if ((Get-Service $s).Status -ne 'Stopped') { "  $s não parou a tempo, seguindo assim mesmo." }
}
$sufixo = Get-Date -Format 'yyyyMMddHHmmss'
foreach ($p in "$env:WINDIR\SoftwareDistribution", "$env:WINDIR\System32\catroot2") {
  try { Rename-Item $p "$(Split-Path $p -Leaf).antigo-$sufixo" -ErrorAction Stop; "Cache renomeado: $p" }
  catch { "Não deu pra renomear $p (em uso). Tente depois de reiniciar." }
}
foreach ($s in $servicos) { Start-Service -Name $s -ErrorAction SilentlyContinue; "Religado: $s" }
'Windows Update reiniciado do zero. Procure as atualizações de novo.'
"""

# reparos: (nome, script PowerShell)
REPAROS = {
    "reparar_disco": (f"Reparar disco {UNIDADE}", _REPARAR_VOLUME),
    "ativar_protecao": ("Ligar a Proteção do Sistema", _ATIVAR_PROTECAO),
    "reparar_wu": ("Reparar o Windows Update", _REPARAR_WU),
}


def rodar_acao(acao, linha, progresso, ctl):
    if acao in REPAROS:
        nome, script = REPAROS[acao]
        linha(f"▶ {nome}")
        codigo = executar(powershell(script), linha, progresso, codificacao="utf-8", ctl=ctl)
        linha(f"✔ {nome} terminou." if codigo == 0 else f"⚠ {nome} terminou com código {codigo}. Veja as mensagens acima.")
        return codigo
    nome, comandos = ACOES[acao]
    linha(f"▶ {nome}")
    progresso(0)
    codigo = 0
    for cmd in comandos:
        codigo = executar(cmd, linha, progresso, ctl=ctl)
    if acao == "chkdsk" and codigo == -1:
        linha("O Windows bloqueou o chkdsk.exe neste PC (costuma ser anticheat ou antivírus). Usando o Repair-Volume, que faz a mesma verificação...")
        codigo = executar(powershell(_VERIFICAR_VOLUME), linha, progresso, codificacao="utf-8", ctl=ctl)
    if codigo == 0:
        linha(f"✔ {nome} terminou.")
    else:
        linha(f"⚠ {nome} terminou com código {codigo}. Veja as mensagens acima.")
    return codigo


def ponto_restauracao(linha, ctl=None):
    script = ("Checkpoint-Computer -Description 'PC Estribado' -RestorePointType MODIFY_SETTINGS -ErrorAction Stop\n"
              "'Ponto de restauração criado (ou já existia um das últimas 24h).'")
    codigo = executar(powershell(script), linha, codificacao="utf-8", ctl=ctl)
    if codigo != 0:
        linha("Não deu pra criar. A Proteção do Sistema pode estar desativada no disco C:.")
    return codigo == 0


# ---------- Antivírus ----------

_DEFENDER_STATUS = r"""
$outros = @(Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct -ErrorAction SilentlyContinue |
  Where-Object { $_.displayName -notmatch 'Defender' } | ForEach-Object { $_.displayName })
$s = Get-MpComputerStatus -ErrorAction SilentlyContinue
$ameacas = @(Get-MpThreatDetection -ErrorAction SilentlyContinue).Count
[pscustomobject]@{
  disponivel = [bool]$s
  ativo = [bool]$s.AntivirusEnabled
  tempo_real = [bool]$s.RealTimeProtectionEnabled
  idade_definicoes = $s.AntivirusSignatureAge
  dias_ultima_verificacao = $s.QuickScanAge
  ameacas = $ameacas
  outros = $outros
} | ConvertTo-Json -Compress
"""


def defender_status():
    return powershell_json(_DEFENDER_STATUS, timeout=60)


# ---------- Discos ----------

_DISCOS = r"""
$l = @(Get-PhysicalDisk | ForEach-Object {
  $r = $_ | Get-StorageReliabilityCounter -ErrorAction SilentlyContinue
  [pscustomobject]@{
    nome = $_.FriendlyName; tipo = "$($_.MediaType)"; saude = "$($_.HealthStatus)"; tamanho = [int64]$_.Size
    temperatura = $r.Temperature; desgaste = $r.Wear; erros_leitura = $r.ReadErrorsTotal; horas_ligado = $r.PowerOnHours
  }
})
ConvertTo-Json -InputObject $l -Compress
"""


def discos_saude():
    return [d for d in powershell_json(_DISCOS, timeout=60) if d]


# ---------- Reinicialização ----------

def reinicio_pendente():
    chaves = [r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired",
              r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending"]
    for chave in chaves:
        try:
            winreg.CloseKey(winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, chave, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY))
            return True
        except OSError:
            pass
    return False


def reiniciar():
    subprocess.run(_s32("shutdown.exe", "/r", "/t", "15", "/c", "PC Estribado: reiniciando para concluir as atualizações."),
                   creationflags=SEM_JANELA, timeout=20)
