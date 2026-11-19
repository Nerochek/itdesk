"""Десктопный интерфейс на PyQt6 (п.10, п.11). Запуск: python run_client.py"""
import sys
import json
from pathlib import Path
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QPixmap, QFont, QFontDatabase

from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QDialog, QFileDialog,
                             QFormLayout, QHBoxLayout, QLineEdit, QMainWindow, QMessageBox,
                             QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem,
                             QTextBrowser, QVBoxLayout, QWidget, QLabel, QScrollArea)

from itdesk_core import (CATEGORY, PRIORITY, STATUS, Api, ApiError, format_stats,
                         format_ticket_html, label)


def setup_font(application):
    """Явный шрифт с кириллицей, включая Qt offscreen на Windows."""
    import matplotlib
    path = Path(matplotlib.get_data_path()) / "fonts/ttf/DejaVuSans.ttf"
    identifier = QFontDatabase.addApplicationFont(str(path))
    families = QFontDatabase.applicationFontFamilies(identifier)
    if families:
        application.setFont(QFont(families[0], 10))


def fill(combo, mapping):
    for key, text in mapping.items():
        combo.addItem(text, key)


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
        for text, w in [("Тема", self.title), ("Аудитория/кабинет", self.room),
                        ("Категория", self.cat), ("Приоритет", self.prio), ("Описание", self.desc)]:
            form.addRow(text, w)
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
        self.view.setHtml(format_ticket_html(t))

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
        self.resize(1320, 650)
        self.filter = QComboBox()
        self.filter.addItem("Все статусы", None)
        fill(self.filter, STATUS)
        self.filter.currentIndexChanged.connect(self.refresh)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["№", "Тема", "Категория", "Приоритет", "Статус", "Исполнитель", "Источник"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(1, 330)
        self.table.doubleClicked.connect(self.open_ticket)
        bar = QHBoxLayout()
        bar.addWidget(self.filter)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по теме…")
        self.search.returnPressed.connect(self.refresh)
        buttons = [("Новая заявка", self.new_ticket), ("Открыть", self.open_ticket), ("Обновить", self.refresh)]
        if u["role"] != "user":
            buttons += [("Статистика", self.show_stats), ("Экспорт CSV", self.export),
                        ("Документ MongoDB", self.show_document), ("Удалить", self.delete_ticket),
                        ("Обработка данных", self.show_processing)]
        for text, fn in buttons:
            b = QPushButton(text)
            b.clicked.connect(fn)
            bar.addWidget(b)
        root = QWidget()
        lay = QVBoxLayout(root)
        lay.addLayout(bar)
        lay.addWidget(self.search)
        lay.addWidget(self.table)
        self.setCentralWidget(root)
        self.refresh()

    def guard(self, fn):
        try:
            return fn()
        except ApiError as e:
            QMessageBox.warning(self, "Ошибка", str(e))

    def refresh(self, *_):
        rows = self.guard(lambda: self.api.tickets(self.filter.currentData(), self.search.text().strip())) or []
        self.table.setRowCount(len(rows))
        for i, t in enumerate(rows):
            vals = [t["id"], t["title"], label(CATEGORY, t["category"]), label(PRIORITY, t["priority"]),
                    label(STATUS, t["status"]), t["assignee"] or "—",
                    {"itdesk": "Пользователь", "demo": "Учебные", "jsonplaceholder": "Внешний API"}.get(t.get("source"), "—")]
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
            QMessageBox.information(self, "Статистика", format_stats(s))

    def show_document(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Документ MongoDB", "Сначала выберите заявку в списке.")
            return
        data = self.guard(lambda: self.api.document(int(self.table.item(row, 0).text())))
        if data:
            dialog = QDialog(self)
            dialog.setWindowTitle("Документ заявки в MongoDB")
            dialog.resize(700, 600)
            view = QPlainTextEdit()
            view.setReadOnly(True)
            view.setPlainText(json.dumps(data, ensure_ascii=False, indent=2))
            layout = QVBoxLayout(dialog)
            layout.addWidget(view)
            dialog.exec()

    def delete_ticket(self):
        row = self.table.currentRow()
        if row < 0:
            return
        tid = int(self.table.item(row, 0).text())
        if QMessageBox.question(self, "Удалить заявку", f"Удалить заявку №{tid} из MongoDB?") == QMessageBox.StandardButton.Yes:
            self.guard(lambda: self.api.delete_ticket(tid))
            self.refresh()

    def show_processing(self):
        ProcessingDialog(self.api, self).exec()
        self.refresh()

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить", "tickets.csv", "CSV (*.csv)")
        if path:
            data = self.guard(self.api.export_csv)
            if data:
                with open(path, "wb") as f:
                    f.write(data)


class ProcessingDialog(QDialog):
    """Один экран для выполнения пунктов обработки и просмотра результата."""
    ACTIONS = [("Учебные заявки", "seed"), ("Импорт из API", "import"),
               ("Очистка Pandas", "clean"), ("Spark и SQL", "spark"),
               ("Hadoop MapReduce", "hadoop"), ("Проверить поиск", "optimize"),
               ("Построить графики", "plot"), ("Выполнить обработку целиком", "all")]

    def __init__(self, api, parent=None):
        super().__init__(parent)
        self.api = api
        self.job_id = None
        self.setWindowTitle("Обработка заявок из MongoDB")
        self.resize(1100, 750)
        layout = QVBoxLayout(self)
        explanation = QLabel("Обработка использует текущие заявки приложения. Учебные записи добавляются только отдельной кнопкой.")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self.buttons = []
        for batch in (self.ACTIONS[:4], self.ACTIONS[4:]):
            row = QHBoxLayout()
            for title, action in batch:
                button = QPushButton(title)
                button.clicked.connect(lambda checked=False, name=action: self.start(name))
                self.buttons.append(button)
                row.addWidget(button)
            layout.addLayout(row)
        self.status = QLabel("Выберите действие. Для Spark и Hadoop может потребоваться до нескольких минут.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.result = QPlainTextEdit()
        self.result.setReadOnly(True)
        self.result.setMaximumHeight(180)
        layout.addWidget(self.result)
        self.image = QLabel("Здесь появятся графики после обработки.")
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.image)
        layout.addWidget(scroll)
        files = QHBoxLayout()
        self.files = QComboBox()
        self.save = QPushButton("Сохранить выбранный результат…")
        self.save.clicked.connect(self.save_file)
        self.save.setEnabled(False)
        files.addWidget(self.files)
        files.addWidget(self.save)
        layout.addLayout(files)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.poll)

    def start(self, action):
        try:
            if action == "seed":
                answer = QMessageBox.question(self, "Учебные данные", "Добавить до 1000 помеченных учебных заявок в общий список?")
                if answer != QMessageBox.StandardButton.Yes:
                    return
            job = self.api.start_processing(action)
            self.job_id = job["id"]
            self.files.clear()
            self.save.setEnabled(False)
            self.result.clear()
            self.image.setText("Ожидание результата обработки…")
            self.status.setText("Выполняется… Можно дождаться результата в этом окне.")
            for button in self.buttons:
                button.setEnabled(False)
            self.timer.start()
        except ApiError as error:
            QMessageBox.warning(self, "Не удалось начать", str(error))

    def poll(self):
        try:
            job = self.api.processing_job(self.job_id)
            if job["status"] == "running":
                return
            self.timer.stop()
            for button in self.buttons:
                button.setEnabled(True)
            if job["status"] == "failed":
                self.status.setText("Обработка не завершена. Причина ниже; журнал можно сохранить.")
                self.result.setPlainText(job.get("error", "Неизвестная ошибка"))
                self.files.addItem("job.log")
                self.save.setEnabled(True)
                return
            payload = job["result"]
            self.status.setText("Готово. Результаты относятся к снимку заявок на момент запуска.")
            self.result.setPlainText("\n".join(payload["messages"]))
            allowed = {"dashboard.png", "dashboard.pdf", "summary.csv", "clean.csv", "clean_receipt.json",
                       "spark_sql.json", "spark_plans.txt", "mongo_explain.json", "hadoop_status.json", "hadoop_result.json"}
            self.files.addItems([name for name in payload["files"] if name in allowed])
            self.save.setEnabled(self.files.count() > 0)
            if "dashboard.png" in payload["files"]:
                pixmap = QPixmap()
                pixmap.loadFromData(self.api.processing_file(self.job_id, "dashboard.png"))
                self.image.setPixmap(pixmap.scaledToWidth(1000, Qt.TransformationMode.SmoothTransformation))
        except ApiError as error:
            self.timer.stop()
            self.status.setText(f"Не удалось получить состояние: {error}. Задача может продолжаться на сервере.")
            for button in self.buttons:
                button.setEnabled(True)

    def save_file(self):
        filename = self.files.currentText()
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить результат", filename)
        if path:
            try:
                data = self.api.processing_file(self.job_id, filename)
                # JSON endpoint API декодирует в словарь, файл сохраняем как JSON.
                if isinstance(data, (dict, list)):
                    data = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
                with open(path, "wb") as stream:
                    stream.write(data)
            except (ApiError, OSError) as error:
                QMessageBox.warning(self, "Ошибка сохранения", str(error))

    def reject(self):
        if self.timer.isActive():
            QMessageBox.information(self, "Обработка", "Дождитесь завершения обработки перед закрытием окна.")
            return
        super().reject()


def main():
    app = QApplication(sys.argv)
    setup_font(app)
    api = Api()
    if LoginDialog(api).exec():
        w = MainWindow(api)
        w.show()
        sys.exit(app.exec())


if __name__ == "__main__":
    main()
