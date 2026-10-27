# Como publicar uma versão do PC Estribado

A atualização automática procura a última versão no **GitHub Releases**. Quem tem o programa instalado recebe o aviso "Saiu a versão X!" e atualiza com um clique.

## Uma vez só: criar o repositório
1. Crie uma conta em https://github.com (grátis).
2. Clique em **New repository**, dê um nome (ex.: `pc-estribado`) e deixe **Public**.
3. Abra `atualizador.py` e preencha a linha:
   ```python
   REPOSITORIO = "seu-usuario/pc-estribado"
   ```

## A cada versão nova
1. Troque o número da versão em **dois lugares** (sempre maior que a anterior, ex.: `1.1.0`):
   - `app.py` → `VERSAO = "1.1.0"`
   - `instalador.iss` → `#define Versao "1.1.0"`
2. Dois cliques em `gerar_instalador.bat`.
3. No GitHub, abra o repositório → **Releases** → **Draft a new release**:
   - **Tag:** `v1.1.0` (o mesmo número, com "v" na frente)
   - **Título:** `PC Estribado 1.1.0`
   - **Descrição:** as novidades, uma por linha começando com `-`. Isso aparece pra pessoa dentro do programa.
   - Arraste o arquivo de `instalador\saida\PC Estribado 1.1.0 - Instalador.exe`.
4. Clique em **Publish release**.

Pronto. Em até 12 horas (ou na hora, em *Sobre → Verificar agora*), todo mundo que tem o programa vê o aviso.

## Segurança
- O programa só baixa de endereços `https://...github.com`.
- O GitHub calcula sozinho a "impressão digital" (SHA-256) de cada arquivo anexado. O programa confere essa impressão depois de baixar e **não instala** se ela não bater.
- Nunca publique um instalador que você não gerou com o `gerar_instalador.bat`.
