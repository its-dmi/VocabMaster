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
from datetime import datetime
from groq import Groq
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
GROQ_API_KEY    = ""   # ← Replace with your key
GROQ_MODEL      = "openai/gpt-oss-120b"
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
    # <-- NEW: Settings table to hold the API key
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key         TEXT PRIMARY KEY,
            value       TEXT
        )
    """)
    conn.commit()
    return conn

def db_save_setting(key: str, value: str):
    conn = db_connect()
    try:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
    finally:
        conn.close()

def db_get_setting(key: str) -> str:
    conn = db_connect()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else ""
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
        # Added 'situation' to the SELECT statement
        rows = conn.execute(
            "SELECT word, pos, definition, situation, sentences FROM words ORDER BY learned_at DESC"
        ).fetchall()
        return [
            {
                "word":       r[0],
                "pos":        r[1],
                "definition": r[2],
                "situation":  r[3],  # <-- Now properly loading from DB!
                "sentences":  json.loads(r[4]) if r[4] else [],
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



# ── WORKER THREAD ─────────────────────────────────────────────────────────────

class WorkerThread(QThread):
    result_ready   = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, word):
        super().__init__()
        self.word = word

    def run(self):
        global GROQ_API_KEY
        if not GROQ_API_KEY:
            self.error_occurred.emit("Groq API key is missing. Please set it in the sidebar.")
            return
            
        try:
            client = Groq(api_key=GROQ_API_KEY)

            prompt = f"""You are a vocabulary teacher. The user entered "{self.word}". 
1. If the word is misspelled, CORRECT IT automatically. Use the correctly spelled word for the rest of the prompt.
2. Provide a clear, simple definition.
3. The part of speech.
4. A vivid, memorable real-life situation/story.
5. 2 example sentences within that story.

Respond ONLY with valid JSON. Do not include memory tips. Format:
{{
  "word": "TheCorrectlySpelledWord",
  "pos": "part of speech",
  "definition": "clear definition",
  "situation": "vivid story",
  "sentences": ["sentence one", "sentence two"]
}}"""

            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=1500,
            )

            raw = response.choices[0].message.content.strip()
            match = re.search(r'\{[\s\S]*\}', raw)
            if match:
                data = json.loads(match.group())
                self.result_ready.emit(data)
            else:
                self.error_occurred.emit("Could not parse AI response. Please try again.")

        except Exception as e:
            self.error_occurred.emit(str(e))

# ── BIG TEST WORKER ───────────────────────────────────────────────────────────

class BigTestWorker(QThread):
    result_ready   = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, words):
        super().__init__()
        self.words = words

    def run(self):
        global GROQ_API_KEY
        if not GROQ_API_KEY:
            self.error_occurred.emit("Groq API key is missing. Please set it in the sidebar.")
            return

        try:
            client = Groq(api_key=GROQ_API_KEY)
            words_str = ", ".join(self.words)
            prompt = f"""Create a strict vocabulary test for these words: {words_str}. 

CRITICAL RULES:
Assign each word randomly to one of two question types:
1. "guess_word": Provide a clear description/meaning of the word WITHOUT ever mentioning the word itself or its roots. The user must guess the word.
2. "make_sentence": Provide the word and its clear description/meaning. The user will be asked to write a sentence using it.

Respond ONLY with a valid JSON array:
[
  {{
    "word": "lucid",
    "type": "guess_word",
    "description": "Expressed clearly; easy to understand."
  }},
  {{
    "word": "ephemeral",
    "type": "make_sentence",
    "description": "Lasting for a very short time."
  }}
]"""

            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=4000,
            )

            raw = response.choices[0].message.content.strip()
            match = re.search(r'\[[\s\S]*\]', raw)
            if match:
                data = json.loads(match.group())
                if isinstance(data, list):
                    self.result_ready.emit(data)
                    return
            self.error_occurred.emit("Could not parse AI response. Please try again.")
        except Exception as e:
            self.error_occurred.emit(str(e))

class SentenceEvalWorker(QThread):
    result_ready   = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, word, sentence):
        super().__init__()
        self.word = word
        self.sentence = sentence

    def run(self):
        global GROQ_API_KEY
        if not GROQ_API_KEY:
            self.error_occurred.emit("Groq API key is missing.")
            return

        try:
            client = Groq(api_key=GROQ_API_KEY)
            prompt = f"""You are a strict vocabulary teacher. The student was asked to write a sentence using the word "{self.word}".
They wrote: "{self.sentence}"

Critically examine this sentence for:
1. Grammatical correctness.
2. Contextual accuracy of the word "{self.word}".
3. Is it an actual meaningful sentence (not just a fragment or gibberish)?

Respond ONLY with a valid JSON object:
{{
  "status": "pass" or "retry",
  "feedback": "Your clear, concise, critical feedback here.",
  "corrected": "The corrected/improved sentence here (leave empty if it was perfect)"
}}

RULES:
- Set "status" to "retry" ONLY if the sentence is gibberish, completely misuses the word, or isn't a proper sentence.
- Set "status" to "pass" if it demonstrates understanding, even if you need to provide minor grammar tweaks in the "corrected" field."""

            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=800,
            )

            raw = response.choices[0].message.content.strip()
            match = re.search(r'\{[\s\S]*\}', raw)
            if match:
                self.result_ready.emit(json.loads(match.group()))
            else:
                self.error_occurred.emit("Could not parse AI evaluation.")
        except Exception as e:
            self.error_occurred.emit(str(e))

# ── LEARNING PAGE ─────────────────────────────────────────────────────────────

class LearningPage(QWidget):
    big_test_requested = pyqtSignal()
    word_learned       = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_word = ""
        self._build_ui()

    def _render_word_ui(self, data):
        """Builds the visual card UI for a word, used by both local cache and AI results."""
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

        self.content_layout.addStretch()

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

        self.worker = WorkerThread(word)
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

        # Save to database and update progress
        db_save_word(data)
        self.word_learned.emit()
        self.refresh_progress()

        # Call the newly created UI renderer
        self._render_word_ui(data)

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
        back_btn.setMaximumWidth(120)
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

        # ── Preview card (Before Exam) ──
        self.preview_card = Card()
        self.preview_card.hide()
        prev_lay = QVBoxLayout(self.preview_card)
        prev_lay.setContentsMargins(32, 28, 32, 28)
        prev_lay.setSpacing(16)

        prev_title = QLabel("👀  Exam Preview")
        prev_title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        prev_title.setStyleSheet(f"color: {PALETTE['accent']}; background: transparent;")
        prev_lay.addWidget(prev_title)

        prev_sub = QLabel("Skim through the 10 words for this exam. Once you start, there's no going back!")
        prev_sub.setFont(QFont("Segoe UI", 12))
        prev_sub.setStyleSheet(f"color: {PALETTE['subtext']}; background: transparent;")
        prev_lay.addWidget(prev_sub)

        # Scrollable list for the 10 words
        self.prev_scroll = QScrollArea()
        self.prev_scroll.setWidgetResizable(True)
        self.prev_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.prev_content = QWidget()
        self.prev_content.setStyleSheet("background: transparent;")
        self.prev_layout = QVBoxLayout(self.prev_content)
        self.prev_layout.setSpacing(10)
        self.prev_scroll.setWidget(self.prev_content)
        prev_lay.addWidget(self.prev_scroll, 1)

        self.start_exam_btn = QPushButton("Start Exam 🚀")
        self.start_exam_btn.setObjectName("primary")
        self.start_exam_btn.setMinimumHeight(48)
        self.start_exam_btn.clicked.connect(self._start_ai_test)
        prev_lay.addWidget(self.start_exam_btn)

        layout.addWidget(self.preview_card, 1)

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
        retry_btn.clicked.connect(self.prepare)
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
        all_words = db_get_all_words() # Now passing the full dictionaries!
        chunks = [all_words[i:i + 10] for i in range(0, len(all_words), 10)]
        
        for i, chunk in enumerate(chunks):
            if len(chunk) == 10:
                btn = QPushButton(f"Practice Test {i+1}  (Words {i*10 + 1} - {(i+1)*10})")
                btn.setObjectName("secondary")
                btn.setMinimumHeight(48)
                btn.clicked.connect(lambda checked, c=chunk: self._show_preview(c))
                self.test_list_layout.addWidget(btn)
            else:
                lbl = QLabel(f"🔒 Learn {10 - len(chunk)} more words to unlock Test {i+1}")
                lbl.setFont(QFont("Segoe UI", 12))
                lbl.setStyleSheet(f"color: {PALETTE['subtext']}; margin-top: 10px;")
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.test_list_layout.addWidget(lbl)

    def _show_preview(self, chunk_dicts):
        """Shows the 10 words and definitions before the AI test starts."""
        self.test_list_widget.hide()
        self.intro_card.hide()
        
        # Save just the word strings to send to the AI later
        self._current_chunk_words = [w["word"] for w in chunk_dicts]
        
        # Clear old preview list
        while self.prev_layout.count():
            item = self.prev_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Populate preview list
        for w in chunk_dicts:
            lbl = QLabel(f"<b style='color:{PALETTE['accent']}'>{w['word'].capitalize()}</b> - {w.get('definition', '')}")
            lbl.setFont(QFont("Segoe UI", 13))
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color: {PALETTE['text']}; padding: 4px;")
            self.prev_layout.addWidget(lbl)

        self.prev_layout.addStretch()
        self.preview_card.show()

    def _start_ai_test(self):
        """Triggered when the user clicks 'Start Exam' from the preview."""
        self._current_q = 0
        self._score     = 0
        
        self.preview_card.hide()
        self.intro_card.show() # Show intro card to hold the loading label
        self.intro_count_lbl.hide() 
        
        self.loading_lbl.setText(f"🧠 Generating questions for these 10 words via AI...")
        self.loading_lbl.show()

        self.worker = BigTestWorker(self._current_chunk_words)
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
        self.submit_btn.setText("Submit Answer")

        qtype = q.get("type", "")
        word  = q.get("word", "")
        desc  = q.get("description", "")

        self.options_widget.hide() # We no longer use multiple choice
        self.fill_input.show()
        self.fill_input.setEnabled(True)
        self.fill_input.clear()
        
        # Reset any previous word label masking
        self.word_label.setText(f"Word: {word}")
        self.word_label.setStyleSheet(f"color: {PALETTE['accent']}; font-size: 15px;")

        if qtype == "guess_word":
            self.q_type_label.setText("📝  Read the meaning and guess the word")
            self.word_label.setText("Word: ???")
            self.word_label.setStyleSheet(f"color: {PALETTE['danger']}; font-size: 15px;")
            self.question_lbl.setText(f"Meaning: {desc}")
            self.fill_input.setPlaceholderText("Type the exact word...")
            
        elif qtype == "make_sentence":
            self.q_type_label.setText("✍️  Write a sentence using the word")
            self.question_lbl.setText(f"Meaning: {desc}\n\nWrite a full sentence using '{word}'.")
            self.fill_input.setPlaceholderText("Type your sentence here...")

        self.q_card.show()

    def _check_answer(self):
        q = self._questions[self._current_q]
        qtype = q.get("type", "")
        word = q.get("word", "")

        if qtype == "guess_word":
            user_ans = self.fill_input.text().strip().lower()
            correct_ans = word.strip().lower()
            
            if user_ans == correct_ans:
                self._score += 1
                self.feedback_lbl.setStyleSheet(f"color: {PALETTE['success']};")
                self.feedback_lbl.setText("✅  Correct!")
            else:
                self.feedback_lbl.setStyleSheet(f"color: {PALETTE['danger']};")
                self.feedback_lbl.setText(f"❌  Incorrect. The exact word was '{correct_ans}'.")
            
            self.feedback_lbl.show()
            self.fill_input.setEnabled(False)
            self.submit_btn.hide()
            self.next_btn.setText("Next →" if self._current_q < len(self._questions) - 1 else "See Final Results 🏆")
            self.next_btn.show()

        elif qtype == "make_sentence":
            sentence = self.fill_input.text().strip()
            words_in_sentence = [w for w in sentence.split() if w.strip()]

            # Validation Gate 1: Check if word exists
            if word.lower() not in sentence.lower():
                self._show_warn(f"⚠️ You must include the word '{word}' in your sentence!")
                return
            
            # Validation Gate 2: Check if it's more than just the word itself
            if len(words_in_sentence) <= 3:
                self._show_warn("⚠️ Please write a complete sentence, not just a few words.")
                return

            # Pass validations, send to AI evaluator
            self.submit_btn.setEnabled(False)
            self.submit_btn.setText("Evaluating via AI...")
            self.feedback_lbl.hide()

            self.eval_worker = SentenceEvalWorker(word, sentence)
            self.eval_worker.result_ready.connect(self._on_eval_ready)
            self.eval_worker.error_occurred.connect(self._on_eval_error)
            self.eval_worker.start()

    def _on_eval_ready(self, result):
        self.submit_btn.setText("Submit Answer")
        self.submit_btn.setEnabled(True)

        status = result.get("status", "retry")
        feedback = result.get("feedback", "")
        corrected = result.get("corrected", "")

        if status == "retry":
            self.feedback_lbl.setStyleSheet(f"color: {PALETTE['warning']};")
            self.feedback_lbl.setText(f"🔄 Please try again:\n{feedback}")
            self.feedback_lbl.show()
            # Note: We intentionally do NOT hide the submit button or increment the score here.
        else:
            self._score += 1
            self.feedback_lbl.setStyleSheet(f"color: {PALETTE['success']};")
            msg = f"✅ Good job!\nFeedback: {feedback}"
            if corrected:
                msg += f"\n\nCorrected version: {corrected}"
            self.feedback_lbl.setText(msg)
            self.feedback_lbl.show()

            self.fill_input.setEnabled(False)
            self.submit_btn.hide()
            self.next_btn.setText("Next →" if self._current_q < len(self._questions) - 1 else "See Final Results 🏆")
            self.next_btn.show()

    def _on_eval_error(self, err):
        self.submit_btn.setText("Submit Answer")
        self.submit_btn.setEnabled(True)
        self._show_warn(f"⚠️ AI Evaluation Error: {err}")

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

# ── WORD LIST PAGE ────────────────────────────────────────────────────────────

class WordListPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(16)

        title = QLabel("📖  My Word Library")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {PALETTE['accent']};")
        layout.addWidget(title)

        # Scrollable area for the list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setSpacing(12)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self.content_widget)
        
        layout.addWidget(scroll, 1)

    def load_words(self):
        # Clear existing items
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        words = db_get_all_words()
        
        if not words:
            empty_lbl = QLabel("No words learned yet. Go learn some!")
            empty_lbl.setStyleSheet(f"color: {PALETTE['subtext']}; font-size: 14px;")
            self.content_layout.addWidget(empty_lbl)
            return

        for w in words:
            card = Card()
            card.setMinimumHeight(80)
            card_lay = QHBoxLayout(card)
            card_lay.setContentsMargins(20, 15, 20, 15)
            
            word_lbl = QLabel(w["word"].capitalize())
            word_lbl.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
            word_lbl.setStyleSheet(f"color: {PALETTE['text']}; background: transparent; border: none;")
            
            pos_lbl = QLabel(w.get("pos", ""))
            pos_lbl.setFont(QFont("Segoe UI", 11))
            pos_lbl.setStyleSheet(f"color: {PALETTE['subtext']}; font-style: italic; background: transparent; border: none;")
            
            def_lbl = QLabel(w.get("definition", ""))
            def_lbl.setFont(QFont("Segoe UI", 12))
            def_lbl.setStyleSheet(f"color: {PALETTE['text']}; background: transparent; border: none;")
            def_lbl.setWordWrap(True)
            
            left_lay = QVBoxLayout()
            left_lay.addWidget(word_lbl)
            left_lay.addWidget(pos_lbl)
            
            card_lay.addLayout(left_lay, 1)
            card_lay.addWidget(def_lbl, 3)
            
            self.content_layout.addWidget(card)

# ── MAIN WINDOW ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VocabMaster  ·  AI-Powered Vocabulary Learning")
        self.setMinimumSize(800, 660)
        self.resize(950, 720)

        central = QWidget()
        self.setCentralWidget(central)
        
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Sidebar Setup ──
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(220)
        self.sidebar.setStyleSheet(f"background-color: {PALETTE['surface']}; border-right: 1px solid {PALETTE['border']};")
        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(0, 20, 0, 20)
        self.sidebar_layout.setSpacing(10)
        # NOTE: Explicit Alignment Flag removed here so the stretch spacer below can work!

        self.logo = QPushButton("📚 VocabMaster")
        self.logo.setFont(QFont("Segoe UI", 30, QFont.Weight.Bold))
        self.logo.setStyleSheet(f"color: {PALETTE['text']}; margin-bottom: 20px;")
        self.sidebar_layout.addWidget(self.logo)
        self.logo.clicked.connect(self._hide_sidebar)
        # Create Sidebar Buttons with Icons
        self.nav_learn = QPushButton("🔍  Learn Words")
        self.nav_list  = QPushButton("📖  My Word List")
        self.nav_tests = QPushButton("🏆  Practice Tests")
        
        # Add Navigation Buttons to Sidebar Layout (They stay at the top)
        for btn in [self.nav_learn, self.nav_list, self.nav_tests]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.sidebar_layout.addWidget(btn)
            
        # This stretch expands dynamically, forcing nav buttons UP and API controls DOWN
        self.sidebar_layout.addStretch()

        # ── API Key Input Section ── (Stays at the absolute bottom)
        self.api_toggle_btn = QPushButton("🔑  Set Groq API Key")
        self.api_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.api_toggle_btn.setStyleSheet(f"""
            text-align: left; padding: 12px 16px; background: transparent; 
            border: none; color: {PALETTE['warning']}; font-size: 14px; font-weight: 600;
        """)
        self.api_toggle_btn.clicked.connect(self._toggle_api_input)
        self.sidebar_layout.addWidget(self.api_toggle_btn)

        self.api_input_widget = QWidget()
        input_lay = QVBoxLayout(self.api_input_widget)
        input_lay.setContentsMargins(10, 0, 10, 0)
        input_lay.setSpacing(8)

        self.api_input = QLineEdit()
        self.api_input.setPlaceholderText("Enter Groq API Key...")
        self.api_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_input.setStyleSheet(f"background-color: {PALETTE['bg']}; border-radius: 6px; padding: 8px; font-size: 12px;")
        
        self.api_save_btn = QPushButton("Save Key")
        self.api_save_btn.setObjectName("secondary")
        self.api_save_btn.setStyleSheet(f"padding: 8px; font-size: 12px; border-radius: 6px;")
        self.api_save_btn.clicked.connect(self._save_api_key)

        self.show_sidebar_btn = QPushButton("☰")
        self.show_sidebar_btn.setFixedSize(64, 64)
        self.show_sidebar_btn.setStyleSheet(f"""
            QPushButton {{
                padding: 0px;
                border-radius: 8px;
                background-color: {PALETTE['surface']};
                border: 1px solid {PALETTE['border']};
                color: {PALETTE['text']};
                font-weight: bold;
                font-size: 16px;
                margin-left: 8px;
                margin-top: 20px;
            }}
            QPushButton:hover {{
                background-color: {PALETTE['card']};
                border-color: {PALETTE['accent']};
            }}
        """)
        self.show_sidebar_btn.clicked.connect(self._show_sidebar)
        self.show_sidebar_btn.hide() # Hidden by default
        
        # We align it to the Top-Left of the main layout so it sits exactly where the sidebar was
        main_layout.addWidget(self.show_sidebar_btn, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        input_lay.addWidget(self.api_input)
        input_lay.addWidget(self.api_save_btn)
        
        self.api_input_widget.hide() # Hidden by default
        self.sidebar_layout.addWidget(self.api_input_widget)

        global GROQ_API_KEY
        saved_key = db_get_setting("groq_api_key")
        if saved_key:
            GROQ_API_KEY = saved_key
            self.api_toggle_btn.setText("🔑  Update API Key")
            self.api_toggle_btn.setStyleSheet(f"""
                text-align: left; padding: 12px 16px; background: transparent; 
                border: none; color: {PALETTE['success']}; font-size: 14px; font-weight: 600;
            """)

        main_layout.addWidget(self.sidebar)

        # ── Stacked Widget & Pages Setup ──
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack, 1)

        # Initialize Pages
        self.learn_page     = LearningPage()
        self.word_list_page = WordListPage()  # The new page we just added
        self.big_test_page  = BigTestPage()

        # Add to Stack
        self.stack.addWidget(self.learn_page)       # Index 0
        self.stack.addWidget(self.word_list_page)   # Index 1
        self.stack.addWidget(self.big_test_page)    # Index 2

        # ── Connect Sidebar Buttons ──
        self.nav_learn.clicked.connect(lambda: self._switch_page(0))
        self.nav_list.clicked.connect(lambda: self._switch_page(1))
        self.nav_tests.clicked.connect(lambda: self._switch_page(2))

        # ── Connect Internal Page Signals ──
        self.learn_page.big_test_requested.connect(lambda: self._switch_page(2))
        self.learn_page.word_learned.connect(self.learn_page.refresh_progress)

        self.big_test_page.back_requested.connect(lambda: self._switch_page(0))
        
        # Start hotkey listener
        self.hotkey_thread = HotkeyThread()
        self.hotkey_thread.word_captured.connect(self._handle_global_hotkey)
        self.hotkey_thread.start()

        # Set Initial Page
        self._switch_page(0)

    def _hide_sidebar(self):
        self.sidebar.hide()
        self.show_sidebar_btn.show()

    def _show_sidebar(self):
        self.sidebar.show()
        self.show_sidebar_btn.hide()

    def _toggle_api_input(self):
        """Shows or hides the API key input bar underneath the button."""
        self.api_input_widget.setVisible(not self.api_input_widget.isVisible())
        if self.api_input_widget.isVisible():
            self.api_input.setFocus()
            
    def _save_api_key(self):
        """Saves the inputted key globally, to the database, and updates the button aesthetic."""
        global GROQ_API_KEY
        key = self.api_input.text().strip()
        if key:
            GROQ_API_KEY = key
            db_save_setting("groq_api_key", key) # <-- Save to SQLite
            
            self.api_toggle_btn.setText("🔑  Update API Key")
            self.api_toggle_btn.setStyleSheet(f"""
                text-align: left; padding: 12px 16px; background: transparent; 
                border: none; color: {PALETTE['success']}; font-size: 14px; font-weight: 600;
            """)
            self.api_input_widget.hide()

    def _switch_page(self, index):
        """Handles routing and updates sidebar button styles for aesthetic feedback."""
        self.stack.setCurrentIndex(index)
        
        # Base style for inactive buttons
        base_style = f"""
            text-align: left; 
            padding: 12px 16px; 
            background: transparent; 
            border: none; 
            color: {PALETTE['subtext']}; 
            font-size: 15px; 
            font-weight: 600; 
            border-radius: 8px;
        """
        
        # Highlight style for the active button
        active_style = f"""
            text-align: left; 
            padding: 12px 16px; 
            background: {PALETTE['card']}; 
            border: none; 
            color: {PALETTE['text']}; 
            font-size: 15px; 
            font-weight: bold; 
            border-radius: 8px; 
            border-left: 4px solid {PALETTE['accent']};
        """

        # Reset all styles
        self.nav_learn.setStyleSheet(base_style)
        self.nav_list.setStyleSheet(base_style)
        self.nav_tests.setStyleSheet(base_style)

        # Apply active style and trigger page-specific refresh logic
        if index == 0:
            self.nav_learn.setStyleSheet(active_style)
        elif index == 1:
            self.nav_list.setStyleSheet(active_style)
            self.word_list_page.load_words()  # Refresh DB data when opened
        elif index == 2:
            self.nav_tests.setStyleSheet(active_style)
            self.big_test_page.prepare()      # Refresh test lists when opened

    def _handle_global_hotkey(self, word):
        # Bring window to front
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.activateWindow()
        self.raise_()
        
        # Navigate to learning page and search
        self.stack.setCurrentIndex(0)
        self.learn_page.word_input.setText(word)
        self.learn_page._on_search()

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
    # Safely retrieve the existing QApplication from the loader, or create a new one
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
        
    app.setStyleSheet(STYLESHEET)
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()
    
    # Safely start the new event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
