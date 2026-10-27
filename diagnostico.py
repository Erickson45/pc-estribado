"""Lê o log, reconhece problemas conhecidos e aponta o reparo de cada um.
Um problema some da lista quando o reparo dele roda com sucesso depois da última ocorrência."""
import datetime
import os
import re

import estado

_DATA = re.compile(r"^\[(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})\] (.*)$")

# id: (padrão no log, título, explicação, ação que resolve, texto do botão)
REGRAS = {
    "sem_admin": (r"requer elevação|requires elevation|access is denied",
                  "Faltou permissão de administrador",
                  "Alguma ferramenta precisou de admin e o programa estava aberto sem. Reabrir como administrador resolve.",
                  "reabrir_admin", "Reabrir como admin"),
    "protecao": (r"Proteção do Sistema pode estar desativada",
                 "Ponto de restauração desligado",
                 "A Proteção do Sistema está desligada, então o Windows não consegue criar pontos de restauração.",
                 "ativar_protecao", "Ligar proteção"),
    "sfc_falhou": (r"não conseguiu corrigir|não foi possível corrigir|unable to fix|mas não (pôde|conseguiu)",
                   "SFC achou arquivos que não conseguiu reparar",
                   "O jeito certo é rodar o DISM (que baixa arquivos bons da Microsoft) e depois o SFC de novo.",
                   "dism_sfc", "Rodar DISM + SFC"),
    "disco": (r"ERROS NO DISCO|Windows (encontrou|found) (problemas|problems)|errors found",
              "Erros no sistema de arquivos do disco",
              "A verificação achou erros no disco. O reparo corrige (às vezes precisa reiniciar).",
              "reparar_disco", "Reparar disco"),
    "windows_update": (r"\[FALHOU\]|0x8024[0-9a-f]{4}|0x800f0[0-9a-f]{3}",
                       "Windows Update com erro",
                       "Alguma atualização falhou. Reiniciar o Windows Update do zero costuma resolver.",
                       "reparar_wu", "Reparar Windows Update"),
    "virus": (r"found [1-9]\d* threats?|[1-9]\d* ameaça",
              "O antivírus encontrou ameaças",
              "Vale rodar uma verificação completa pra garantir que tudo foi removido.",
              "defender_completa", "Verificação completa"),
}

# quais regras cada ação resolve quando termina bem
RESOLVE = {"ativar_protecao": ["protecao"], "dism_sfc": ["sfc_falhou"], "sfc": ["sfc_falhou"],
           "reparar_disco": ["disco"], "reparar_wu": ["windows_update"], "defender_completa": ["virus"]}


def ler_log(maximo=600):
    if not os.path.exists(estado.ARQ_LOG):
        return []
    with open(estado.ARQ_LOG, encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()[-maximo:]


def problemas(eh_admin):
    resolvidos = estado.ler().get("resolvidos", {})
    achados = {}
    for linha in ler_log(4000):
        m = _DATA.match(linha)
        if not m:
            continue
        quando = datetime.datetime.strptime(m.group(1), "%d/%m/%Y %H:%M:%S").timestamp()
        for rid, (padrao, *_resto) in REGRAS.items():
            if re.search(padrao, m.group(2), re.IGNORECASE):
                achados[rid] = (quando, m.group(2))
    lista = []
    for rid, (quando, exemplo) in achados.items():
        if quando <= resolvidos.get(rid, 0) or (rid == "sem_admin" and eh_admin):
            continue
        _, titulo, explicacao, acao, botao = REGRAS[rid]
        lista.append(dict(id=rid, titulo=titulo, explicacao=explicacao, acao=acao, botao=botao,
                          exemplo=exemplo, quando=datetime.datetime.fromtimestamp(quando).strftime("%d/%m %H:%M")))
    return lista


def marcar_resolvido(acao):
    regras = RESOLVE.get(acao)
    if regras:
        resolvidos = estado.ler().get("resolvidos", {})
        agora = datetime.datetime.now().timestamp()
        resolvidos.update({r: agora for r in regras})
        estado.marcar("resolvidos", resolvidos)
