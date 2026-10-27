"""Guarda quando foi a última limpeza, checagem etc. (usado na nota de saúde) e o log."""
import datetime
import json
import os
import time

PASTA = os.path.join(os.environ.get("LOCALAPPDATA", ""), "PC Estribado")
ARQ_ESTADO = os.path.join(PASTA, "estado.json")
ARQ_LOG = os.path.join(PASTA, "log.txt")


def ler():
    try:
        with open(ARQ_ESTADO, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def marcar(chave, valor=None):
    dados = ler()
    dados[chave] = time.time() if valor is None else valor
    os.makedirs(PASTA, exist_ok=True)
    with open(ARQ_ESTADO, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)


def limpar_log():
    if os.path.exists(ARQ_LOG):
        os.remove(ARQ_LOG)
    log("Log limpo.")


def log(texto):
    os.makedirs(PASTA, exist_ok=True)
    with open(ARQ_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.datetime.now():%d/%m/%Y %H:%M:%S}] {texto}\n")
