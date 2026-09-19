"""Camada de dados do Controle de Estoque (SQLite, 100% offline)."""

import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

APP_NAME = "ControleEstoque"


class ErroEstoque(Exception):
    """Erro de regra de negócio (mensagem já pronta para o usuário)."""


def pasta_dados() -> Path:
    """Pasta gravável do usuário — funciona mesmo instalado em Program Files."""
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA") or Path.home())
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    destino = base / APP_NAME
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def caminho_banco() -> Path:
    return pasta_dados() / "estoque.db"


def agora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


ESQUEMA = """
CREATE TABLE IF NOT EXISTS produtos (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo         TEXT    NOT NULL UNIQUE,
    nome           TEXT    NOT NULL,
    categoria      TEXT    NOT NULL DEFAULT '',
    unidade        TEXT    NOT NULL DEFAULT 'un',
    quantidade     REAL    NOT NULL DEFAULT 0,
    estoque_minimo REAL    NOT NULL DEFAULT 0,
    preco_custo    REAL    NOT NULL DEFAULT 0,
    preco_venda    REAL    NOT NULL DEFAULT 0,
    localizacao    TEXT    NOT NULL DEFAULT '',
    observacao     TEXT    NOT NULL DEFAULT '',
    criado_em      TEXT    NOT NULL,
    atualizado_em  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS movimentacoes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    produto_id  INTEGER NOT NULL REFERENCES produtos(id) ON DELETE CASCADE,
    tipo        TEXT    NOT NULL CHECK (tipo IN ('entrada', 'saida', 'ajuste')),
    quantidade  REAL    NOT NULL,
    saldo_apos  REAL    NOT NULL,
    observacao  TEXT    NOT NULL DEFAULT '',
    data        TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_mov_produto ON movimentacoes(produto_id);
CREATE INDEX IF NOT EXISTS idx_mov_data    ON movimentacoes(data);
CREATE INDEX IF NOT EXISTS idx_prod_nome   ON produtos(nome);
"""


class Banco:
    """Acesso ao SQLite. Uma instância por aplicação."""

    def __init__(self, caminho: Path | str | None = None):
        self.caminho = Path(caminho) if caminho else caminho_banco()
        self.con = sqlite3.connect(str(self.caminho))
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = ON")
        self.con.execute("PRAGMA journal_mode = WAL")
        self.con.executescript(ESQUEMA)
        self.con.commit()

    def fechar(self) -> None:
        self.con.close()

    # ------------------------------------------------------------------ CRUD

    def listar_produtos(self, busca: str = "", somente_baixo: bool = False) -> list[sqlite3.Row]:
        sql = "SELECT * FROM produtos WHERE 1=1"
        params: list = []
        if busca.strip():
            termo = f"%{busca.strip()}%"
            sql += " AND (codigo LIKE ? OR nome LIKE ? OR categoria LIKE ? OR localizacao LIKE ?)"
            params += [termo, termo, termo, termo]
        if somente_baixo:
            sql += " AND quantidade <= estoque_minimo"
        sql += " ORDER BY nome COLLATE NOCASE"
        return self.con.execute(sql, params).fetchall()

    def obter_produto(self, produto_id: int) -> sqlite3.Row | None:
        return self.con.execute("SELECT * FROM produtos WHERE id = ?", (produto_id,)).fetchone()

    def criar_produto(self, dados: dict) -> int:
        self._validar(dados)
        ts = agora()
        try:
            cur = self.con.execute(
                """INSERT INTO produtos
                   (codigo, nome, categoria, unidade, quantidade, estoque_minimo,
                    preco_custo, preco_venda, localizacao, observacao, criado_em, atualizado_em)
                   VALUES (:codigo, :nome, :categoria, :unidade, :quantidade, :estoque_minimo,
                           :preco_custo, :preco_venda, :localizacao, :observacao, :criado, :atualizado)""",
                {**dados, "criado": ts, "atualizado": ts},
            )
        except sqlite3.IntegrityError as exc:
            raise ErroEstoque(f"Já existe um produto com o código '{dados['codigo']}'.") from exc

        produto_id = int(cur.lastrowid)
        if float(dados["quantidade"]) > 0:
            self.con.execute(
                """INSERT INTO movimentacoes (produto_id, tipo, quantidade, saldo_apos, observacao, data)
                   VALUES (?, 'entrada', ?, ?, 'Estoque inicial', ?)""",
                (produto_id, float(dados["quantidade"]), float(dados["quantidade"]), ts),
            )
        self.con.commit()
        return produto_id

    def atualizar_produto(self, produto_id: int, dados: dict) -> None:
        """Atualiza o cadastro. A quantidade NÃO é alterada aqui — use movimentações."""
        self._validar(dados, checar_quantidade=False)
        try:
            self.con.execute(
                """UPDATE produtos SET
                       codigo = :codigo, nome = :nome, categoria = :categoria,
                       unidade = :unidade, estoque_minimo = :estoque_minimo,
                       preco_custo = :preco_custo, preco_venda = :preco_venda,
                       localizacao = :localizacao, observacao = :observacao,
                       atualizado_em = :atualizado
                   WHERE id = :id""",
                {**dados, "id": produto_id, "atualizado": agora()},
            )
        except sqlite3.IntegrityError as exc:
            raise ErroEstoque(f"Já existe outro produto com o código '{dados['codigo']}'.") from exc
        self.con.commit()

    def excluir_produto(self, produto_id: int) -> None:
        self.con.execute("DELETE FROM produtos WHERE id = ?", (produto_id,))
        self.con.commit()

    @staticmethod
    def _validar(dados: dict, checar_quantidade: bool = True) -> None:
        if not str(dados.get("codigo", "")).strip():
            raise ErroEstoque("O código do produto é obrigatório.")
        if not str(dados.get("nome", "")).strip():
            raise ErroEstoque("O nome do produto é obrigatório.")
        if float(dados.get("estoque_minimo", 0)) < 0:
            raise ErroEstoque("O estoque mínimo não pode ser negativo.")
        if checar_quantidade and float(dados.get("quantidade", 0)) < 0:
            raise ErroEstoque("A quantidade não pode ser negativa.")

    # ---------------------------------------------------------- movimentação

    def _movimentar(self, produto_id: int, tipo: str, delta: float, observacao: str) -> float:
        with self.con:  # transação: saldo e histórico gravados juntos
            self.con.execute("BEGIN IMMEDIATE")
            produto = self.obter_produto(produto_id)
            if produto is None:
                raise ErroEstoque("Produto não encontrado.")
            saldo = round(float(produto["quantidade"]) + delta, 4)
            if saldo < 0:
                raise ErroEstoque(
                    f"Saldo insuficiente: há {produto['quantidade']:g} {produto['unidade']} "
                    f"de '{produto['nome']}' em estoque."
                )
            ts = agora()
            self.con.execute(
                "UPDATE produtos SET quantidade = ?, atualizado_em = ? WHERE id = ?",
                (saldo, ts, produto_id),
            )
            self.con.execute(
                """INSERT INTO movimentacoes (produto_id, tipo, quantidade, saldo_apos, observacao, data)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (produto_id, tipo, delta, saldo, observacao.strip(), ts),
            )
        return saldo

    def registrar_entrada(self, produto_id: int, qtd: float, observacao: str = "") -> float:
        if qtd <= 0:
            raise ErroEstoque("A quantidade da entrada deve ser maior que zero.")
        return self._movimentar(produto_id, "entrada", abs(qtd), observacao)

    def registrar_saida(self, produto_id: int, qtd: float, observacao: str = "") -> float:
        if qtd <= 0:
            raise ErroEstoque("A quantidade da saída deve ser maior que zero.")
        return self._movimentar(produto_id, "saida", -abs(qtd), observacao)

    def ajustar_estoque(self, produto_id: int, nova_qtd: float, observacao: str = "") -> float:
        produto = self.obter_produto(produto_id)
        if produto is None:
            raise ErroEstoque("Produto não encontrado.")
        if nova_qtd < 0:
            raise ErroEstoque("A quantidade ajustada não pode ser negativa.")
        delta = round(nova_qtd - float(produto["quantidade"]), 4)
        if delta == 0:
            return float(produto["quantidade"])
        return self._movimentar(produto_id, "ajuste", delta, observacao or "Ajuste de inventário")

    def listar_movimentacoes(
        self, busca: str = "", tipo: str = "", limite: int = 1000
    ) -> list[sqlite3.Row]:
        sql = """SELECT m.*, p.codigo, p.nome, p.unidade
                 FROM movimentacoes m JOIN produtos p ON p.id = m.produto_id
                 WHERE 1=1"""
        params: list = []
        if busca.strip():
            termo = f"%{busca.strip()}%"
            sql += " AND (p.codigo LIKE ? OR p.nome LIKE ? OR m.observacao LIKE ?)"
            params += [termo, termo, termo]
        if tipo:
            sql += " AND m.tipo = ?"
            params.append(tipo)
        sql += " ORDER BY m.data DESC, m.id DESC LIMIT ?"
        params.append(limite)
        return self.con.execute(sql, params).fetchall()

    # -------------------------------------------------------------- resumo

    def resumo(self) -> dict:
        linha = self.con.execute(
            """SELECT COUNT(*) AS itens,
                      COALESCE(SUM(quantidade * preco_custo), 0) AS valor_custo,
                      COALESCE(SUM(quantidade * preco_venda), 0) AS valor_venda,
                      COALESCE(SUM(CASE WHEN quantidade <= estoque_minimo THEN 1 ELSE 0 END), 0) AS baixos
               FROM produtos"""
        ).fetchone()
        return dict(linha)