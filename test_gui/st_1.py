"""
StrangerThings_GUI.py
Stranger Things–themed Python GUI using PySide6 with full hover effects.
"""

import sys
import time
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontDatabase, QFont, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
)


# --------------------------------------------------------
# CRT SCANLINE OVERLAY
# --------------------------------------------------------
class ScanlineOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.offset = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(55)

    def animate(self):
        self.offset = (self.offset + 1) % 8
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setOpacity(0.06)
        w = self.width()
        h = self.height()
        stripe_h = 4
        y = -self.offset
        pen = QPen(QColor(0, 0, 0))
        painter.setPen(pen)
        while y < h:
            painter.fillRect(0, y, w, stripe_h / 2, QColor(0, 0, 0))
            y += stripe_h
        painter.end()


# --------------------------------------------------------
# FLICKERING TITLE LABEL
# --------------------------------------------------------
class FlickerLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._opacity = 1.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(2000)
        self._flicker_timer = QTimer(self)
        self._flicker_timer.timeout.connect(self._flicker_step)
        self._flicker_step_count = 0

    def _tick(self):
        if (time.time() * 1000) % 7 < 1:
            self._flicker_step_count = 6
            self._flicker_timer.start(60)

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


# --------------------------------------------------------
# PULSING BUTTON WITH HOVER GLOW
# --------------------------------------------------------
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
        glow = 0.4 + self._pulse * 0.6
        self.setStyleSheet(self.style_template(glow))

    def style_template(self, glow):
        return f"""
        QPushButton {{
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                                        stop:0 rgba(255,75,75,{glow}),
                                        stop:1 rgba(155,0,0,{glow}));
            border: 2px solid rgba(255,0,0,{0.4 + glow * 0.5});
            padding: 14px 18px;
            border-radius: 10px;
            font-weight: bold;
            color: #fff;
            transition: all 140ms;
        }}

        QPushButton:hover {{
            border: 2px solid rgba(255,40,40,1);
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                                        stop:0 rgba(255,95,95,1),
                                        stop:1 rgba(180,0,0,1));
            transform: scale(1.06);
        }}

        QPushButton:pressed {{
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                                        stop:0 rgba(180,0,0,1),
                                        stop:1 rgba(120,0,0,1));
            transform: scale(0.94);
        }}
        """


# --------------------------------------------------------
# MAIN WINDOW
# --------------------------------------------------------
class RetroWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Stranger Things 5')
        self.setMinimumSize(920, 600)
        self.setStyleSheet(self.global_styles())

        self.load_optional_font('PressStart2P.ttf')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)

        title = FlickerLabel('STRANGER THINGS')
        title.setObjectName('title')
        title.setAlignment(Qt.AlignCenter)
        title.setFixedHeight(110)
        layout.addWidget(title)

        main = QHBoxLayout()

        # LEFT PANEL
        left = QVBoxLayout()
        left.setSpacing(10)

        start_btn = PulsingButton('BEGIN')
        start_btn.setObjectName('start_btn')
        start_btn.clicked.connect(self.on_start)
        left.addWidget(start_btn)

        explore_btn = QPushButton('EXPLORE')
        explore_btn.setObjectName('explore_btn')
        explore_btn.clicked.connect(self.on_explore)
        left.addWidget(explore_btn)

        left.addStretch()
        main.addLayout(left, 2)

        # RIGHT PANEL
        right = QVBoxLayout()
        right.setSpacing(8)

        characters_label = QLabel('Hawkins')
        characters_label.setObjectName('side_title')
        right.addWidget(characters_label)

        self.char_list = QListWidget()
        for name in ['Eleven', 'Mike', 'Dustin', 'Lucas', 'Will', 'Joyce', 'Hopper']:
            self.char_list.addItem(QListWidgetItem(name))
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

        self.overlay = ScanlineOverlay(self)
        self.overlay.raise_()

        self.ambient_timer = QTimer(self)
        self.ambient_timer.timeout.connect(self.ambient_update)
        self.ambient_timer.start(4500)

    # --------------------------------------------------------
    def load_optional_font(self, filename):
        if Path(filename).exists():
            _id = QFontDatabase.addApplicationFont(str(Path(filename).absolute()))
            families = QFontDatabase.applicationFontFamilies(_id)
            if families:
                f = QFont(families[0])
                f.setPointSize(16)
                self.setFont(f)

    # --------------------------------------------------------
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

    # --------------------------------------------------------
    def on_start(self):
        self.console.setText('You pressed BEGIN. Adventure mode engaged — lights dim, gates open...')

    def on_explore(self):
        sel = self.char_list.currentItem()
        name = sel.text() if sel else 'the town'
        self.console.setText(f'You explore {name}. Memories and secrets surface...')

    # --------------------------------------------------------
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.overlay.setGeometry(0, 0, self.width(), self.height())

    # --------------------------------------------------------
    def global_styles(self):
        return '''
        QWidget { 
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1, 
            stop:0 #060606, stop:1 #0b0b0b); 
            color: #eaeaea; 
        }

        #title { 
            color: #ff2d2d; 
            font-size: 48px; 
            font-weight: bold; 
            letter-spacing: 6px;  
            font-family: 'PressStart2P','Benguiat',serif; 
        }

        QPushButton#explore_btn { 
            background: transparent; 
            border: 1px solid #6b0000; 
            padding: 10px; 
            border-radius: 8px; 
            transition: 140ms;
            color: #ff9c9c;
        }

        QPushButton#explore_btn:hover {
            background: rgba(40,0,0,0.7);
            border: 1px solid #ff3d3d;
            color: white;
            transform: scale(1.06);
        }

        #side_title { 
            color: #ff7b7b; 
            font-weight: bold; 
            margin-bottom: 6px; 
        }

        QListWidget#char_list { 
            background: rgba(0,0,0,0.45); 
            border: 1px solid #2a0a0a; 
            padding: 6px; 
        }

        QListWidget#char_list::item {
            padding: 6px;
            color: #ffbcbc;
            border-radius: 6px;
            margin: 2px;
        }

        QListWidget#char_list::item:hover {
            background: rgba(80, 0, 0, 0.7);
            color: white;
            border: 1px solid #ff3d3d;
            padding-left: 10px;
            transition: 120ms;
        }

        QListWidget#char_list::item:selected {
            background: rgba(150, 0, 0, 0.9);
            color: white;
            border: 1px solid #ff0000;
        }

        #console { 
            background: rgba(8,8,8,0.35); 
            border: 1px solid #2a0a0a; 
            padding: 8px; 
            border-radius: 6px; 
            font-family: monospace; 
        }

        #footer { 
            color: #bfbfbf; 
            font-size: 11px; 
        }
        '''


# --------------------------------------------------------
# RUN
# --------------------------------------------------------
if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = RetroWindow()
    w.show()
    sys.exit(app.exec())
