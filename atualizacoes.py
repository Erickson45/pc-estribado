"""Atualizações: programas via winget, Windows Update e drivers via a API do próprio Windows."""
import re
import subprocess

from sistema import SEM_JANELA, executar, powershell, powershell_json

_ID_WINGET = re.compile(r"^[\w.\-+]+$")
_GUID = re.compile(r"^[0-9a-fA-F-]{36}$")
_WINGET_FLAGS = ["--accept-source-agreements", "--disable-interactivity"]


# ---------- winget ----------

def _tabela_winget(texto):
    """Lê a tabela que o 'winget upgrade' imprime (Nome, ID, Versão, Disponível, Origem)."""
    # o spinner do winget reescreve a linha com \r; fica só o último pedaço
    linhas = [l.rstrip("\r").split("\r")[-1].rstrip() for l in texto.split("\n")]
    try:
        sep = next(i for i, l in enumerate(linhas) if l.startswith("---"))
    except StopIteration:
        return []
    colunas = [m.start() for m in re.finditer(r"\S+", linhas[sep - 1])]
    if len(colunas) < 4:
        return []
    itens = []
    for l in linhas[sep + 1:]:
        if not l.strip() or len(l) < colunas[3]:
            break
        campos = [l[a:b].strip() for a, b in zip(colunas, colunas[1:] + [None])]
        if not campos[1] or " " in campos[1]:
            break
        itens.append(dict(nome=campos[0], id=campos[1], versao=campos[2], disponivel=campos[3]))
    return itens


def winget_listar():
    proc = subprocess.run(["winget", "upgrade", *_WINGET_FLAGS], capture_output=True,
                          creationflags=SEM_JANELA, timeout=300)
    return _tabela_winget(proc.stdout.decode("utf-8", "replace"))


def winget_atualizar(pacote, linha, progresso, ctl):
    base = ["winget", "upgrade", "--silent", "--accept-package-agreements", *_WINGET_FLAGS]
    if pacote:
        if not _ID_WINGET.match(pacote):
            raise ValueError("ID de pacote inválido")
        cmd = base + ["--id", pacote, "--exact"]
    else:
        cmd = base + ["--all"]
    return executar(cmd, linha, progresso, codificacao="utf-8", ctl=ctl)


# ---------- Windows Update (sistema e drivers) ----------

# ServerSelection 2 = direto no Windows Update, o que inclui os drivers "opcionais"
_BUSCAR = r"""
$s = New-Object -ComObject Microsoft.Update.Session
$q = $s.CreateUpdateSearcher(); $q.ServerSelection = 2
$r = $q.Search("IsInstalled=0 and IsHidden=0 and Type='__TIPO__'")
$l = @(foreach ($u in $r.Updates) {
  $item = [ordered]@{ id = $u.Identity.UpdateID; titulo = $u.Title; tamanho = [int64]$u.MaxDownloadSize; driver = ($u.Type -eq 2) }
  if ($u.Type -eq 2) {
    try { $item.classe = $u.DriverClass; $item.fabricante = $u.DriverManufacturer; $item.data = $u.DriverVerDate.ToString('dd/MM/yyyy'); $item.hwid = $u.DriverHardwareID } catch {}
  }
  [pscustomobject]$item
})
ConvertTo-Json -InputObject $l -Compress
"""

_INSTALAR = r"""
$ids = '__IDS__'.Split(',')
$nomes = @{2='OK'; 3='OK com avisos'; 4='FALHOU'; 5='Cancelado'}
$s = New-Object -ComObject Microsoft.Update.Session
"Procurando as atualizações escolhidas..."
$q = $s.CreateUpdateSearcher(); $q.ServerSelection = 2
$r = $q.Search("IsInstalled=0 and IsHidden=0")
$col = New-Object -ComObject Microsoft.Update.UpdateColl
foreach ($u in $r.Updates) {
  if ($ids -contains $u.Identity.UpdateID) {
    if (-not $u.EulaAccepted) { $u.AcceptEula() }
    [void]$col.Add($u)
  }
}
if ($col.Count -eq 0) { "Nenhuma atualização pendente encontrada."; exit 0 }
"Baixando $($col.Count) atualização(ões)... 10%"
$d = $s.CreateUpdateDownloader(); $d.Updates = $col; [void]$d.Download()
"Instalando... 50%"
$i = $s.CreateUpdateInstaller(); $i.Updates = $col; $res = $i.Install()
for ($k = 0; $k -lt $col.Count; $k++) {
  $c = $res.GetUpdateResult($k).ResultCode
  "[$($nomes[$c])] $($col.Item($k).Title)"
}
"Concluído. 100%"
if ($res.RebootRequired) { "REINICIE o PC para terminar de aplicar as atualizações." }
"""

_HISTORICO = r"""
$q = (New-Object -ComObject Microsoft.Update.Session).CreateUpdateSearcher()
$n = $q.GetTotalHistoryCount()
$l = @()
if ($n -gt 0) {
  $l = @(foreach ($e in $q.QueryHistory(0, [Math]::Min(25, $n))) {
    if ($e.Title) { [pscustomobject]@{ titulo = $e.Title; data = $e.Date.ToLocalTime().ToString('dd/MM/yyyy HH:mm'); resultado = $e.ResultCode } }
  })
}
ConvertTo-Json -InputObject $l -Compress
"""


def wu_buscar(drivers=False):
    return [u for u in powershell_json(_BUSCAR.replace("__TIPO__", "Driver" if drivers else "Software"), timeout=900) if u]


def wu_historico():
    return [h for h in powershell_json(_HISTORICO, timeout=120) if h]


def wu_instalar_tudo(drivers, linha, progresso, ctl):
    linha("Procurando " + ("drivers novos..." if drivers else "atualizações do Windows..."))
    itens = wu_buscar(drivers)
    if not itens:
        linha("Nada pendente.")
        return 0
    return wu_instalar([u["id"] for u in itens], linha, progresso, ctl)


def wu_instalar(ids, linha, progresso, ctl):
    ids = [i for i in ids if _GUID.match(i)]
    if not ids:
        linha("Nada selecionado.")
        return 0
    return executar(powershell(_INSTALAR.replace("__IDS__", ",".join(ids))), linha, progresso,
                    codificacao="utf-8", ctl=ctl)


# ---------- Drivers instalados ----------

_PROBLEMAS = r"""
$l = @(Get-CimInstance Win32_PnPEntity | Where-Object { $_.ConfigManagerErrorCode -notin 0, 45 -and $_.Name } | ForEach-Object {
  [pscustomobject]@{ nome = $_.Name; codigo = [int]$_.ConfigManagerErrorCode; classe = "$($_.PNPClass)" } })
ConvertTo-Json -InputObject $l -Compress
"""

_PRINCIPAIS = r"""
$f = "DeviceClass='DISPLAY' OR DeviceClass='NET' OR DeviceClass='MEDIA' OR DeviceClass='BLUETOOTH' OR DeviceClass='HDC' OR DeviceClass='SCSIADAPTER'"
$l = @(Get-CimInstance Win32_PnPSignedDriver -Filter $f | Where-Object { $_.DeviceName -and $_.DriverProviderName -ne 'Microsoft' } | ForEach-Object {
  [pscustomobject]@{ nome = $_.DeviceName; classe = $_.DeviceClass; versao = $_.DriverVersion; fabricante = $_.DriverProviderName; hwid = $_.HardWareID
                     data = if ($_.DriverDate) { $_.DriverDate.ToString('yyyy-MM-dd') } else { $null } } })
ConvertTo-Json -InputObject $l -Compress
"""

PROBLEMAS = {
    1: "não está configurado direito", 3: "driver corrompido ou sem memória", 10: "não consegue iniciar",
    12: "conflito de recursos", 14: "precisa reiniciar o PC", 18: "precisa reinstalar o driver",
    19: "registro com problema", 21: "sendo removido", 22: "desativado", 24: "não encontrado ou sem driver",
    28: "sem driver instalado", 31: "não está funcionando direito", 37: "driver não iniciou",
    39: "driver corrompido ou ausente", 43: "o Windows parou o dispositivo porque ele deu erro",
    52: "assinatura do driver inválida",
}


def dispositivos_problema():
    itens = [d for d in powershell_json(_PROBLEMAS, timeout=60) if d]
    for d in itens:
        d["problema"] = PROBLEMAS.get(d["codigo"], f"erro código {d['codigo']}")
    return itens


def drivers_principais():
    vistos = set()
    itens = []
    for d in powershell_json(_PRINCIPAIS, timeout=90):
        if d and (d["nome"], d["versao"]) not in vistos:
            vistos.add((d["nome"], d["versao"]))
            itens.append(d)
    ordem = {"DISPLAY": 0, "NET": 1, "MEDIA": 2, "BLUETOOTH": 3}
    return sorted(itens, key=lambda d: (ordem.get(d["classe"], 9), d["nome"]))
