# CRUD-Python-do-Zero---projeto---PDU
# Controle de Estoque

Aplicativo desktop **offline** de controle de estoque em Python (PyQt5 + SQLite),
empacotado como `.exe` e instalável no Windows.

---

## Arquivos

| Arquivo | Para que serve |
|---|---|
| `main.py` | Interface gráfica (janela, tabelas, diálogos) |
| `database.py` | Banco SQLite: CRUD, movimentações, validações |
| `requirements.txt` | Dependências (só PyQt5) |
| `build.bat` | Gera o `ControleEstoque.exe` |
| `instalador.iss` | Gera o instalador `ControleEstoque-Setup.exe` |

Coloque todos na **mesma pasta**, ex.: `C:\projetos\estoque\`.

---

## Passo 1 — Instalar o Python (uma vez só)

1. Baixe o Python 3.10 ou superior em <https://www.python.org/downloads/windows/>
2. Na primeira tela do instalador, **marque "Add python.exe to PATH"**
3. Conclua a instalação e confirme abrindo o Prompt de Comando:
   ```
   python --version
   ```

## Passo 2 — Rodar em modo desenvolvimento

Dentro da pasta do projeto, no Prompt de Comando:

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

A janela deve abrir. Cadastre um produto para testar.

## Passo 3 — Gerar o executável

Ainda na pasta do projeto, dê **duplo clique em `build.bat`** (ou rode `build.bat` no
Prompt). Ele cria o ambiente, instala o PyInstaller e empacota tudo.

Resultado: **`dist\ControleEstoque.exe`** — arquivo único, roda sem Python instalado.

> Quer um ícone próprio? Coloque um arquivo `icone.ico` na pasta antes de rodar o
> `build.bat`; ele é detectado automaticamente.

> Antivírus reclamando? É falso positivo comum com PyInstaller `--onefile`.
> Assinar digitalmente o `.exe` resolve em ambiente corporativo.

## Passo 4 — Gerar o instalador

1. Baixe e instale o **Inno Setup**: <https://jrsoftware.org/isdl.php>
2. Abra `instalador.iss` no Inno Setup Compiler
3. Menu **Build → Compile** (ou `Ctrl+F9`)

Resultado: **`Output\ControleEstoque-Setup.exe`**. É esse arquivo que você distribui:
ele instala em `Arquivos de Programas`, cria atalho no Menu Iniciar e na Área de
Trabalho, e registra a desinstalação no Painel de Controle.

## Passo 5 — Instalar na máquina do usuário

Copie o `ControleEstoque-Setup.exe` para o computador destino e execute
(pede permissão de administrador). Depois é só abrir pelo atalho.

---

## Onde ficam os dados

```
%APPDATA%\ControleEstoque\estoque.db
```

Fica na pasta do usuário — e não em `Arquivos de Programas` — porque esta última é
somente leitura para programas comuns no Windows. Isso também significa que
**reinstalar ou atualizar o app não apaga o estoque**.

Para fazer backup: menu **Arquivo → Backup do banco…** (usa a API de backup do SQLite,
segura mesmo com o app aberto). Ou copie o `.db` direto.

---

## O que o app faz

- **CRUD de produtos**: código único, nome, categoria, unidade, preço de custo e venda, local, observação
- **Movimentações**: entrada, saída e ajuste de inventário, cada uma gravada com saldo resultante, data e observação
- **Bloqueio de saldo negativo**: saída maior que o estoque é recusada com aviso
- **Alerta de estoque mínimo**: linha amarela quando está no limite, vermelha quando zerado, aviso após a movimentação, e filtro "Somente abaixo do mínimo"
- **Busca** por código, nome, categoria ou local; ordenação clicando no cabeçalho
- **Exportar CSV** (`Ctrl+E`) da aba ativa, com `;` e BOM — abre direto no Excel em português
- **Resumo** no rodapé: total de itens, valor em estoque a preço de custo, quantidade abaixo do mínimo

Atalhos: `Ctrl+N` novo produto · `Ctrl+F` buscar · `Ctrl+E` exportar · `F5` atualizar · `Ctrl+Q` sair

---

## Ideias para a próxima versão

- Leitor de código de barras (funciona sem código: o leitor USB "digita" o código — basta o foco estar no campo de busca)
- Impressão de etiquetas
- Usuários e senha, se mais de uma pessoa mexer no estoque
- Relatório de curva ABC / giro por período