"""Десктопный интерфейс на PyQt6 (п.10, п.11). Запуск: python run_client.py"""
import html
import sys

from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QDialog, QFileDialog,
                             QFormLayout, QHBoxLayout, QLineEdit, QMainWindow, QMessageBox,
                             QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem,
                             QTextBrowser, QVBoxLayout, QWidget)

from .api import Api, ApiError

STATUS = {"new": "Новая", "in_progress": "В работе", "resolved": "Решена", "closed": "Закрыта"}
PRIORITY = {"low": "Низкий", "medium": "Средний", "high": "Высокий"}
CATEGORY = {"hardware": "Оборудование", "network": "Сеть / Wi-Fi", "software": "ПО",
            "projector": "Проектор / аудитория", "account": "Учётная запись", "other": "Другое"}
esc = html.escape


def fill(combo, mapping):
    for key, label in mapping.items():
        combo.addItem(label, key)


class LoginDialog(QDialog):
    def __init__(self, api):
        super().__init__()
        self.api = api
        self.setWindowTitle("ITDesk — вход")
        self.user, self.pw = QLineEdit(), QLineEdit()
        self.pw.setEchoMode(QLineEdit.EchoMode.Password)
        form = QFormLayout(self)
        form.addRow("Логин", self.user)
        form.addRow("Пароль", self.pw)
        row = QHBoxLayout()
        for text, fn in [("Войти", self.do_login), ("Регистрация", self.do_register)]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        form.addRow(row)

    def do_login(self):
        try:
            self.api.login(self.user.text().strip(), self.pw.text())
            self.accept()
        except ApiError as e:
            QMessageBox.warning(self, "Ошибка", str(e))

    def do_register(self):
        try:
            self.api.register(self.user.text().strip(), self.pw.text())
            QMessageBox.information(self, "Готово", "Аккаунт создан, теперь войдите.")
        except ApiError as e:
            QMessageBox.warning(self, "Ошибка", str(e))


class NewTicketDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Новая заявка")
        self.title, self.room = QLineEdit(), QLineEdit()
        self.desc = QPlainTextEdit()
        self.cat, self.prio = QComboBox(), QComboBox()
        fill(self.cat, CATEGORY)
        fill(self.prio, PRIORITY)
        self.prio.setCurrentIndex(1)
        form = QFormLayout(self)
        for label, w in [("Тема", self.title), ("Аудитория/кабинет", self.room),
                         ("Категория", self.cat), ("Приоритет", self.prio), ("Описание", self.desc)]:
            form.addRow(label, w)
        ok = QPushButton("Отправить")
        ok.clicked.connect(self.accept)
        form.addRow(ok)

    def data(self):
        return dict(title=self.title.text().strip(), description=self.desc.toPlainText().strip(),
                    category=self.cat.currentData(), priority=self.prio.currentData(),
                    room=self.room.text().strip())


class TicketDialog(QDialog):
    def __init__(self, api, tid):
        super().__init__()
        self.api, self.tid = api, tid
        self.resize(560, 560)
        self.view = QTextBrowser()
        self.comment = QLineEdit()
        self.comment.setPlaceholderText("Комментарий…")
        send = QPushButton("Отправить")
        send.clicked.connect(self.send_comment)
        lay = QVBoxLayout(self)
        lay.addWidget(self.view)
        row = QHBoxLayout()
        row.addWidget(self.comment)
        row.addWidget(send)
        lay.addLayout(row)
        if api.user["role"] != "user":
            self.status = QComboBox()
            fill(self.status, STATUS)
            take = QPushButton("Взять в работу")
            take.clicked.connect(self.take)
            save = QPushButton("Сохранить статус")
            save.clicked.connect(self.save_status)
            r2 = QHBoxLayout()
            for w in (self.status, save, take):
                r2.addWidget(w)
            lay.addLayout(r2)
        self.reload()

    def reload(self):
        t = self.api.ticket(self.tid)
        if hasattr(self, "status"):
            self.status.setCurrentIndex(self.status.findData(t["status"]))
        h = (f"<h3>#{t['id']} {esc(t['title'])}</h3><p><b>Статус:</b> {STATUS[t['status']]} | "
             f"<b>Приоритет:</b> {PRIORITY[t['priority']]} | <b>Категория:</b> {CATEGORY[t['category']]}<br>"
             f"<b>Автор:</b> {esc(t['author'])} | <b>Исполнитель:</b> {esc(t['assignee'] or '—')} | "
             f"<b>Кабинет:</b> {esc(t['room'] or '—')}</p><p>{esc(t['description'])}</p>"
             f"<hr><b>Комментарии</b><br>")
        h += "".join(f"<p><i>{esc(c['username'])}, {c['created_at']}</i>: {esc(c['text'])}</p>"
                     for c in t["comments"])
        h += "<hr><b>История</b><br>" + "".join(
            f"<small>{x['created_at']} — {esc(x['username'])}: {esc(x['action'])}</small><br>"
            for x in t["history"])
        self.view.setHtml(h)

    def _safe(self, fn):
        try:
            fn()
            self.reload()
        except ApiError as e:
            QMessageBox.warning(self, "Ошибка", str(e))

    def send_comment(self):
        text = self.comment.text().strip()
        if text:
            self._safe(lambda: self.api.comment(self.tid, text))
            self.comment.clear()

    def save_status(self):
        self._safe(lambda: self.api.update_ticket(self.tid, status=self.status.currentData()))

    def take(self):
        self._safe(lambda: self.api.update_ticket(self.tid, assignee_id=self.api.user["id"],
                                                  status="in_progress"))


class MainWindow(QMainWindow):
    def __init__(self, api):
        super().__init__()
        self.api = api
        u = api.user
        self.setWindowTitle(f"ITDesk — {u['username']} ({u['role']})")
        self.resize(940, 520)
        self.filter = QComboBox()
        self.filter.addItem("Все статусы", None)
        fill(self.filter, STATUS)
        self.filter.currentIndexChanged.connect(self.refresh)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["№", "Тема", "Категория", "Приоритет", "Статус", "Исполнитель"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(1, 330)
        self.table.doubleClicked.connect(self.open_ticket)
        bar = QHBoxLayout()
        bar.addWidget(self.filter)
        buttons = [("Новая заявка", self.new_ticket), ("Открыть", self.open_ticket), ("Обновить", self.refresh)]
        if u["role"] != "user":
            buttons += [("Статистика", self.show_stats), ("Экспорт CSV", self.export)]
        for text, fn in buttons:
            b = QPushButton(text)
            b.clicked.connect(fn)
            bar.addWidget(b)
        root = QWidget()
        lay = QVBoxLayout(root)
        lay.addLayout(bar)
        lay.addWidget(self.table)
        self.setCentralWidget(root)
        self.refresh()

    def guard(self, fn):
        try:
            return fn()
        except ApiError as e:
            QMessageBox.warning(self, "Ошибка", str(e))

    def refresh(self, *_):
        rows = self.guard(lambda: self.api.tickets(self.filter.currentData())) or []
        self.table.setRowCount(len(rows))
        for i, t in enumerate(rows):
            vals = [t["id"], t["title"], CATEGORY[t["category"]], PRIORITY[t["priority"]],
                    STATUS[t["status"]], t["assignee"] or "—"]
            for j, v in enumerate(vals):
                self.table.setItem(i, j, QTableWidgetItem(str(v)))

    def new_ticket(self):
        dlg = NewTicketDialog()
        if dlg.exec():
            self.guard(lambda: self.api.create_ticket(**dlg.data()))
            self.refresh()

    def open_ticket(self, *_):
        r = self.table.currentRow()
        if r >= 0:
            tid = int(self.table.item(r, 0).text())
            self.guard(lambda: TicketDialog(self.api, tid).exec())
            self.refresh()

    def show_stats(self):
        s = self.guard(self.api.stats)
        if s:
            fmt = lambda d, m: "\n".join(f"  {m.get(k, k)}: {v}" for k, v in d.items()) or "  —"
            QMessageBox.information(
                self, "Статистика",
                f"По статусам:\n{fmt(s['by_status'], STATUS)}\n\nПо категориям:\n"
                f"{fmt(s['by_category'], CATEGORY)}\n\nПо приоритетам:\n{fmt(s['by_priority'], PRIORITY)}")

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить", "tickets.csv", "CSV (*.csv)")
        if path:
            data = self.guard(self.api.export_csv)
            if data:
                with open(path, "wb") as f:
                    f.write(data)


def main():
    app = QApplication(sys.argv)
    api = Api()
    if LoginDialog(api).exec():
        w = MainWindow(api)
        w.show()
        sys.exit(app.exec())


if __name__ == "__main__":
    main()
