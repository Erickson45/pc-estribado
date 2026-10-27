"""Informações do PC: hardware (lido uma vez) e uso em tempo real (CPU, RAM, discos, processos)."""
import threading
import time

import psutil

from sistema import powershell_json

_HARDWARE = r"""
function Data($d) { if ($d) { $d.ToString('dd/MM/yyyy') } else { $null } }
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$placa = Get-CimInstance Win32_BaseBoard | Select-Object -First 1
$bios = Get-CimInstance Win32_BIOS | Select-Object -First 1
$so = Get-CimInstance Win32_OperatingSystem
$gpus = @(Get-CimInstance Win32_VideoController | ForEach-Object {
  [pscustomobject]@{ nome = $_.Name; driver = $_.DriverVersion; data = (Data $_.DriverDate); vram = [int64]$_.AdapterRAM } })
$ram = @(Get-CimInstance Win32_PhysicalMemory | ForEach-Object {
  [pscustomobject]@{ tamanho = [int64]$_.Capacity; velocidade = $_.ConfiguredClockSpeed; fabricante = "$($_.Manufacturer)".Trim() } })
$discos = @(Get-PhysicalDisk | ForEach-Object {
  [pscustomobject]@{ nome = $_.FriendlyName; tipo = "$($_.MediaType)"; saude = "$($_.HealthStatus)"; tamanho = [int64]$_.Size; barramento = "$($_.BusType)" } })
[pscustomobject]@{
  cpu = [pscustomobject]@{ nome = "$($cpu.Name)".Trim(); nucleos = $cpu.NumberOfCores; threads = $cpu.NumberOfLogicalProcessors; mhz = $cpu.MaxClockSpeed }
  placa = "$($placa.Manufacturer) $($placa.Product)".Trim()
  bios = "$($bios.SMBIOSBIOSVersion)"
  instalado = (Data $so.InstallDate)
  gpus = $gpus; ram = $ram; discos = $discos
} | ConvertTo-Json -Depth 4 -Compress
"""

_cache = None

# O psutil guarda a medição da CPU por thread, e cada chamada da interface vem numa thread nova
# (aí toda leitura seria "a primeira" e daria 0%). Uma thread fixa mede de segundo em segundo.
_cpu = {"pct": 0.0}


def _medir_cpu():
    while True:
        _cpu["pct"] = psutil.cpu_percent(interval=1)


threading.Thread(target=_medir_cpu, daemon=True, name="medidor-cpu").start()


def info():
    """Hardware do PC. Demora uns segundos na primeira vez, depois fica em cache."""
    global _cache
    if _cache is None:
        _cache = powershell_json(_HARDWARE, timeout=90)
    return _cache


def discos():
    lista = []
    for parte in psutil.disk_partitions():
        if "cdrom" in parte.opts or not parte.fstype:
            continue
        try:
            uso = psutil.disk_usage(parte.mountpoint)
        except OSError:
            continue
        lista.append(dict(letra=parte.mountpoint.rstrip("\\"), total=uso.total, livre=uso.free))
    return lista


def metricas():
    """Uso atual: chamado a cada 2 segundos pela tela de início.
    Só ela deve ler a CPU, senão uma leitura zera a medição da outra."""
    mem = psutil.virtual_memory()
    freq = psutil.cpu_freq()

    # soma por nome, senão o Chrome aparece 30 vezes
    por_nome = {}
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            nome = p.info["name"] or "?"
            por_nome[nome] = por_nome.get(nome, 0) + p.info["memory_info"].rss
        except (psutil.Error, AttributeError):
            continue
    pesados = sorted(por_nome.items(), key=lambda x: -x[1])[:6]

    bateria = psutil.sensors_battery()
    return dict(
        cpu=_cpu["pct"],
        cpu_mhz=round(freq.current) if freq else None,
        ram=dict(total=mem.total, usada=mem.total - mem.available, pct=mem.percent),
        discos=discos(),
        ligado_ha=int(time.time() - psutil.boot_time()),
        processos=[dict(nome=n.removesuffix(".exe"), memoria=m) for n, m in pesados],
        bateria=dict(pct=bateria.percent, carregando=bateria.power_plugged) if bateria else None,
    )
