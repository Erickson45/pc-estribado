"""Atualização automática do próprio programa: confere a última versão no GitHub Releases,
baixa o instalador, confere o hash SHA-256 e roda o instalador em modo silencioso."""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

import estado

# >>> Preencha com "seu-usuario/nome-do-repositorio" do GitHub antes de publicar <<<
REPOSITORIO = "Erickson45/pc-estribado"

# Só pra testes rodando pelo Python: aponta pra um servidor local no lugar do GitHub
_TESTE = os.environ.get("PC_ESTRIBADO_URL_ATUALIZACAO") if not getattr(sys, "frozen", False) else None
URL = _TESTE or (f"https://api.github.com/repos/{REPOSITORIO}/releases/latest" if REPOSITORIO else "")
PASTA = os.path.join(tempfile.gettempdir(), "PC Estribado - atualizacao")
INTERVALO = 12 * 3600  # verificação automática no máximo a cada 12h


def _versao(texto):
    return tuple(int(n) for n in re.findall(r"\d+", texto or "")[:3])


def _origem_confiavel(url):
    if _TESTE:
        return True
    partes = urllib.parse.urlparse(url)
    return partes.scheme == "https" and (partes.hostname or "").endswith("github.com")


def _baixar_json(url):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "PC-Estribado"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def verificar(versao_atual, so_se_vencido=False):
    """Pergunta ao GitHub qual a última versão. Com so_se_vencido, respeita o intervalo de 12h."""
    dados = estado.ler()
    if not URL:
        return dict(configurado=False)
    if so_se_vencido:
        if not dados.get("atualizacao_auto", True):
            return dict(configurado=True, pulado=True)
        if time.time() - dados.get("ultima_verificacao_att", 0) < INTERVALO:
            ultima = dados.get("ultima_att_encontrada")
            if isinstance(ultima, dict) and _versao(ultima["versao"]) > _versao(versao_atual):
                return ultima  # já sabíamos de uma versão nova
            return dict(configurado=True, pulado=True)

    rel = _baixar_json(URL)
    instalador = next((a for a in rel.get("assets", []) if a["name"].lower().endswith(".exe")), None)
    if not instalador:
        raise RuntimeError("A última versão publicada não tem o instalador (.exe) anexado.")
    # o GitHub calcula o hash de cada arquivo anexado ("digest"); na falta dele, aceita um .sha256 publicado junto
    sha = (instalador.get("digest") or "").removeprefix("sha256:")
    if not sha:
        anexo = next((a for a in rel.get("assets", []) if a["name"].lower().endswith(".sha256")), None)
        if anexo:
            with urllib.request.urlopen(anexo["browser_download_url"], timeout=15) as r:
                sha = r.read().decode().split()[0]
    info = dict(configurado=True, versao=rel["tag_name"].lstrip("vV"), notas=rel.get("body") or "",
                url=instalador["browser_download_url"], tamanho=instalador.get("size", 0),
                sha256=sha.lower(), pagina=rel.get("html_url", ""), publicado=(rel.get("published_at") or "")[:10])
    info["nova"] = _versao(info["versao"]) > _versao(versao_atual)
    estado.marcar("ultima_verificacao_att")
    estado.marcar("ultima_att_encontrada", info if info["nova"] else False)  # None viraria "agora" no marcar()
    return info


def baixar(info, linha, progresso, ctl):
    """Baixa o instalador e confere o hash. Devolve o caminho do arquivo."""
    if not _origem_confiavel(info["url"]):
        raise RuntimeError("Endereço de download fora do GitHub. Por segurança, não vou baixar.")
    if not re.fullmatch(r"[0-9a-f]{64}", info.get("sha256") or ""):
        raise RuntimeError("Essa versão foi publicada sem o hash SHA-256. Por segurança, não vou instalar.")
    os.makedirs(PASTA, exist_ok=True)
    destino = os.path.join(PASTA, f"PC Estribado {info['versao']} - Instalador.exe")
    linha(f"Baixando a versão {info['versao']}...")
    req = urllib.request.Request(info["url"], headers={"User-Agent": "PC-Estribado"})
    soma = hashlib.sha256()
    baixado = 0
    with urllib.request.urlopen(req, timeout=30) as r, open(destino, "wb") as f:
        total = int(r.headers.get("Content-Length") or info.get("tamanho") or 0)
        while bloco := r.read(256 * 1024):
            ctl.checar()
            f.write(bloco)
            soma.update(bloco)
            baixado += len(bloco)
            if total:
                progresso(baixado / total * 100)
    linha(f"Baixado: {baixado / 1048576:.1f} MB. Conferindo se o arquivo é o original...")
    if soma.hexdigest() != info["sha256"]:
        os.remove(destino)
        raise RuntimeError("O arquivo baixado não bate com o publicado (hash diferente). Apaguei ele e não vou instalar.")
    linha("✔ Arquivo conferido: é o original.")
    return destino


def instalar(caminho):
    """Abre o instalador em modo silencioso; ele fecha o programa, atualiza e abre de novo."""
    subprocess.Popen([caminho, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
                     creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP, close_fds=True)
