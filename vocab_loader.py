import sys
import os
import requests
import hashlib
import runpy

# ── FORCE LOAD DEPENDENCIES ───────────────────────────────────────────────────
# We must actually import these (NO 'if False:') so they are loaded into 
# the frozen app's memory *before* runpy executes vocab_master.py.
import keyboard
import groq
import pyperclip
import sqlite3

from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QLabel, 
                             QProgressBar, QMainWindow, QHBoxLayout, 
                             QLineEdit, QPushButton, QFrame, QStackedWidget, 
                             QRadioButton, QButtonGroup, QScrollArea, 
                             QGraphicsDropShadowEffect)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QEventLoop
from PyQt6.QtGui import QFont, QColor, QLinearGradient, QPainter, QBrush

# ── UPDATE CONFIGURATION ──────────────────────────────────────────────────────
GITHUB_RAW_URL = "https://raw.githubusercontent.com/its-dmi/VocabMaster/main/vocab_master.py"
TARGET_FILENAME = "vocab_master.py"

# ── PERSISTENT PATH FIX ──
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

PALETTE = {
    "bg": "#0F1117",
    "surface": "#1A1D2E",
    "accent": "#7C6AF7",
    "text": "#E8EAF6",
    "subtext": "#8B90B0"
}

class UpdateWorker(QThread):
    status_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def run(self):
        # THE FIX: Use BASE_DIR here! This ensures it saves exactly next to the .exe
        local_path = os.path.join(BASE_DIR, TARGET_FILENAME)
        
        try:
            self.status_signal.emit("Checking for remote updates...")
            response = requests.get(GITHUB_RAW_URL, timeout=3)
            
            if response.status_code == 200:
                remote_code = response.content
                update_needed = True
                
                if os.path.exists(local_path):
                    with open(local_path, "rb") as f:
                        local_code = f.read()
                    if hashlib.md5(local_code).hexdigest() == hashlib.md5(remote_code).hexdigest():
                        update_needed = False
                
                if update_needed:
                    self.status_signal.emit("Downloading latest engine updates...")
                    with open(local_path, "wb") as f:
                        f.write(remote_code)
                    self.status_signal.emit("Update complete! Launching...")
                else:
                    self.status_signal.emit("App up to date! Loading environment...")
            else:
                self.status_signal.emit("Couldn't reach server. Loading offline engine...")
        except Exception:
            self.status_signal.emit("Offline mode. Loading local components...")
        
        self.msleep(600)
        self.finished_signal.emit()

class LoaderWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VocabMaster Bootloader")
        self.setFixedSize(420, 220)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet(f"background-color: {PALETTE['bg']}; border-radius: 16px;")
        self._build_ui()
        
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 40, 30, 40)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        title = QLabel("VocabMaster")
        title.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {PALETTE['text']};")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        self.status_lbl = QLabel("Initializing application layers...")
        self.status_lbl.setFont(QFont("Segoe UI", 11))
        self.status_lbl.setStyleSheet(f"color: {PALETTE['subtext']}; margin-top: 10px;")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_lbl)
        
        self.progress = QProgressBar()
        self.progress.setRange(0, 0) # Infinite busy state animation
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet(f"""
            QProgressBar {{
                background-color: {PALETTE['surface']};
                border: none;
                border-radius: 2px;
                margin-top: 20px;
            }}
            QProgressBar::chunk {{
                background-color: {PALETTE['accent']};
                border-radius: 2px;
            }}
        """)
        layout.addWidget(self.progress)
        
        self.worker = UpdateWorker()
        self.worker.status_signal.connect(self.status_lbl.setText)
        self.worker.finished_signal.connect(self._boot_app)
        self.worker.start()

    # Inside class LoaderWindow(QWidget):
    def _boot_app(self):
        # Only close the visual window. Do NOT call QApplication.quit() here!
        self.close()

def main():
    # ── PATH FIX FOR BUNDLED LIBS ──
    if getattr(sys, 'frozen', False):
        bundled_dir = sys._MEIPASS
        sys.path.append(bundled_dir)
        sys.path.append(os.path.dirname(sys.executable))
        
    app = QApplication(sys.argv)
    
    # Prevent the global app instance from dying when the loader closes
    app.setQuitOnLastWindowClosed(False) 
    
    loader = LoaderWindow()
    loader.show()
    
    # Run a temporary, local event loop just for the loading process
    loop = QEventLoop()
    loader.worker.finished_signal.connect(loop.quit)
    loop.exec() 

    # ── Safe to execute the main app out of the persistent path ──
    local_path = os.path.join(BASE_DIR, TARGET_FILENAME)
    
    if os.path.exists(local_path):
        # Restore normal Qt behavior so the main app can close properly later
        app.setQuitOnLastWindowClosed(True) 
        runpy.run_path(local_path, run_name="__main__")

if __name__ == "__main__":
    main()