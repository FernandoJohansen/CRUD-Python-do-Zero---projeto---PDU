"""Controle de Estoque / PDU — aplicativo desktop offline (PyQt5 + SQLite)."""
"""Iniciado em 23/08/2026 por Fernando Ayrton Johansen Neto: Github.com/FernandoJohansen"""
import csv
import sys
from datetime import datetime

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont, QKeySequence
from PyQt5.QtWidgets import (
    QAbstractItemView, QAction, QApplication, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)


from database import Banco, ErroEstoque, caminho_banco

VERSAO = "1.0.0"
COR_ALERTA = QColor("#ffe0e0")
COR_ATENCAO = QColor("#fff4d6")


def moeda(valor: float) -> str:
    texto = f"{valor:,.2f}"
    return "R$ " + texto.replace(",", "@").replace(".", ",").replace("@", ".")


def numero(valor: float) -> str:
    return f"{valor:g}"


def data_br(texto: str) -> str:
    try:
        return datetime.strptime(texto, "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return texto


def celula(texto: str, valor_ordenacao=None, alinhar_direita: bool = False) -> QTableWidgetItem:
    item = QTableWidgetItem(texto)
    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    if valor_ordenacao is not None:
        item.setData(Qt.UserRole + 1, valor_ordenacao)
        item.setData(Qt.EditRole, valor_ordenacao)
    if alinhar_direita:
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return item


class DialogoProduto(QDialog):
    """Cadastro e edição de produto."""

    def __init__(self, parent=None, produto=None):
        super().__init__(parent)
        self.produto = produto
        self.setWindowTitle("Editar produto" if produto else "Novo produto")
        self.setMinimumWidth(460)

        self.codigo = QLineEdit()
        self.codigo.setMaxLength(40)
        self.nome = QLineEdit()
        self.categoria = QLineEdit()
        self.unidade = QComboBox()
        self.unidade.setEditable(True)
        self.unidade.addItems(["un", "cx", "pct", "kg", "g", "L", "ml", "m", "par"])
        self.localizacao = QLineEdit()
        self.localizacao.setPlaceholderText("Ex.: Prateleira A3")

        self.quantidade = self._spin(sufixo="")
        self.estoque_minimo = self._spin(sufixo="")
        self.preco_custo = self._spin(prefixo="R$ ")
        self.preco_venda = self._spin(prefixo="R$ ")

        self.observacao = QPlainTextEdit()
        self.observacao.setMaximumHeight(70)

        form = QFormLayout()
        form.addRow("Código *", self.codigo)
        form.addRow("Nome *", self.nome)
        form.addRow("Categoria", self.categoria)
        form.addRow("Unidade", self.unidade)
        form.addRow("Local", self.localizacao)
        form.addRow("Quantidade", self.quantidade)
        form.addRow("Estoque mínimo", self.estoque_minimo)
        form.addRow("Preço de custo", self.preco_custo)
        form.addRow("Preço de venda", self.preco_venda)
        form.addRow("Observação", self.observacao)

        if produto:
            self.codigo.setText(produto["codigo"])
            self.nome.setText(produto["nome"])
            self.categoria.setText(produto["categoria"])
            self.unidade.setCurrentText(produto["unidade"])
            self.localizacao.setText(produto["localizacao"])
            self.quantidade.setValue(float(produto["quantidade"]))
            self.quantidade.setEnabled(False)
            self.quantidade.setToolTip("Use Entrada/Saída/Ajuste para alterar o saldo.")
            self.estoque_minimo.setValue(float(produto["estoque_minimo"]))
            self.preco_custo.setValue(float(produto["preco_custo"]))
            self.preco_venda.setValue(float(produto["preco_venda"]))
            self.observacao.setPlainText(produto["observacao"])

        botoes = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        botoes.button(QDialogButtonBox.Save).setText("Salvar")
        botoes.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(botoes)

    @staticmethod
    def _spin(prefixo: str = "", sufixo: str = "") -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setDecimals(2)
        spin.setRange(0, 9_999_999)
        spin.setGroupSeparatorShown(True)
        if prefixo:
            spin.setPrefix(prefixo)
        if sufixo:
            spin.setSuffix(sufixo)
        return spin

    def dados(self) -> dict:
        return {
            "codigo": self.codigo.text().strip(),
            "nome": self.nome.text().strip(),
            "categoria": self.categoria.text().strip(),
            "unidade": self.unidade.currentText().strip() or "un",
            "quantidade": self.quantidade.value(),
            "estoque_minimo": self.estoque_minimo.value(),
            "preco_custo": self.preco_custo.value(),
            "preco_venda": self.preco_venda.value(),
            "localizacao": self.localizacao.text().strip(),
            "observacao": self.observacao.toPlainText().strip(),
        }


class DialogoMovimento(QDialog):
    """Entrada, saída ou ajuste de um produto."""

    def __init__(self, parent, produto, tipo: str):
        super().__init__(parent)
        self.tipo = tipo
        titulos = {"entrada": "Entrada de estoque", "saida": "Saída de estoque", "ajuste": "Ajuste de inventário"}
        self.setWindowTitle(titulos[tipo])
        self.setMinimumWidth(400)

        saldo = float(produto["quantidade"])
        cabecalho = QLabel(f"<b>{produto['nome']}</b><br>Saldo atual: {numero(saldo)} {produto['unidade']}")
        cabecalho.setTextFormat(Qt.RichText)

        self.quantidade = QDoubleSpinBox()
        self.quantidade.setDecimals(2)
        self.quantidade.setRange(0, 9_999_999)
        self.quantidade.setGroupSeparatorShown(True)
        self.quantidade.setValue(saldo if tipo == "ajuste" else 1)
        if tipo != "ajuste":
            self.quantidade.setMinimum(0.01)

        self.observacao = QLineEdit()
        self.observacao.setPlaceholderText("Ex.: NF 1234, venda balcão, quebra…")

        rotulo = "Nova quantidade" if tipo == "ajuste" else "Quantidade"
        form = QFormLayout()
        form.addRow(rotulo, self.quantidade)
        form.addRow("Observação", self.observacao)

        botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botoes.button(QDialogButtonBox.Ok).setText("Confirmar")
        botoes.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(cabecalho)
        layout.addLayout(form)
        layout.addWidget(botoes)
        self.quantidade.setFocus()
        self.quantidade.selectAll()


class JanelaPrincipal(QMainWindow):
    COLUNAS = ["Código", "Nome", "Categoria", "Un.", "Quantidade", "Mínimo",
               "Custo", "Venda", "Total (custo)", "Local"]
    COLUNAS_MOV = ["Data", "Produto", "Tipo", "Quantidade", "Saldo após", "Observação"]

    def __init__(self, banco: Banco):
        super().__init__()
        self.banco = banco
        self.setWindowTitle(f"Controle de Estoque {VERSAO}")
        self.resize(1080, 640)

        self.abas = QTabWidget()
        self.abas.addTab(self._aba_produtos(), "Produtos")
        self.abas.addTab(self._aba_movimentacoes(), "Movimentações")
        self.abas.currentChanged.connect(self._aba_mudou)
        self.setCentralWidget(self.abas)

        self._menus()
        self.statusBar().showMessage("Pronto")
        self.recarregar()

    # ------------------------------------------------------------------ UI

    def _aba_produtos(self) -> QWidget:
        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Buscar por código, nome, categoria ou local…  (Ctrl+F)")
        self.busca.setClearButtonEnabled(True)
        self.busca.textChanged.connect(self.recarregar_produtos)

        self.filtro_baixo = QCheckBox("Somente abaixo do mínimo")
        self.filtro_baixo.stateChanged.connect(self.recarregar_produtos)

        topo = QHBoxLayout()
        topo.addWidget(self.busca, 1)
        topo.addWidget(self.filtro_baixo)

        self.tabela = QTableWidget(0, len(self.COLUNAS))
        self.tabela.setHorizontalHeaderLabels(self.COLUNAS)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.setAlternatingRowColors(True)
        self.tabela.setSortingEnabled(True)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tabela.doubleClicked.connect(self.editar_produto)

        botoes = QHBoxLayout()
        for texto, slot in [
            ("Novo produto", self.novo_produto),
            ("Editar", self.editar_produto),
            ("Excluir", self.excluir_produto),
            ("Entrada", lambda: self.movimentar("entrada")),
            ("Saída", lambda: self.movimentar("saida")),
            ("Ajuste", lambda: self.movimentar("ajuste")),
        ]:
            botao = QPushButton(texto)
            botao.clicked.connect(slot)
            botoes.addWidget(botao)
        botoes.addStretch()

        self.rotulo_resumo = QLabel()
        fonte = QFont()
        fonte.setBold(True)
        self.rotulo_resumo.setFont(fonte)

        pagina = QWidget()
        layout = QVBoxLayout(pagina)
        layout.addLayout(topo)
        layout.addWidget(self.tabela)
        layout.addLayout(botoes)
        layout.addWidget(self.rotulo_resumo)
        return pagina

    def _aba_movimentacoes(self) -> QWidget:
        self.busca_mov = QLineEdit()
        self.busca_mov.setPlaceholderText("Buscar por produto ou observação…")
        self.busca_mov.setClearButtonEnabled(True)
        self.busca_mov.textChanged.connect(self.recarregar_movimentacoes)

        self.filtro_tipo = QComboBox()
        self.filtro_tipo.addItem("Todos os tipos", "")
        self.filtro_tipo.addItem("Entradas", "entrada")
        self.filtro_tipo.addItem("Saídas", "saida")
        self.filtro_tipo.addItem("Ajustes", "ajuste")
        self.filtro_tipo.currentIndexChanged.connect(self.recarregar_movimentacoes)

        topo = QHBoxLayout()
        topo.addWidget(self.busca_mov, 1)
        topo.addWidget(self.filtro_tipo)

        self.tabela_mov = QTableWidget(0, len(self.COLUNAS_MOV))
        self.tabela_mov.setHorizontalHeaderLabels(self.COLUNAS_MOV)
        self.tabela_mov.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela_mov.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela_mov.setAlternatingRowColors(True)
        self.tabela_mov.setSortingEnabled(True)
        self.tabela_mov.verticalHeader().setVisible(False)
        self.tabela_mov.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)

        pagina = QWidget()
        layout = QVBoxLayout(pagina)
        layout.addLayout(topo)
        layout.addWidget(self.tabela_mov)
        return pagina

    def _menus(self) -> None:
        arquivo = self.menuBar().addMenu("&Arquivo")

        acao_novo = QAction("&Novo produto", self, shortcut=QKeySequence.New, triggered=self.novo_produto)
        acao_csv = QAction("Exportar &CSV…", self, shortcut="Ctrl+E", triggered=self.exportar_csv)
        acao_backup = QAction("&Backup do banco…", self, triggered=self.fazer_backup)
        acao_sair = QAction("Sai&r", self, shortcut="Ctrl+Q", triggered=self.close)
        for acao in (acao_novo, acao_csv, acao_backup):
            arquivo.addAction(acao)
        arquivo.addSeparator()
        arquivo.addAction(acao_sair)

        ajuda = self.menuBar().addMenu("A&juda")
        ajuda.addAction(QAction("&Sobre", self, triggered=self.sobre))

        self.addAction(QAction("Buscar", self, shortcut="Ctrl+F", triggered=lambda: self.busca.setFocus()))
        self.addAction(QAction("Atualizar", self, shortcut=QKeySequence.Refresh, triggered=self.recarregar))

    # -------------------------------------------------------------- dados

    def recarregar(self) -> None:
        self.recarregar_produtos()
        self.recarregar_movimentacoes()

    def _aba_mudou(self, indice: int) -> None:
        if indice == 1:
            self.recarregar_movimentacoes()

    def recarregar_produtos(self) -> None:
        produtos = self.banco.listar_produtos(self.busca.text(), self.filtro_baixo.isChecked())
        self.tabela.setSortingEnabled(False)
        self.tabela.setRowCount(0)
        for linha, p in enumerate(produtos):
            self.tabela.insertRow(linha)
            qtd, minimo = float(p["quantidade"]), float(p["estoque_minimo"])
            total = qtd * float(p["preco_custo"])
            valores = [
                celula(p["codigo"]),
                celula(p["nome"]),
                celula(p["categoria"]),
                celula(p["unidade"]),
                celula(numero(qtd), qtd, True),
                celula(numero(minimo), minimo, True),
                celula(moeda(p["preco_custo"]), float(p["preco_custo"]), True),
                celula(moeda(p["preco_venda"]), float(p["preco_venda"]), True),
                celula(moeda(total), total, True),
                celula(p["localizacao"]),
            ]
            valores[0].setData(Qt.UserRole, p["id"])
            cor = None
            if qtd <= 0:
                cor = COR_ALERTA
            elif qtd <= minimo:
                cor = COR_ATENCAO
            for coluna, item in enumerate(valores):
                if cor:
                    item.setBackground(cor)
                self.tabela.setItem(linha, coluna, item)
        self.tabela.setSortingEnabled(True)
        self.tabela.resizeColumnsToContents()
        self.tabela.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._atualizar_resumo(len(produtos))

    def recarregar_movimentacoes(self) -> None:
        movimentos = self.banco.listar_movimentacoes(
            self.busca_mov.text(), self.filtro_tipo.currentData()
        )
        rotulos = {"entrada": "Entrada", "saida": "Saída", "ajuste": "Ajuste"}
        self.tabela_mov.setSortingEnabled(False)
        self.tabela_mov.setRowCount(0)
        for linha, m in enumerate(movimentos):
            self.tabela_mov.insertRow(linha)
            delta = float(m["quantidade"])
            texto_delta = f"{'+' if delta > 0 else ''}{numero(delta)} {m['unidade']}"
            itens = [
                celula(data_br(m["data"]), m["data"]),
                celula(f"{m['codigo']} — {m['nome']}"),
                celula(rotulos[m["tipo"]]),
                celula(texto_delta, delta, True),
                celula(numero(float(m["saldo_apos"])), float(m["saldo_apos"]), True),
                celula(m["observacao"]),
            ]
            itens[3].setForeground(QColor("#1a7f37") if delta > 0 else QColor("#b42318"))
            for coluna, item in enumerate(itens):
                self.tabela_mov.setItem(linha, coluna, item)
        self.tabela_mov.setSortingEnabled(True)
        self.tabela_mov.resizeColumnsToContents()
        self.tabela_mov.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)

    def _atualizar_resumo(self, exibidos: int) -> None:
        r = self.banco.resumo()
        self.rotulo_resumo.setText(
            f"{exibidos} exibido(s)  |  {r['itens']} produto(s) cadastrado(s)  |  "
            f"Valor em estoque (custo): {moeda(r['valor_custo'])}  |  "
            f"Abaixo do mínimo: {r['baixos']}"
        )

    # -------------------------------------------------------------- ações

    def _produto_selecionado(self):
        linha = self.tabela.currentRow()
        if linha < 0:
            QMessageBox.information(self, "Selecione", "Selecione um produto na lista.")
            return None
        produto_id = self.tabela.item(linha, 0).data(Qt.UserRole)
        return self.banco.obter_produto(int(produto_id))

    def novo_produto(self) -> None:
        dialogo = DialogoProduto(self)
        while dialogo.exec_() == QDialog.Accepted:
            try:
                self.banco.criar_produto(dialogo.dados())
            except ErroEstoque as erro:
                QMessageBox.warning(self, "Não foi possível salvar", str(erro))
                continue
            self.recarregar()
            self.statusBar().showMessage("Produto cadastrado.", 4000)
            return

    def editar_produto(self) -> None:
        produto = self._produto_selecionado()
        if not produto:
            return
        dialogo = DialogoProduto(self, produto)
        while dialogo.exec_() == QDialog.Accepted:
            try:
                self.banco.atualizar_produto(produto["id"], dialogo.dados())
            except ErroEstoque as erro:
                QMessageBox.warning(self, "Não foi possível salvar", str(erro))
                continue
            self.recarregar()
            self.statusBar().showMessage("Produto atualizado.", 4000)
            return

    def excluir_produto(self) -> None:
        produto = self._produto_selecionado()
        if not produto:
            return
        resposta = QMessageBox.question(
            self,
            "Excluir produto",
            f"Excluir '{produto['nome']}' e todo o seu histórico de movimentações?\n"
            "Esta ação não pode ser desfeita.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if resposta == QMessageBox.Yes:
            self.banco.excluir_produto(produto["id"])
            self.recarregar()
            self.statusBar().showMessage("Produto excluído.", 4000)

    def movimentar(self, tipo: str) -> None:
        produto = self._produto_selecionado()
        if not produto:
            return
        dialogo = DialogoMovimento(self, produto, tipo)
        while dialogo.exec_() == QDialog.Accepted:
            qtd = dialogo.quantidade.value()
            obs = dialogo.observacao.text()
            try:
                if tipo == "entrada":
                    saldo = self.banco.registrar_entrada(produto["id"], qtd, obs)
                elif tipo == "saida":
                    saldo = self.banco.registrar_saida(produto["id"], qtd, obs)
                else:
                    saldo = self.banco.ajustar_estoque(produto["id"], qtd, obs)
            except ErroEstoque as erro:
                QMessageBox.warning(self, "Operação não realizada", str(erro))
                continue
            self.recarregar()
            self.statusBar().showMessage(
                f"{produto['nome']}: novo saldo {numero(saldo)} {produto['unidade']}.", 6000
            )
            if saldo <= float(produto["estoque_minimo"]):
                QMessageBox.warning(
                    self, "Estoque baixo",
                    f"'{produto['nome']}' está em {numero(saldo)} {produto['unidade']}, "
                    f"no mínimo ou abaixo ({numero(float(produto['estoque_minimo']))}).",
                )
            return

    def exportar_csv(self) -> None:
        produtos_aba = self.abas.currentIndex() == 0
        sugestao = ("produtos" if produtos_aba else "movimentacoes") + \
            f"_{datetime.now():%Y-%m-%d}.csv"
        caminho, _ = QFileDialog.getSaveFileName(self, "Exportar CSV", sugestao, "CSV (*.csv)")
        if not caminho:
            return
        tabela = self.tabela if produtos_aba else self.tabela_mov
        colunas = self.COLUNAS if produtos_aba else self.COLUNAS_MOV
        try:
            with open(caminho, "w", newline="", encoding="utf-8-sig") as arquivo:
                escritor = csv.writer(arquivo, delimiter=";")
                escritor.writerow(colunas)
                for linha in range(tabela.rowCount()):
                    escritor.writerow(
                        [tabela.item(linha, c).text() if tabela.item(linha, c) else ""
                         for c in range(len(colunas))]
                    )
        except OSError as erro:
            QMessageBox.critical(self, "Erro ao exportar", str(erro))
            return
        self.statusBar().showMessage(f"Exportado para {caminho}", 6000)

    def fazer_backup(self) -> None:
        sugestao = f"backup_estoque_{datetime.now():%Y-%m-%d_%H%M}.db"
        caminho, _ = QFileDialog.getSaveFileName(self, "Salvar backup", sugestao, "Banco SQLite (*.db)")
        if not caminho:
            return
        try:
            destino = Banco(caminho)
            self.banco.con.backup(destino.con)
            destino.fechar()
        except Exception as erro:  # noqa: BLE001 — feedback ao usuário
            QMessageBox.critical(self, "Erro no backup", str(erro))
            return
        QMessageBox.information(self, "Backup concluído", f"Cópia salva em:\n{caminho}")

    def sobre(self) -> None:
        QMessageBox.about(
            self,
            "Sobre",
            f"<b>Controle de Estoque</b> {VERSAO}<br><br>"
            "Aplicativo offline em Python (PyQt5 + SQLite).<br><br>"
            f"Banco de dados:<br><code>{caminho_banco()}</code>",
        )

    def closeEvent(self, evento):  # noqa: N802 — assinatura do Qt
        self.banco.fechar()
        super().closeEvent(evento)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Controle de Estoque")
    app.setStyle("Fusion")
    try:
        banco = Banco()
    except Exception as erro:  # noqa: BLE001
        QMessageBox.critical(None, "Erro ao abrir o banco", str(erro))
        return 1
    janela = JanelaPrincipal(banco)
    janela.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())