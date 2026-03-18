"""
StrangerThings_GUI_with_Login.py
A Stranger Things–themed Python GUI with a themed Login Portal (single-file) using PySide6.

This visual-only GUI includes:
- A Stranger Things styled login screen (username + password) with animated flicker and glowing "ENTER" button.
- After successful login, the main Stranger Things themed UI (visual only) appears.
- No network or external authentication — a local placeholder check is used. Replace `check_credentials()` with your backend auth if needed.

Dependencies:
- Python 3.8+
- pip install PySide6

Run:
python StrangerThings_GUI_with_Login.py

Default demo credentials (use to get inside):
- username: eleven
- password: 0119

Note: Place a background image named `stranger_bg.jpg` in the same folder to get the full wallpaper effect.
"""

import sys
import time
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QFontDatabase, QFont, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QStackedLayout,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
)


# ----------------------------- Utilities ---------------------------------

def load_font_if_present(filename: str):
    if Path(filename).exists():
        _id = QFontDatabase.addApplicationFont(str(Path(filename).absolute()))
        families = QFontDatabase.applicationFontFamilies(_id)
        if families:
            return families[0]
    return None


# ----------------------------- Visual Effects ----------------------------

class FlickerLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._opacity = 1.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1800)
        self._flicker_timer = QTimer(self)
        self._flicker_timer.timeout.connect(self._flicker_step)
        self._flicker_step_count = 0

    def _tick(self):
        # trigger occasional flicker
        if int(time.time() * 1000) % 11 == 0:
            self._flicker_step_count = 5
            self._flicker_timer.start(55)

    def _flicker_step(self):
        if self._flicker_step_count <= 0:
            self._flicker_timer.stop()
            self._opacity = 1.0
            self.update()
            return
        self._opacity = 0.4 + (self._flicker_step_count % 3) * 0.2
        self._flicker_step_count -= 1
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setOpacity(self._opacity)
        super().paintEvent(event)
        painter.end()


class PulsingButton(QPushButton):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._pulse = 0
        self._dir = 1
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.pulse)
        self.timer.start(80)

    def pulse(self):
        self._pulse += self._dir * 0.06
        if self._pulse >= 1:
            self._pulse = 1
            self._dir = -1
        elif self._pulse <= 0:
            self._pulse = 0
            self._dir = 1
        glow = 0.25 + self._pulse * 0.75
        self.setStyleSheet(self.style_template(glow))

    def style_template(self, glow):
        return f"""
        QPushButton {{
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ff4b4b, stop:1 #9b0000);
            border: none;
            padding: 12px 16px;
            border-radius: 8px;
            font-weight: bold;
            color: #fff;
            text-shadow: 0 0 {int(8*glow)}px rgba(255,60,60,0.9);
        }}
        QPushButton:pressed {{
            transform: translateY(1px);
        }}
        """


# ----------------------------- Login Widget ------------------------------

class LoginWidget(QWidget):
    login_success = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName('login_widget')
        self.setStyleSheet(self.login_styles())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(120, 80, 120, 80)
        layout.setSpacing(14)

        title = FlickerLabel('STRANGER THINGS')
        title.setObjectName('login_title')
        title.setAlignment(Qt.AlignCenter)
        title.setFixedHeight(90)
        layout.addWidget(title)

        self.user = QLineEdit()
        self.user.setPlaceholderText('username')
        self.user.setObjectName('user')
        layout.addWidget(self.user)

        self.pwd = QLineEdit()
        self.pwd.setPlaceholderText('password')
        self.pwd.setEchoMode(QLineEdit.Password)
        self.pwd.setObjectName('pwd')
        layout.addWidget(self.pwd)

        btns = QHBoxLayout()
        self.enter_btn = PulsingButton('ENTER')
        self.enter_btn.clicked.connect(self.attempt_login)
        btns.addWidget(self.enter_btn)

        self.guest_btn = QPushButton('GUEST')
        self.guest_btn.setObjectName('guest')
        self.guest_btn.clicked.connect(self.enter_guest)
        btns.addWidget(self.guest_btn)

        layout.addLayout(btns)

        self.hint = QLabel("(demo credentials: eleven / 0119)")
        self.hint.setObjectName('hint')
        self.hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.hint)

    def attempt_login(self):
        username = self.user.text().strip()
        password = self.pwd.text().strip()
        if not username or not password:
            self.shake('Please enter username and password')
            return

        if check_credentials(username, password):
            self.login_success.emit()
        else:
            self.shake('ACCESS DENIED')

    def enter_guest(self):
        # guest just lets in with limited UI; for now identical flow
        self.login_success.emit()

    def shake(self, message: str):
        # quick visual feedback via messagebox + brief UI flicker
        dialog = QMessageBox(self)
        dialog.setWindowTitle('Login')
        dialog.setText(message)
        dialog.setIcon(QMessageBox.Warning)
        dialog.exec()

    def login_styles(self):
        return '''
        QWidget#login_widget { background: rgba(0,0,0,0.35); border-radius: 12px; }
        #login_title { color: #ff2d2d; font-size: 42px; font-weight: bold; letter-spacing: 6px; }
        QLineEdit#user, QLineEdit#pwd { background: rgba(255,255,255,0.03); border: 1px solid #3a0b0b; padding: 10px; border-radius: 8px; color: #f2f2f2; }
        QPushButton#guest { background: transparent; border: 1px solid #6b0000; padding: 10px; border-radius: 8px; color: #f2f2f2; }
        QLabel#hint { color: #d7a6a6; font-size: 11px; }
        '''


# ----------------------------- Main Retro UI -----------------------------

class RetroMain(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName('main_widget')
        self.setStyleSheet(self.main_styles())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)

        title = FlickerLabel('STRANGER THINGS')
        title.setObjectName('title')
        title.setAlignment(Qt.AlignCenter)
        title.setFixedHeight(110)
        layout.addWidget(title)

        main = QHBoxLayout()

        left = QVBoxLayout()
        left.setSpacing(10)

        begin_btn = PulsingButton('BEGIN')
        begin_btn.setObjectName('begin')
        begin_btn.clicked.connect(lambda: self.console_set('Adventure begins...'))
        left.addWidget(begin_btn)

        explore_btn = QPushButton('EXPLORE')
        explore_btn.setObjectName('explore')
        explore_btn.clicked.connect(lambda: self.console_set('You explore Hawkins...'))
        left.addWidget(explore_btn)

        left.addStretch()
        main.addLayout(left, 2)

        right = QVBoxLayout()
        right.setSpacing(8)

        characters_label = QLabel('Hawkins')
        characters_label.setObjectName('side_title')
        right.addWidget(characters_label)

        self.char_list = QListWidget()
        for name in ['Eleven', 'Mike', 'Dustin', 'Lucas', 'Will', 'Joyce', 'Hopper']:
            item = QListWidgetItem(name)
            self.char_list.addItem(item)
        self.char_list.setObjectName('char_list')
        right.addWidget(self.char_list)

        self.console = QLabel('Welcome to Hawkins. The Upside Down waits...')
        self.console.setObjectName('console')
        self.console.setWordWrap(True)
        self.console.setFixedHeight(110)
        right.addWidget(self.console)

        main.addLayout(right, 3)

        layout.addLayout(main)

        footer = QLabel('— A themed UI for fans —')
        footer.setObjectName('footer')
        footer.setAlignment(Qt.AlignCenter)
        layout.addWidget(footer)

        # ambient updates
        self.ambient_timer = QTimer(self)
        self.ambient_timer.timeout.connect(self.ambient_update)
        self.ambient_timer.start(4500)

    def ambient_update(self):
        messages = [
            'Static whispers from the Upside Down...',
            'Faint synth in the distance — you feel a chill.',
            'The lights flicker. Eleven is watching.',
            'A bicycle rolls by on a lonely street.',
            'Radio static: ---..---..---'
        ]
        idx = int(time.time()) % len(messages)
        self.console.setText(messages[idx])

    def console_set(self, text: str):
        self.console.setText(text)

    def main_styles(self):
        return '''
        QWidget#main_widget { background: transparent; }
        #title { color: #ff2d2d; font-size: 48px; font-weight: bold; letter-spacing: 6px; }
        QPushButton#explore { background: transparent; border: 1px solid #6b0000; padding: 10px; border-radius: 8px; }
        #side_title { color: #ff7b7b; font-weight: bold; margin-bottom: 6px; }
        QListWidget#char_list { background: rgba(0,0,0,0.45); border: 1px solid #2a0a0a; padding: 6px; }
        #console { background: rgba(8,8,8,0.35); border: 1px solid #2a0a0a; padding: 8px; border-radius: 6px; font-family: monospace; }
        #footer { color: #bfbfbf; font-size: 11px; }
        '''


# ----------------------------- App Container -----------------------------

class AppContainer(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Stranger Things — Login Portal')
        self.setMinimumSize(920, 600)

        # try load optional font
        font_family = load_font_if_present('PressStart2P.ttf')
        if font_family:
            app_font = QFont(font_family)
            app_font.setPointSize(10)
            QApplication.instance().setFont(app_font)

        # background image via stylesheet (user must provide file)
        self.setStyleSheet(self.app_styles())

        self.stack = QStackedLayout(self)

        self.login = LoginWidget()
        self.main_ui = RetroMain()

        self.login.login_success.connect(self.show_main)

        container_widget = QWidget()
        container_layout = QVBoxLayout(container_widget)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addLayout(self.stack)

        self.stack.addWidget(self.login)
        self.stack.addWidget(self.main_ui)

        # overlay flicker label to keep theme consistent
        self.overlay_flicker = FlickerLabel('')
        self.overlay_flicker.setVisible(False)

    def show_main(self):
        self.stack.setCurrentWidget(self.main_ui)

    def app_styles(self):
        return '''
        QWidget { background-image: url('stranger_bg.jpg'); background-repeat: no-repeat; background-position: center; background-attachment: fixed; background-size: cover; color: #eaeaea; }
        '''


# ----------------------------- Authentication --------------------------------

def check_credentials(username: str, password: str) -> bool:
    """Placeholder local credential check.
    Replace this with your server-side authentication as needed.
    """
    demo_user = 'eleven'
    demo_pass = '0119'
    return (username == demo_user and password == demo_pass)


# ----------------------------- Main -------------------------------------

if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = AppContainer()
    w.show()
    sys.exit(app.exec())
