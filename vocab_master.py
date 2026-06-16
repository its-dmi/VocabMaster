"""
VocabMaster - AI-Powered Vocabulary Learning App
Uses Groq API to teach words contextually and test understanding.
Includes word history (SQLite) and a Big Test unlocked after 10 words.
"""

import sys
import json
import re
import random
import sqlite3
import os
import requests  # Native HTTP requests for universal API calls
from datetime import datetime
import keyboard
import pyperclip
import time

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFrame, QStackedWidget,
    QRadioButton, QButtonGroup, QScrollArea, QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import (
    QFont, QColor, QLinearGradient, QPainter, QBrush
)

# ── CONFIG ────────────────────────────────────────────────────────────────────
BIG_TEST_UNLOCK = 10   # words needed to unlock the Big Test
DB_PATH         = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vocab_history.db")
# ─────────────────────────────────────────────────────────────────────────────

PALETTE = {
    "bg":        "#0F1117",
    "surface":   "#1A1D2E",
    "card":      "#22263A",
    "accent":    "#7C6AF7",
    "accent2":   "#5BBFFA",
    "success":   "#4ECCA3",
    "danger":    "#FF6B9D",
    "warning":   "#FFD166",
    "gold":      "#FFC857",
    "text":      "#E8EAF6",
    "subtext":   "#8B90B0",
    "border":    "#2E3356",
}

STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {PALETTE['bg']};
    color: {PALETTE['text']};
    font-family: 'Segoe UI', Arial, sans-serif;
}}
QLineEdit {{
    background-color: {PALETTE['card']};
    border: 2px solid {PALETTE['border']};
    border-radius: 12px;
    padding: 14px 20px;
    font-size: 16px;
    color: {PALETTE['text']};
    selection-background-color: {PALETTE['accent']};
}}
QLineEdit:focus {{
    border-color: {PALETTE['accent']};
}}
QPushButton {{
    border-radius: 12px;
    padding: 14px 28px;
    font-size: 15px;
    font-weight: 600;
    border: none;
}}
QPushButton#primary {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {PALETTE['accent']}, stop:1 #9B8BFF);
    color: white;
}}
QPushButton#primary:hover {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #8D7FFF, stop:1 #AFA0FF);
}}
QPushButton#primary:disabled {{
    background: {PALETTE['border']};
    color: {PALETTE['subtext']};
}}
QPushButton#secondary {{
    background-color: {PALETTE['card']};
    color: {PALETTE['accent']};
    border: 2px solid {PALETTE['accent']};
}}
QPushButton#secondary:hover {{
    background-color: {PALETTE['accent']};
    color: white;
}}
QPushButton#gold {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {PALETTE['gold']}, stop:1 #FFB347);
    color: #1A1D2E;
    font-weight: 700;
}}
QPushButton#gold:hover {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #FFD580, stop:1 #FFC04D);
}}
QPushButton#gold:disabled {{
    background: {PALETTE['border']};
    color: {PALETTE['subtext']};
}}
QScrollArea, QScrollBar {{
    background-color: transparent;
    border: none;
}}
QScrollBar:vertical {{
    width: 6px;
    background: {PALETTE['surface']};
    border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background: {PALETTE['border']};
    border-radius: 3px;
    min-height: 40px;
}}
QRadioButton {{
    font-size: 14px;
    color: {PALETTE['text']};
    spacing: 10px;
    padding: 4px;
}}
QRadioButton::indicator {{
    width: 18px; height: 18px;
    border-radius: 9px;
    border: 2px solid {PALETTE['border']};
    background: {PALETTE['card']};
}}
QRadioButton::indicator:checked {{
    border-color: {PALETTE['accent']};
    background: {PALETTE['accent']};
}}
"""

class HotkeyThread(QThread):
    word_captured = pyqtSignal(str)

    def run(self):
        # Hotkey callback
        def on_activate():
            keyboard.send('ctrl+c')
            time.sleep(0.1)  # Brief pause to let OS update the clipboard
            text = pyperclip.paste().strip()
            # Basic validation to ensure it's a single word (or short phrase)
            if text and len(text.split()) <= 3:
                self.word_captured.emit(text)

        # Register hotkey
        keyboard.add_hotkey('ctrl+shift+l', on_activate)
        keyboard.wait() # Keeps the thread alive

# ── DATABASE ──────────────────────────────────────────────────────────────────

def db_connect():
    conn = sqlite3.connect(DB_PATH)
    # Existing words table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS words (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            word        TEXT UNIQUE NOT NULL,
            pos         TEXT,
            definition  TEXT,
            situation   TEXT,
            sentences   TEXT,
            memory_tip  TEXT,
            learned_at  TEXT
        )
    """)
    # New settings table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    return conn

def db_get_setting(key, default=""):
    conn = db_connect()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default
    finally:
        conn.close()

def db_save_setting(key, value):
    conn = db_connect()
    try:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
    finally:
        conn.close()

def db_save_word(data: dict):
    conn = db_connect()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO words
                (word, pos, definition, situation, sentences, memory_tip, learned_at)
            VALUES (?,?,?,?,?,?,?)
        """, (
            data.get("word", "").lower(),
            data.get("pos", ""),
            data.get("definition", ""),
            data.get("situation", ""),
            json.dumps(data.get("sentences", [])),
            data.get("memory_tip", ""),
            datetime.now().isoformat(),
        ))
        conn.commit()
    finally:
        conn.close()

def db_get_all_words() -> list:
    conn = db_connect()
    try:
        rows = conn.execute(
            "SELECT word, pos, definition, sentences FROM words ORDER BY learned_at DESC"
        ).fetchall()
        return [
            {
                "word":      r[0],
                "pos":       r[1],
                "definition": r[2],
                "sentences": json.loads(r[3]) if r[3] else [],
            }
            for r in rows
        ]
    finally:
        conn.close()

def db_word_count() -> int:
    conn = db_connect()
    try:
        return conn.execute("SELECT COUNT(*) FROM words").fetchone()[0]
    finally:
        conn.close()


# ── HELPERS ───────────────────────────────────────────────────────────────────
def card_shadow():
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(24)
    shadow.setColor(QColor(0, 0, 0, 100))
    shadow.setOffset(0, 4)
    return shadow


class Card(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {PALETTE['card']};
                border-radius: 18px;
                border: 1px solid {PALETTE['border']};
            }}
        """)
        self.setGraphicsEffect(card_shadow())


class GradientHeader(QWidget):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.text = text
        self.setFixedHeight(70)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        grad = QLinearGradient(0, 0, self.width(), 0)
        grad.setColorAt(0, QColor(PALETTE['accent']))
        grad.setColorAt(1, QColor(PALETTE['accent2']))
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 14, 14)
        painter.setPen(QColor("white"))
        painter.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text)

class ApiConfigBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {PALETTE['card']};
                border-bottom: 1px solid {PALETTE['border']};
            }}
            QLabel {{ font-size: 13px; font-weight: bold; color: {PALETTE['subtext']}; }}
        """)
        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 10, 20, 10)

        # Toggle Button (The Drop-down Header)
        self.toggle_btn = QPushButton("⚙️  API Configuration  ▼")
        self.toggle_btn.setStyleSheet(f"""
            text-align: left; 
            background: transparent; 
            border: none; 
            color: {PALETTE['accent2']};
            font-size: 14px;
            font-weight: bold;
        """)
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.clicked.connect(self._toggle)
        self.main_layout.addWidget(self.toggle_btn)

        # Form Container (Hidden by default)
        self.form_widget = QWidget()
        form_layout = QHBoxLayout(self.form_widget)
        form_layout.setContentsMargins(0, 10, 0, 0)
        form_layout.setSpacing(10)

        # Endpoint URL
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("e.g., https://api.groq.com/openai/v1/chat/completions")
        self.url_input.setToolTip("Use any OpenAI-compatible endpoint (Groq, OpenRouter, LM Studio, etc.)")
        
        # Model
        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("e.g., llama-3.3-70b-versatile")
        
        # API Key (Password Masked)
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("Your API Key")
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)

        # Save Button
        self.save_btn = QPushButton("Save & Hide")
        self.save_btn.setObjectName("secondary")
        self.save_btn.clicked.connect(self._save)

        form_layout.addWidget(QLabel("Endpoint:"))
        form_layout.addWidget(self.url_input, 3)
        form_layout.addWidget(QLabel("Model:"))
        form_layout.addWidget(self.model_input, 2)
        form_layout.addWidget(QLabel("Key:"))
        form_layout.addWidget(self.key_input, 2)
        form_layout.addWidget(self.save_btn)

        self.main_layout.addWidget(self.form_widget)
        self.is_expanded = False
        self.form_widget.hide()

    def _load_settings(self):
        # Defaults to Groq's OpenAI-compatible endpoint if completely empty
        url = db_get_setting("api_url", "https://api.groq.com/openai/v1/chat/completions")
        model = db_get_setting("api_model", "llama-3.3-70b-versatile")
        key = db_get_setting("api_key", "")

        self.url_input.setText(url)
        self.model_input.setText(model)
        self.key_input.setText(key)

        # If no key exists on boot, force expand the config bar
        if not key:
            self._expand()

    def _toggle(self):
        if self.is_expanded:
            self._collapse()
        else:
            self._expand()

    def _expand(self):
        self.form_widget.show()
        self.toggle_btn.setText("⚙️  API Configuration  ▲")
        self.is_expanded = True

    def _collapse(self):
        self.form_widget.hide()
        self.toggle_btn.setText("⚙️  API Configuration  ▼")
        self.is_expanded = False

    def _save(self):
        db_save_setting("api_url", self.url_input.text().strip())
        db_save_setting("api_model", self.model_input.text().strip())
        db_save_setting("api_key", self.key_input.text().strip())
        self._collapse()

# ── WORKER THREAD ─────────────────────────────────────────────────────────────

class WorkerThread(QThread):
    result_ready   = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, word, mode="learn"):
        super().__init__()
        self.word = word
        self.mode = mode

    def run(self):
        try:
            # 1. Pull dynamic settings from SQLite
            api_url = db_get_setting("api_url", "https://api.groq.com/openai/v1/chat/completions")
            api_model = db_get_setting("api_model", "llama-3.3-70b-versatile")
            api_key = db_get_setting("api_key", "")

            if not api_key and "localhost" not in api_url and "127.0.0.1" not in api_url:
                self.error_occurred.emit("Please enter your API Key in the settings bar above.")
                return

            if self.mode == "learn":
                prompt = f"""You are a vocabulary teacher. The user entered "{self.word}". 
1. If misspelled, CORRECT IT. Use the correctly spelled word for the response.
2. Provide a clear definition.
3. Part of speech.
4. A memorable real-life situation/story.
5. 2 example sentences within that story.

Respond ONLY with valid JSON format:
{{
  "word": "TheCorrectWord",
  "pos": "part of speech",
  "definition": "definition",
  "situation": "story",
  "sentences": ["sentence one", "sentence two"]
}}"""
            else:
                prompt = f"""Create a vocabulary quiz for the word "{self.word}".

Make 3 questions that test UNDERSTANDING and USAGE (not just definition recall):
- Q1: Fill-in-the-blank (give a sentence with ___ where the word should go)
- Q2: Multiple choice — which sentence uses "{self.word}" correctly? (4 options, only 1 correct)
- Q3: Scenario — describe a brief situation, ask if "{self.word}" applies (Yes/No with brief why)

Respond ONLY with valid JSON:
{{
  "questions": [
    {{
      "type": "fill_blank",
      "question": "Fill in the blank: sentence with ___",
      "answer": "{self.word}",
      "hint": "brief grammatical hint"
    }},
    {{
      "type": "multiple_choice",
      "question": "Which sentence uses '{self.word}' correctly?",
      "options": ["option A", "option B", "option C", "option D"],
      "correct": 0,
      "explanation": "why this is correct"
    }},
    {{
      "type": "scenario",
      "question": "Scenario description — would you use '{self.word}' here?",
      "answer": "Yes/No",
      "explanation": "brief explanation"
    }}
  ]
}}"""

            # 2. Universal OpenAI-compatible HTTP Request
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": api_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                # Force JSON output (Supported by most modern APIs)
                "response_format": {"type": "json_object"} 
            }

            response = requests.post(api_url, headers=headers, json=payload, timeout=30)
            
            # Catch HTTP errors (e.g., 401 Unauthorized, 404 Not Found)
            if response.status_code != 200:
                err_msg = response.json().get('error', {}).get('message', 'Unknown API Error')
                self.error_occurred.emit(f"API Error ({response.status_code}): {err_msg}")
                return

            # Parse universal response format
            data = response.json()
            raw = data['choices'][0]['message']['content'].strip()
            
            match = re.search(r'\{[\s\S]*\}', raw)
            if match:
                parsed_data = json.loads(match.group())
                self.result_ready.emit(parsed_data)
            else:
                self.error_occurred.emit("Could not parse AI response. Please try again.")

        except requests.exceptions.RequestException as e:
            self.error_occurred.emit(f"Network error: Check your Endpoint URL or connection. ({e})")
        except Exception as e:
            self.error_occurred.emit(f"System Error: {str(e)}")

# ── BIG TEST WORKER ───────────────────────────────────────────────────────────

class BigTestWorker(QThread):
    result_ready   = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, words):
        super().__init__()
        self.words = words

    def run(self):
        try:
            # 1. Fetch the universal configuration from SQLite settings
            api_url = db_get_setting("api_url", "https://api.groq.com/openai/v1/chat/completions")
            api_model = db_get_setting("api_model", "llama-3.3-70b-versatile")
            api_key = db_get_setting("api_key", "")

            # Prevent empty API key errors unless targeting a local address
            if not api_key and "localhost" not in api_url and "127.0.0.1" not in api_url:
                self.error_occurred.emit("Please enter your API Key in the settings bar above.")
                return

            # 2. Build the original test generation prompt
            words_str = ", ".join(self.words)
            prompt = f"""Create a vocabulary test with one question per word listed below. The test must genuinely assess whether the student understands each word's meaning and usage — not whether they memorized a definition.

Words to test: {words_str}

For each word, create ONE question. Vary the question types across words:

1. "fill_blank": A sentence or short paragraph with ___ where the word belongs. Answer is the word itself. Do NOT name the word in the question — the student must guess it from context.

2. "multiple_choice": "Which sentence uses the word correctly?" with 4 answer options. Include "options" (list of 4 strings) and "correct" (0-based index of the right answer).

3. "scenario": A brief real-world situation. Ask "Does the word apply here?" Answer is "Yes" or "No".

Every question must include an "explanation" field that teaches the student WHY the answer is right or wrong.

Respond ONLY with valid JSON array — no commentary:
[
  {{
    "word": "word1",
    "type": "fill_blank",
    "question": "The scientist gave an ___ explanation that made everything clear.",
    "answer": "lucid",
    "explanation": "Lucid means clear and easy to understand."
  }},
  {{
    "word": "word2",
    "type": "multiple_choice",
    "question": "Which sentence uses 'ephemeral' correctly?",
    "options": ["The ephemeral building stood for centuries.", "The ephemeral beauty of the sunset lasted only moments.", "He gave an ephemeral speech that lasted three hours.", "The ephemeral rock formation was made of solid granite."],
    "correct": 1,
    "explanation": "Ephemeral means lasting a very short time. Only the sunset sentence fits."
  }},
  {{
    "word": "word3",
    "type": "scenario",
    "question": "Your friend spends hours carefully planning a party, but it rains and only two people show up. Would you describe the outcome as 'debacle'?",
    "answer": "Yes",
    "explanation": "A debacle is a complete failure or fiasco. A party that flops despite careful planning fits."
  }}
]"""

            # 3. Formulate the universal OpenAI-compatible payload structure
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": api_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7
                # Note: We omit response_format here because some models fail json_object matching when requested to return a root array [] instead of a root object {}
            }

            # 4. Fire the HTTP request (giving it a slightly longer 60s timeout since generating full tests takes time)
            response = requests.post(api_url, headers=headers, json=payload, timeout=60)
            
            if response.status_code != 200:
                try:
                    err_msg = response.json().get('error', {}).get('message', 'Unknown API Error')
                except Exception:
                    err_msg = response.text[:200]
                self.error_occurred.emit(f"API Error ({response.status_code}): {err_msg}")
                return

            # 5. Extract and parse the payload text safely via regex matching
            data = response.json()
            raw = data['choices'][0]['message']['content'].strip()
            
            match = re.search(r'\[[\s\S]*\]', raw)
            if match:
                parsed_data = json.loads(match.group())
                if isinstance(parsed_data, list):
                    self.result_ready.emit(parsed_data)
                    return
                    
            self.error_occurred.emit("Could not parse AI response into a valid question list.")

        except requests.exceptions.RequestException as e:
            self.error_occurred.emit(f"Network error: Check your Endpoint URL or connection. ({e})")
        except Exception as e:
            self.error_occurred.emit(f"System Error: {str(e)}")

# ── LEARNING PAGE ─────────────────────────────────────────────────────────────

class LearningPage(QWidget):
    quiz_requested     = pyqtSignal(str, dict)
    big_test_requested = pyqtSignal()
    word_learned       = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_word = ""
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(16)

        # Search row + Big Test button
        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        search_card = Card()
        search_layout = QHBoxLayout(search_card)
        search_layout.setContentsMargins(20, 12, 20, 12)
        search_layout.setSpacing(12)

        emoji_lbl = QLabel("🔍")
        emoji_lbl.setFont(QFont("Segoe UI", 16))
        emoji_lbl.setStyleSheet("background: transparent; border: none;")
        search_layout.addWidget(emoji_lbl)

        self.word_input = QLineEdit()
        self.word_input.setPlaceholderText("Enter a word to learn…")
        self.word_input.returnPressed.connect(self._on_search)
        search_layout.addWidget(self.word_input)

        self.search_btn = QPushButton("  Learn  ")
        self.search_btn.setObjectName("primary")
        self.search_btn.setMinimumWidth(100)
        self.search_btn.clicked.connect(self._on_search)
        search_layout.addWidget(self.search_btn)

        top_row.addWidget(search_card, 1)

        self.big_test_btn = QPushButton("🏆  Big Test")
        self.big_test_btn.setObjectName("gold")
        self.big_test_btn.setMinimumWidth(130)
        self.big_test_btn.setMinimumHeight(54)
        self.big_test_btn.setToolTip(f"Unlocked after learning {BIG_TEST_UNLOCK} words")
        self.big_test_btn.clicked.connect(self.big_test_requested.emit)
        top_row.addWidget(self.big_test_btn)

        layout.addLayout(top_row)

        # Progress line
        self.prog_label = QLabel()
        self.prog_label.setFont(QFont("Segoe UI", 12))
        layout.addWidget(self.prog_label)

        # Status
        self.status_label = QLabel("Type a word and press Enter or click Learn")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet(f"color: {PALETTE['subtext']}; font-size: 13px;")
        layout.addWidget(self.status_label)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setSpacing(16)
        self.content_layout.addStretch()
        scroll.setWidget(self.content_widget)
        layout.addWidget(scroll, 1)

        self.refresh_progress()

    def refresh_progress(self):
        count     = db_word_count()
        remaining = max(0, BIG_TEST_UNLOCK - count)
        if count >= BIG_TEST_UNLOCK:
            self.prog_label.setText(f"📚  {count} words learned  ·  Big Test unlocked! 🔓")
            self.prog_label.setStyleSheet(f"color: {PALETTE['gold']}; font-weight: 600;")
            self.big_test_btn.setEnabled(True)
        else:
            self.prog_label.setText(
                f"📚  {count} / {BIG_TEST_UNLOCK} words learned  ·  "
                f"{remaining} more to unlock the Big Test 🔒"
            )
            self.prog_label.setStyleSheet(f"color: {PALETTE['subtext']};")
            self.big_test_btn.setEnabled(False)

    def _on_search(self):
        word = self.word_input.text().strip()
        if not word:
            return
            
        # 1. Caching Check: Look in DB first
        all_words = db_get_all_words()
        for w in all_words:
            if w["word"].lower() == word.lower():
                self._current_word = w["word"]
                self.status_label.setText("Loaded from local memory.")
                self._clear_content()
                self._render_word_ui(w) # Abstracted the UI rendering to a new method
                return

        # 2. If not in DB, proceed to AI
        self._current_word = word
        self.search_btn.setEnabled(False)
        self.status_label.setText(f"✨ Asking AI about '{word}'…")
        self._clear_content()

        self.worker = WorkerThread(word, mode="learn")
        self.worker.result_ready.connect(self._on_learn_result)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.start()

    def _clear_content(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_learn_result(self, data):
        self.search_btn.setEnabled(True)
        self.status_label.setText("")
        self._clear_content()

        db_save_word(data)
        self.word_learned.emit()
        self.refresh_progress()

        # Title card
        title_card = Card()
        tc_layout = QVBoxLayout(title_card)
        tc_layout.setContentsMargins(24, 20, 24, 20)
        tc_layout.setSpacing(6)

        word_lbl = QLabel(data.get("word", self._current_word).upper())
        word_lbl.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
        word_lbl.setStyleSheet(f"color: {PALETTE['accent']}; background: transparent; border: none;")
        tc_layout.addWidget(word_lbl)

        pos_lbl = QLabel(data.get("pos", ""))
        pos_lbl.setFont(QFont("Segoe UI", 13))
        pos_lbl.setStyleSheet(
            f"color: {PALETTE['accent2']}; background: transparent; border: none; font-style: italic;"
        )
        tc_layout.addWidget(pos_lbl)
        self.content_layout.addWidget(title_card)

        self._add_section_card("📖  Definition",          data.get("definition", ""), PALETTE['accent'])
        self._add_section_card("🎬  Real-Life Situation", data.get("situation",   ""), PALETTE['accent2'])

        sentences = data.get("sentences", [])
        if sentences:
            ex_card = Card()
            ex_layout = QVBoxLayout(ex_card)
            ex_layout.setContentsMargins(24, 20, 24, 20)
            ex_layout.setSpacing(10)

            hdr = QLabel("✏️  Example Sentences")
            hdr.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
            hdr.setStyleSheet(f"color: {PALETTE['success']}; background: transparent; border: none;")
            ex_layout.addWidget(hdr)

            for i, s in enumerate(sentences):
                s_fmt = re.sub(r'\*(.+?)\*', r'<b style="color:#7C6AF7">\1</b>', s)
                lbl = QLabel(
                    f"<span style='color:{PALETTE['subtext']}'>{i+1}.</span>  {s_fmt}"
                )
                lbl.setFont(QFont("Segoe UI", 14))
                lbl.setWordWrap(True)
                lbl.setStyleSheet(
                    f"background: transparent; border: none; color: {PALETTE['text']};"
                )
                lbl.setTextFormat(Qt.TextFormat.RichText)
                ex_layout.addWidget(lbl)
            self.content_layout.addWidget(ex_card)

        quiz_btn = QPushButton("  Take the Word Quiz  →")
        quiz_btn.setObjectName("primary")
        quiz_btn.setMinimumHeight(52)
        quiz_btn.clicked.connect(lambda: self.quiz_requested.emit(self._current_word, data))
        self.content_layout.addWidget(quiz_btn)
        self.content_layout.addStretch()

    def _add_section_card(self, title, text, color):
        card = Card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(24, 18, 24, 18)
        cl.setSpacing(8)

        hdr = QLabel(title)
        hdr.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {color}; background: transparent; border: none;")
        cl.addWidget(hdr)

        body = QLabel(text)
        body.setFont(QFont("Segoe UI", 14))
        body.setWordWrap(True)
        body.setStyleSheet(f"color: {PALETTE['text']}; background: transparent; border: none;")
        cl.addWidget(body)
        self.content_layout.addWidget(card)

    def _on_error(self, msg):
        self.search_btn.setEnabled(True)
        self.status_label.setText(f"⚠️  Error: {msg}")
        self.status_label.setStyleSheet(f"color: {PALETTE['danger']}; font-size: 13px;")


# ── WORD QUIZ PAGE ────────────────────────────────────────────────────────────

class QuizPage(QWidget):
    back_requested     = pyqtSignal()
    new_word_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._questions = []
        self._current_q = 0
        self._score     = 0
        self._word      = ""
        self._btn_group = None
        self._build_ui()

    def _build_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(32, 24, 32, 24)
        self.main_layout.setSpacing(16)

        hdr_row = QHBoxLayout()
        back_btn = QPushButton("← Back")
        back_btn.setObjectName("secondary")
        back_btn.setMaximumWidth(100)
        back_btn.clicked.connect(self.back_requested.emit)
        hdr_row.addWidget(back_btn)
        hdr_row.addStretch()

        self.quiz_title = QLabel("Quiz")
        self.quiz_title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        self.quiz_title.setStyleSheet(f"color: {PALETTE['accent']};")
        hdr_row.addWidget(self.quiz_title)
        hdr_row.addStretch()

        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet(f"color: {PALETTE['subtext']}; font-size: 13px;")
        hdr_row.addWidget(self.progress_label)
        self.main_layout.addLayout(hdr_row)

        self.loading_label = QLabel("⏳  Generating quiz questions…")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setFont(QFont("Segoe UI", 15))
        self.loading_label.setStyleSheet(f"color: {PALETTE['subtext']};")
        self.main_layout.addWidget(self.loading_label)

        # Question card
        self.q_card = Card()
        self.q_card.hide()
        q_layout = QVBoxLayout(self.q_card)
        q_layout.setContentsMargins(28, 24, 28, 24)
        q_layout.setSpacing(14)

        self.q_type_label = QLabel()
        self.q_type_label.setFont(QFont("Segoe UI", 11))
        self.q_type_label.setStyleSheet(
            f"color: {PALETTE['subtext']}; background: transparent; border: none;"
        )
        q_layout.addWidget(self.q_type_label)

        self.q_text = QLabel()
        self.q_text.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.q_text.setWordWrap(True)
        self.q_text.setStyleSheet(
            f"color: {PALETTE['text']}; background: transparent; border: none;"
        )
        q_layout.addWidget(self.q_text)

        self.fill_input = QLineEdit()
        self.fill_input.setPlaceholderText("Type your answer…")
        self.fill_input.hide()
        q_layout.addWidget(self.fill_input)

        self.options_widget = QWidget()
        self.options_widget.setStyleSheet("background: transparent;")
        self.options_layout = QVBoxLayout(self.options_widget)
        self.options_layout.setSpacing(8)
        self.options_layout.setContentsMargins(0, 0, 0, 0)
        self.options_widget.hide()
        q_layout.addWidget(self.options_widget)

        self.hint_label = QLabel()
        self.hint_label.setFont(QFont("Segoe UI", 12))
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet(
            f"color: {PALETTE['subtext']}; font-style: italic; background: transparent; border: none;"
        )
        self.hint_label.hide()
        q_layout.addWidget(self.hint_label)

        self.feedback_label = QLabel()
        self.feedback_label.setFont(QFont("Segoe UI", 13))
        self.feedback_label.setWordWrap(True)
        self.feedback_label.setStyleSheet("background: transparent; border: none;")
        self.feedback_label.hide()
        q_layout.addWidget(self.feedback_label)

        self.submit_btn = QPushButton("Submit Answer")
        self.submit_btn.setObjectName("primary")
        self.submit_btn.setMinimumHeight(48)
        self.submit_btn.clicked.connect(self._check_answer)
        q_layout.addWidget(self.submit_btn)

        self.next_btn = QPushButton("Next Question →")
        self.next_btn.setObjectName("secondary")
        self.next_btn.setMinimumHeight(48)
        self.next_btn.hide()
        self.next_btn.clicked.connect(self._next_question)
        q_layout.addWidget(self.next_btn)

        self.main_layout.addWidget(self.q_card, 1)

        # Results card
        self.result_card = Card()
        self.result_card.hide()
        r_layout = QVBoxLayout(self.result_card)
        r_layout.setContentsMargins(32, 32, 32, 32)
        r_layout.setSpacing(16)
        r_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.score_emoji = QLabel("🎉")
        self.score_emoji.setFont(QFont("Segoe UI", 48))
        self.score_emoji.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.score_emoji.setStyleSheet("background: transparent; border: none;")
        r_layout.addWidget(self.score_emoji)

        self.score_label = QLabel()
        self.score_label.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        self.score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.score_label.setStyleSheet(
            f"color: {PALETTE['accent']}; background: transparent; border: none;"
        )
        r_layout.addWidget(self.score_label)

        self.score_msg = QLabel()
        self.score_msg.setFont(QFont("Segoe UI", 14))
        self.score_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.score_msg.setWordWrap(True)
        self.score_msg.setStyleSheet(
            f"color: {PALETTE['subtext']}; background: transparent; border: none;"
        )
        r_layout.addWidget(self.score_msg)

        btn_row = QHBoxLayout()
        retry_btn = QPushButton("🔄  Retry Quiz")
        retry_btn.setObjectName("secondary")
        retry_btn.clicked.connect(self._retry)
        btn_row.addWidget(retry_btn)

        new_word_btn = QPushButton("📚  New Word")
        new_word_btn.setObjectName("primary")
        new_word_btn.clicked.connect(self.new_word_requested.emit)
        btn_row.addWidget(new_word_btn)
        r_layout.addLayout(btn_row)

        self.main_layout.addWidget(self.result_card, 1)

    def load_quiz(self, word, learn_data):
        self._word      = word
        self._score     = 0
        self._current_q = 0
        self.quiz_title.setText(f"Quiz: {word.upper()}")
        self.q_card.hide()
        self.result_card.hide()
        self.loading_label.show()

        self.worker = WorkerThread(word, mode="quiz")
        self.worker.result_ready.connect(self._on_quiz_ready)
        self.worker.error_occurred.connect(self._on_quiz_error)
        self.worker.start()

    def _on_quiz_ready(self, data):
        self._questions = data.get("questions", [])
        self.loading_label.hide()
        if self._questions:
            self._show_question(0)
        else:
            self.loading_label.setText("⚠️  No questions received. Please go back and try again.")
            self.loading_label.show()

    def _on_quiz_error(self, msg):
        self.loading_label.setText(f"⚠️  {msg}")
        self.loading_label.show()

    def _show_question(self, idx):
        q = self._questions[idx]
        self.progress_label.setText(f"Q {idx+1} of {len(self._questions)}")
        self.feedback_label.hide()
        self.next_btn.hide()
        self.submit_btn.show()
        self.submit_btn.setEnabled(True)

        qtype = q.get("type", "")
        self.q_type_label.setText({
            "fill_blank":      "📝  Fill in the Blank",
            "multiple_choice": "🔘  Multiple Choice",
            "scenario":        "🧠  Scenario",
        }.get(qtype, "Question"))
        self.q_text.setText(q.get("question", ""))

        self.fill_input.hide()
        self.fill_input.clear()
        self.fill_input.setEnabled(True)
        self.options_widget.hide()
        self.hint_label.hide()

        while self.options_layout.count():
            item = self.options_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if qtype == "fill_blank":
            self.fill_input.show()
            if hint := q.get("hint", ""):
                self.hint_label.setText(f"Hint: {hint}")
                self.hint_label.show()

        elif qtype == "multiple_choice":
            self._btn_group = QButtonGroup(self)
            for i, opt in enumerate(q.get("options", [])):
                rb = QRadioButton(f"  {opt}")
                rb.setFont(QFont("Segoe UI", 13))
                self._btn_group.addButton(rb, i)
                frame = QFrame()
                frame.setStyleSheet(f"""
                    QFrame {{
                        background-color: {PALETTE['surface']};
                        border-radius: 10px;
                        border: 1px solid {PALETTE['border']};
                    }}
                """)
                fl = QHBoxLayout(frame)
                fl.setContentsMargins(10, 6, 10, 6)
                fl.addWidget(rb)
                self.options_layout.addWidget(frame)
            self.options_widget.show()

        elif qtype == "scenario":
            self._btn_group = QButtonGroup(self)
            for i, opt in enumerate(["✅  Yes", "❌  No"]):
                rb = QRadioButton(opt)
                rb.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
                self._btn_group.addButton(rb, i)
                self.options_layout.addWidget(rb)
            self.options_widget.show()

        self.q_card.show()

    def _check_answer(self):
        q     = self._questions[self._current_q]
        qtype = q.get("type", "")
        correct     = False
        explanation = q.get("explanation", "")

        if qtype == "fill_blank":
            user_ans    = self.fill_input.text().strip().lower()
            correct_ans = q.get("answer", "").strip().lower()
            correct     = user_ans == correct_ans
            explanation = explanation or f"The correct answer is: \"{q.get('answer', '')}\""

        elif qtype == "multiple_choice":
            btn = self._btn_group.checkedButton()
            if not btn:
                self._show_warn("⚠️  Please select an option first.")
                return
            correct = self._btn_group.id(btn) == q.get("correct", 0)

        elif qtype == "scenario":
            btn = self._btn_group.checkedButton()
            if not btn:
                self._show_warn("⚠️  Please select Yes or No first.")
                return
            user_ans = "yes" if self._btn_group.id(btn) == 0 else "no"
            correct  = user_ans.lower() == q.get("answer", "").lower()

        if correct:
            self._score += 1
            self.feedback_label.setStyleSheet(
                f"color: {PALETTE['success']}; background: transparent; border: none;"
            )
            self.feedback_label.setText(f"✅  Correct!  {explanation}")
        else:
            self.feedback_label.setStyleSheet(
                f"color: {PALETTE['danger']}; background: transparent; border: none;"
            )
            self.feedback_label.setText(f"❌  Not quite.  {explanation}")

        self.feedback_label.show()
        self.submit_btn.hide()
        self.fill_input.setEnabled(False)
        self.next_btn.setText(
            "Next Question →" if self._current_q < len(self._questions) - 1 else "See Results 🏆"
        )
        self.next_btn.show()

    def _show_warn(self, msg):
        self.feedback_label.setText(msg)
        self.feedback_label.setStyleSheet(
            f"color: {PALETTE['warning']}; background: transparent; border: none;"
        )
        self.feedback_label.show()

    def _next_question(self):
        self._current_q += 1
        if self._current_q < len(self._questions):
            self._show_question(self._current_q)
        else:
            self._show_results()

    def _show_results(self):
        self.q_card.hide()
        total = len(self._questions)
        pct   = int(self._score / total * 100)
        if pct == 100:
            emoji, msg = "🏆", "Perfect score! You've truly mastered this word."
        elif pct >= 66:
            emoji, msg = "⭐", "Great job! Just a bit more practice and you'll own it."
        else:
            emoji, msg = "💪", "Keep going — review the word and try again!"

        self.score_emoji.setText(emoji)
        self.score_label.setText(f"{self._score} / {total}  ({pct}%)")
        self.score_msg.setText(msg)
        self.progress_label.setText("")
        self.result_card.show()

    def _retry(self):
        self._score = 0
        self._current_q = 0
        self.result_card.hide()
        self._show_question(0)


# ── BIG TEST PAGE ─────────────────────────────────────────────────────────────

class BigTestPage(QWidget):
    """
    AI-generated vocabulary test across the entire word bank.
    Each word gets a fresh question testing real understanding:
    fill-in-the-blank (guess from context), multiple choice (correct usage),
    or scenario (does the word apply?).
    """
    back_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._questions = []
        self._current_q = 0
        self._score     = 0
        self._btn_group = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(16)

        # Header
        hdr_row = QHBoxLayout()
        back_btn = QPushButton("← Back")
        back_btn.setObjectName("secondary")
        back_btn.setMaximumWidth(100)
        back_btn.clicked.connect(self.back_requested.emit)
        hdr_row.addWidget(back_btn)
        hdr_row.addStretch()

        title = QLabel("🏆  Big Vocab Test")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {PALETTE['gold']};")
        hdr_row.addWidget(title)
        hdr_row.addStretch()

        self.progress_lbl = QLabel("")
        self.progress_lbl.setStyleSheet(f"color: {PALETTE['subtext']}; font-size: 13px;")
        hdr_row.addWidget(self.progress_lbl)
        layout.addLayout(hdr_row)

        # ── Intro card ──
        self.intro_card = Card()
        intro_lay = QVBoxLayout(self.intro_card)
        intro_lay.setContentsMargins(32, 28, 32, 28)
        intro_lay.setSpacing(16)
        intro_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        crown = QLabel("🧠")
        crown.setFont(QFont("Segoe UI", 52))
        crown.setAlignment(Qt.AlignmentFlag.AlignCenter)
        crown.setStyleSheet("background: transparent; border: none;")
        intro_lay.addWidget(crown)

        self.intro_count_lbl = QLabel()
        self.intro_count_lbl.setFont(QFont("Segoe UI", 17, QFont.Weight.Bold))
        self.intro_count_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.intro_count_lbl.setStyleSheet(
            f"color: {PALETTE['text']}; background: transparent; border: none;"
        )
        intro_lay.addWidget(self.intro_count_lbl)

        sub = QLabel(
            "AI will create one fresh question per word — fill-in-the-blank,\n"
            "correct-usage multiple choice, or real-world scenarios.\n"
            "No definitions. No shortcuts. Real understanding."
        )
        sub.setFont(QFont("Segoe UI", 13))
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color: {PALETTE['subtext']}; background: transparent; border: none;")
        intro_lay.addWidget(sub)

        self.loading_lbl = QLabel("")
        self.loading_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_lbl.setFont(QFont("Segoe UI", 14))
        self.loading_lbl.setStyleSheet(f"color: {PALETTE['subtext']}; background: transparent; border: none;")
        self.loading_lbl.hide()
        intro_lay.addWidget(self.loading_lbl)

        # Container for the chunked test buttons
        self.test_list_widget = QWidget()
        self.test_list_widget.setStyleSheet("background: transparent;")
        self.test_list_layout = QVBoxLayout(self.test_list_widget)
        self.test_list_layout.setSpacing(10)
        intro_lay.addWidget(self.test_list_widget)

        layout.addWidget(self.intro_card, 1)

        # ── Question card ──
        self.q_card = Card()
        self.q_card.hide()
        q_lay = QVBoxLayout(self.q_card)
        q_lay.setContentsMargins(28, 24, 28, 24)
        q_lay.setSpacing(14)

        self.q_type_label = QLabel()
        self.q_type_label.setFont(QFont("Segoe UI", 11))
        self.q_type_label.setStyleSheet(
            f"color: {PALETTE['subtext']}; background: transparent; border: none;"
        )
        q_lay.addWidget(self.q_type_label)

        self.word_label = QLabel()
        self.word_label.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.word_label.setStyleSheet(
            f"color: {PALETTE['accent']}; background: transparent; border: none;"
        )
        q_lay.addWidget(self.word_label)

        self.question_lbl = QLabel()
        self.question_lbl.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.question_lbl.setWordWrap(True)
        self.question_lbl.setStyleSheet(
            f"color: {PALETTE['text']}; background: transparent; border: none;"
        )
        q_lay.addWidget(self.question_lbl)

        self.fill_input = QLineEdit()
        self.fill_input.setPlaceholderText("Type the missing word…")
        self.fill_input.hide()
        q_lay.addWidget(self.fill_input)

        self.options_widget = QWidget()
        self.options_widget.setStyleSheet("background: transparent;")
        self.options_layout = QVBoxLayout(self.options_widget)
        self.options_layout.setSpacing(10)
        self.options_layout.setContentsMargins(0, 4, 0, 0)
        self.options_widget.hide()
        q_lay.addWidget(self.options_widget)

        self.feedback_lbl = QLabel()
        self.feedback_lbl.setFont(QFont("Segoe UI", 13))
        self.feedback_lbl.setWordWrap(True)
        self.feedback_lbl.setStyleSheet("background: transparent; border: none;")
        self.feedback_lbl.hide()
        q_lay.addWidget(self.feedback_lbl)

        self.submit_btn = QPushButton("Submit Answer")
        self.submit_btn.setObjectName("primary")
        self.submit_btn.setMinimumHeight(48)
        self.submit_btn.clicked.connect(self._check_answer)
        q_lay.addWidget(self.submit_btn)

        self.next_btn = QPushButton("Next →")
        self.next_btn.setObjectName("secondary")
        self.next_btn.setMinimumHeight(46)
        self.next_btn.hide()
        self.next_btn.clicked.connect(self._next_question)
        q_lay.addWidget(self.next_btn)

        layout.addWidget(self.q_card, 1)

        # ── Results card ──
        self.result_card = Card()
        self.result_card.hide()
        r_lay = QVBoxLayout(self.result_card)
        r_lay.setContentsMargins(32, 32, 32, 32)
        r_lay.setSpacing(16)
        r_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.res_emoji = QLabel()
        self.res_emoji.setFont(QFont("Segoe UI", 52))
        self.res_emoji.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.res_emoji.setStyleSheet("background: transparent; border: none;")
        r_lay.addWidget(self.res_emoji)

        self.res_score_lbl = QLabel()
        self.res_score_lbl.setFont(QFont("Segoe UI", 26, QFont.Weight.Bold))
        self.res_score_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.res_score_lbl.setStyleSheet(
            f"color: {PALETTE['gold']}; background: transparent; border: none;"
        )
        r_lay.addWidget(self.res_score_lbl)

        self.res_msg = QLabel()
        self.res_msg.setFont(QFont("Segoe UI", 14))
        self.res_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.res_msg.setWordWrap(True)
        self.res_msg.setStyleSheet(
            f"color: {PALETTE['subtext']}; background: transparent; border: none;"
        )
        r_lay.addWidget(self.res_msg)

        rb_row = QHBoxLayout()
        retry_btn = QPushButton("🔄  New Test")
        retry_btn.setObjectName("secondary")
        retry_btn.clicked.connect(self._start_test)
        rb_row.addWidget(retry_btn)

        back_home = QPushButton("🏠  Back to Learning")
        back_home.setObjectName("primary")
        back_home.clicked.connect(self.back_requested.emit)
        rb_row.addWidget(back_home)
        r_lay.addLayout(rb_row)

        layout.addWidget(self.result_card, 1)

    # ── logic ─────────────────────────────────────────────────────────────────

    def prepare(self):
        count = db_word_count()
        self.intro_count_lbl.setText(
            f"You've learned {count} word{'s' if count != 1 else ''} — let's test real understanding!"
        )
        self.intro_card.show()
        self.q_card.hide()
        self.result_card.hide()
        self.progress_lbl.setText("")
        self.loading_lbl.hide()
        
        # Clear old buttons before generating new ones
        while self.test_list_layout.count():
            item = self.test_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        self.test_list_widget.show()
        self._generate_test_list()

    def _generate_test_list(self):
        all_words = [w["word"] for w in db_get_all_words()]
        # Chunk into groups of 10
        chunks = [all_words[i:i + 10] for i in range(0, len(all_words), 10)]
        
        # Generate UI Buttons for each test block
        for i, chunk in enumerate(chunks):
            if len(chunk) == 10:
                btn = QPushButton(f"Practice Test {i+1}  (Words {i*10 + 1} - {(i+1)*10})")
                btn.setObjectName("secondary")
                btn.setMinimumHeight(48)
                btn.clicked.connect(lambda checked, c=chunk: self._start_specific_test(c))
                self.test_list_layout.addWidget(btn)
            else:
                # Incomplete chunk (less than 10 words)
                lbl = QLabel(f"🔒 Learn {10 - len(chunk)} more words to unlock Test {i+1}")
                lbl.setFont(QFont("Segoe UI", 12))
                lbl.setStyleSheet(f"color: {PALETTE['subtext']}; margin-top: 10px;")
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.test_list_layout.addWidget(lbl)

    def _start_specific_test(self, chunk_words):
        self._current_q = 0
        self._score     = 0
        
        # Hide the list and show loading text
        self.test_list_widget.hide()
        self.loading_lbl.setText(f"🧠  Generating {len(chunk_words)} customized questions via AI…")
        self.loading_lbl.show()
        self.q_card.hide()
        self.result_card.hide()

        # Send only the 10 words to the AI worker
        self.worker = BigTestWorker(chunk_words)
        self.worker.result_ready.connect(self._on_questions_ready)
        self.worker.error_occurred.connect(self._on_test_error)
        self.worker.start()

    def _on_questions_ready(self, questions):
        self._questions = questions
        self.loading_lbl.hide()
        self.intro_card.hide()
        if self._questions:
            self._show_question(0)
        else:
            self.loading_lbl.setText("⚠️  No questions received. Please try again.")
            self.loading_lbl.show()
            self.start_btn.show()

    def _on_test_error(self, msg):
        self.loading_lbl.setText(f"⚠️  {msg}")
        self.loading_lbl.show()
        self.start_btn.show()

    def _show_question(self, idx):
        q = self._questions[idx]
        self.progress_lbl.setText(f"Q {idx+1} of {len(self._questions)}")
        self.feedback_lbl.hide()
        self.next_btn.hide()
        self.submit_btn.show()
        self.submit_btn.setEnabled(True)

        qtype = q.get("type", "")
        word  = q.get("word", "")
        self.q_type_label.setText({
            "fill_blank":      "📝  Guess the Word from Context",
            "multiple_choice": "🔘  Which Sentence Uses It Correctly?",
            "scenario":        "🧠  Does the Word Apply?",
        }.get(qtype, "Question"))

        if qtype == "fill_blank":
            self.word_label.setText("Word: ???")
            self.word_label.setStyleSheet(
                f"color: {PALETTE['danger']}; background: transparent; border: none; font-size: 15px;"
            )
        else:
            self.word_label.setText(f"Word: {word}")
            self.word_label.setStyleSheet(
                f"color: {PALETTE['accent']}; background: transparent; border: none; font-size: 15px;"
            )

        self.question_lbl.setText(q.get("question", ""))

        self.fill_input.hide()
        self.fill_input.clear()
        self.fill_input.setEnabled(True)
        self.options_widget.hide()

        while self.options_layout.count():
            item = self.options_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if qtype == "fill_blank":
            self.fill_input.show()

        elif qtype == "multiple_choice":
            self._btn_group = QButtonGroup(self)
            for i, opt in enumerate(q.get("options", [])):
                rb = QRadioButton(f"  {opt}")
                rb.setFont(QFont("Segoe UI", 13))
                self._btn_group.addButton(rb, i)
                frame = QFrame()
                frame.setStyleSheet(f"""
                    QFrame {{
                        background-color: {PALETTE['surface']};
                        border-radius: 10px;
                        border: 1px solid {PALETTE['border']};
                    }}
                """)
                fl = QHBoxLayout(frame)
                fl.setContentsMargins(10, 6, 10, 6)
                fl.addWidget(rb)
                self.options_layout.addWidget(frame)
            self.options_widget.show()

        elif qtype == "scenario":
            self._btn_group = QButtonGroup(self)
            for i, opt in enumerate(["✅  Yes", "❌  No"]):
                rb = QRadioButton(opt)
                rb.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
                self._btn_group.addButton(rb, i)
                self.options_layout.addWidget(rb)
            self.options_widget.show()

        self.q_card.show()

    def _check_answer(self):
        q     = self._questions[self._current_q]
        qtype = q.get("type", "")
        correct     = False
        explanation = q.get("explanation", "")

        if qtype == "fill_blank":
            user_ans    = self.fill_input.text().strip().lower()
            correct_ans = q.get("answer", "").strip().lower()
            correct     = user_ans == correct_ans

        elif qtype == "multiple_choice":
            btn = self._btn_group.checkedButton()
            if not btn:
                self._show_warn("⚠️  Please select an option first.")
                return
            correct = self._btn_group.id(btn) == q.get("correct", 0)

        elif qtype == "scenario":
            btn = self._btn_group.checkedButton()
            if not btn:
                self._show_warn("⚠️  Please select Yes or No first.")
                return
            user_ans = "yes" if self._btn_group.id(btn) == 0 else "no"
            correct  = user_ans.lower() == q.get("answer", "").lower()

        if correct:
            self._score += 1
            self.feedback_lbl.setStyleSheet(
                f"color: {PALETTE['success']}; background: transparent; border: none;"
            )
            self.feedback_lbl.setText(f"✅  Correct!  {explanation}")
        else:
            self.feedback_lbl.setStyleSheet(
                f"color: {PALETTE['danger']}; background: transparent; border: none;"
            )
            self.feedback_lbl.setText(f"❌  Not quite.  {explanation}")

        self.feedback_lbl.show()
        self.submit_btn.hide()
        if qtype == "fill_blank":
            self.fill_input.setEnabled(False)
        else:
            for b in self._btn_group.buttons():
                b.setEnabled(False)

        self.next_btn.setText(
            "Next →" if self._current_q < len(self._questions) - 1 else "See Final Results 🏆"
        )
        self.next_btn.show()

    def _show_warn(self, msg):
        self.feedback_lbl.setText(msg)
        self.feedback_lbl.setStyleSheet(
            f"color: {PALETTE['warning']}; background: transparent; border: none;"
        )
        self.feedback_lbl.show()

    def _next_question(self):
        self._current_q += 1
        if self._current_q < len(self._questions):
            self._show_question(self._current_q)
        else:
            self._show_results()

    def _show_results(self):
        self.q_card.hide()
        total = len(self._questions)
        pct   = int(self._score / total * 100)

        if pct == 100:
            emoji, msg = "🏆", "PERFECT! You genuinely know every word. Incredible!"
        elif pct >= 80:
            emoji, msg = "🥇", "Excellent! Your vocabulary is really solid."
        elif pct >= 60:
            emoji, msg = "⭐", "Good effort! Review the ones you missed and try again."
        else:
            emoji, msg = "📖", "Time to revisit your word list — you'll get there!"

        self.res_emoji.setText(emoji)
        self.res_score_lbl.setText(f"{self._score} / {total}  ({pct}%)")
        self.res_msg.setText(msg)
        self.progress_lbl.setText("")
        self.result_card.show()


# ── MAIN WINDOW ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VocabMaster  ·  AI-Powered Vocabulary Learning")
        self.setMinimumSize(760, 660)
        self.resize(860, 720)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Add Universal API Config Bar
        self.config_bar = ApiConfigBar()
        main_layout.addWidget(self.config_bar)

        # 2. Add Existing Gradient Header
        main_layout.addWidget(GradientHeader("📚  VocabMaster"))

        # 3. Add Existing Stack Layout...
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack, 1)

        # Build Sidebar
        sidebar = QFrame()
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet(f"background-color: {PALETTE['surface']}; border-right: 1px solid {PALETTE['border']};")
        sidebar_layout = QVBoxLayout(sidebar)
        
        logo = QLabel("📚 VocabMaster")
        logo.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        sidebar_layout.addWidget(logo)
        
        self.nav_learn = QPushButton("Learn Words")
        self.nav_list = QPushButton("My Word List")
        self.nav_tests = QPushButton("Practice Tests")
        
        # Style buttons to look sleek and flat
        for btn in [self.nav_learn, self.nav_list, self.nav_tests]:
            btn.setStyleSheet(f"text-align: left; padding: 10px; background: transparent; border: none; color: {PALETTE['text']}; font-size: 14px;")
            sidebar_layout.addWidget(btn)
        
        sidebar_layout.addStretch()
        main_layout.addWidget(sidebar)

        # Stacked Widget for Pages
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack, 1)
        self.learn_page    = LearningPage()
        self.quiz_page     = QuizPage()
        self.big_test_page = BigTestPage()

        self.stack.addWidget(self.learn_page)       # 0
        self.stack.addWidget(self.quiz_page)        # 1
        self.stack.addWidget(self.big_test_page)    # 2

        self.learn_page.quiz_requested.connect(self._go_to_quiz)
        self.learn_page.big_test_requested.connect(self._go_to_big_test)
        self.learn_page.word_learned.connect(self.learn_page.refresh_progress)

        self.quiz_page.back_requested.connect(lambda: self.stack.setCurrentIndex(0))
        self.quiz_page.new_word_requested.connect(self._new_word)

        self.big_test_page.back_requested.connect(self._back_from_big_test)
        
        # Start the hotkey listener
        self.hotkey_thread = HotkeyThread()
        self.hotkey_thread.word_captured.connect(self._handle_global_hotkey)
        self.hotkey_thread.start()

    def _handle_global_hotkey(self, word):
        # Bring window to front
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.activateWindow()
        self.raise_()
        
        # Navigate to learning page and search
        self.stack.setCurrentIndex(0)
        self.learn_page.word_input.setText(word)
        self.learn_page._on_search()


    def _go_to_quiz(self, word, data):
        self.quiz_page.load_quiz(word, data)
        self.stack.setCurrentIndex(1)

    def _go_to_big_test(self):
        self.big_test_page.prepare()
        self.stack.setCurrentIndex(2)

    def _back_from_big_test(self):
        self.learn_page.refresh_progress()
        self.stack.setCurrentIndex(0)

    def _new_word(self):
        self.stack.setCurrentIndex(0)
        self.learn_page.word_input.setFocus()
        self.learn_page.word_input.selectAll()


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

def main():

    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()