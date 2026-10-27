"""Manutenção automática semanal via Agendador de Tarefas do Windows.
A tarefa abre o programa com --auto, que roda sem janela e fecha sozinho."""
import os
import re
import sys

import estado
import limpeza
import sistema

TAREFA = "PC Estribado - Manutencao semanal"
DIAS = {"segunda": "Monday", "terca": "Tuesday", "quarta": "Wednesday", "quinta": "Thursday",
        "sexta": "Friday", "sabado": "Saturday", "domingo": "Sunday"}


def _ps_texto(s):
    return "'" + s.replace("'", "''") + "'"


def _comando():
    """Executável e argumentos que a tarefa agendada vai chamar."""
    if getattr(sys, "frozen", False):
        return sys.executable, "--auto"
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
    return (pythonw if os.path.exists(pythonw) else sys.executable), f'"{script}" --auto'


_STATUS = r"""
$t = Get-ScheduledTask -TaskName __NOME__ -ErrorAction SilentlyContinue
if (-not $t) { '{"existe":false}'; exit }
$i = $t | Get-ScheduledTaskInfo
function D($d) { if ($d -and $d.Year -gt 2000) { $d.ToString('dd/MM/yyyy HH:mm') } else { $null } }
[pscustomobject]@{ existe = $true; ativo = ($t.State -ne 'Disabled'); proxima = (D $i.NextRunTime); ultima = (D $i.LastRunTime); resultado = $i.LastTaskResult; exe = $t.Actions[0].Execute } | ConvertTo-Json -Compress
"""


def status():
    s = sistema.powershell_json(_STATUS.replace("__NOME__", _ps_texto(TAREFA)), timeout=60)
    config = estado.ler().get("auto", {})
    return dict(ativo=bool(s.get("existe") and s.get("ativo")), proxima=s.get("proxima"), ultima=s.get("ultima"),
                dia=config.get("dia", "sexta"), hora=config.get("hora", "12:00"), exe=s.get("exe"))


def corrigir_caminho():
    """Se o programa mudou de lugar (ex.: saiu dos Downloads e foi instalado), reaponta a tarefa."""
    s = status()
    if s["ativo"] and s["exe"] and os.path.normcase(s["exe"]) != os.path.normcase(_comando()[0]):
        estado.log(f"Manutenção automática apontava pra {s['exe']}; corrigindo pro programa atual.")
        ativar(s["dia"], s["hora"])


def ativar(dia, hora):
    if dia not in DIAS or not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", hora):
        raise ValueError("Dia ou horário inválido")
    exe, args = _comando()
    script = f"""
$a = New-ScheduledTaskAction -Execute {_ps_texto(exe)} -Argument {_ps_texto(args)}
$g = New-ScheduledTaskTrigger -Weekly -DaysOfWeek {DIAS[dia]} -At {_ps_texto(hora)}
$p = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\\$env:USERNAME" -LogonType Interactive -RunLevel Highest
$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName {_ps_texto(TAREFA)} -Action $a -Trigger $g -Principal $p -Settings $s -Force -ErrorAction Stop | Out-Null
'{{"ok":true}}'
"""
    sistema.powershell_json(script, timeout=60)
    estado.marcar("auto", dict(dia=dia, hora=hora))
    return status()


def desativar():
    sistema.powershell_json(f"Unregister-ScheduledTask -TaskName {_ps_texto(TAREFA)} -Confirm:$false -ErrorAction SilentlyContinue\n"
                            "'{\"ok\":true}'", timeout=60)
    return status()


def rodar():
    """O que a manutenção automática faz (sem janela): limpeza padrão, antivírus e DNS."""
    estado.log("===== Manutenção automática =====")
    ctl = sistema.Controle("Manutenção automática")
    padroes = [a["id"] for a in limpeza.ALVOS if a["padrao"]]
    total, _ = limpeza.limpar(padroes, estado.log, lambda _: None, ctl)
    estado.log(f"Limpeza automática: {limpeza.formatar(total)} liberados.")
    estado.marcar("ultima_limpeza")
    for acao in ("defender_atualizar", "dns"):
        try:
            sistema.rodar_acao(acao, estado.log, lambda _: None, ctl)
        except Exception as e:
            estado.log(f"Erro em {acao}: {e}")
    estado.marcar("ultima_auto")
    estado.log("Manutenção automática concluída.")
