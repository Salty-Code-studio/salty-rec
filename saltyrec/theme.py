"""Salty Rec look, on the same tokens as Yabi (Sand & Surf).

Three rules run the whole UI:
  Three planes   big type in the back, the subject in the middle, the button on top (stage.py).
  One signal     coral only ever means "tap this". Status, selection, sliders and focus are ink.
                 Allowed coral selectors: #record, #signal, #barStop. Nothing else.
  No middle      one huge thing per screen (painted by Stage), everything else body, small or tiny.
"""
SAND, SAND_2, PANEL, FILL = "#F2EBDD", "#EAE0CD", "#FCFAF4", "#F4EEE1"
TEAL, TEAL_700, INK, INK_SOFT, INK_MUTE = "#0E3A40", "#0A2C31", "#1C2B2E", "#586A6D", "#8B9B9D"
CORAL, CORAL_600, SKY = "#FF6F59", "#F2563F", "#4FA8C9"
SIGNAL, SIGNAL_600 = CORAL, CORAL_600
DANGER = "#C0473A"
LINE, LINE_RGBA = "#E3DAC8", (227, 218, 200)
BACK_TYPE = "#E4D8C2"            # the huge back-plane type: sand on sand, reads as depth not as text

# sizes: body, small, tiny. The huge size is only ever painted by Stage.
BODY, SMALL, TINY = 13, 12, 10
MUTED = INK_SOFT

QSS = f"""
* {{ font-family: "Inter", "Segoe UI", "Helvetica Neue"; font-size: {BODY}px; color: {INK}; }}
QMainWindow, QWidget#root, QWidget#library, QMessageBox, QDialog {{ background: {SAND}; }}
QLabel#brand {{ font-family: "Space Grotesk"; font-size: {BODY}px; font-weight: 700; color: {TEAL}; }}
QLabel#label {{ font-family: "JetBrains Mono"; font-size: {TINY}px; letter-spacing: 1.5px; color: {INK_MUTE}; }}
QLabel#muted, QLabel#summary {{ color: {INK_SOFT}; font-size: {SMALL}px; }}
QLabel#status {{ color: {TEAL}; font-family: "JetBrains Mono"; font-size: {TINY + 1}px; }}
QLabel#clock {{ font-family: "JetBrains Mono"; font-size: {TINY + 1}px; color: {INK_SOFT}; }}
QLineEdit#title {{ font-family: "Space Grotesk"; font-size: {BODY + 1}px; font-weight: 700; color: {TEAL};
                  background: transparent; border: 1px solid transparent; border-radius: 8px; padding: 4px 6px; }}
QLineEdit#title:hover {{ border-color: {LINE}; }}
QLineEdit#title:focus {{ border-color: {TEAL}; background: {PANEL}; }}
QFrame#card {{ background: {PANEL}; border: 1px solid {LINE}; border-radius: 14px; }}
QComboBox, QLineEdit {{ background: {PANEL}; border: 1px solid {LINE}; border-radius: 10px; padding: 6px 10px; min-height: 20px; }}
QComboBox:focus, QLineEdit:focus {{ border-color: {TEAL}; }}
QComboBox::drop-down {{ border: 0; width: 22px; }}
QComboBox QAbstractItemView {{ background: {PANEL}; selection-background-color: {FILL}; selection-color: {TEAL}; }}

/* quiet by default: ink on paper */
QPushButton {{ background: transparent; border: 1px solid {LINE}; border-radius: 10px; padding: 6px 12px;
              color: {TEAL}; font-size: {SMALL}px; font-weight: 500; }}
QPushButton:hover {{ background: {FILL}; border-color: #D6CBB5; }}
QPushButton:focus {{ border-color: {TEAL}; }}
QPushButton:disabled {{ color: {INK_MUTE}; border-color: {LINE}; }}
QPushButton#text {{ border: 0; padding: 4px 6px; color: {INK_SOFT}; }}
QPushButton#text:hover {{ color: {TEAL}; background: transparent; }}
QPushButton#danger {{ border: 0; color: {DANGER}; padding: 4px 6px; }}
QPushButton#seg {{ border: 0; border-radius: 8px; padding: 6px 8px; color: {INK_SOFT}; font-size: {SMALL}px; }}
QPushButton#seg:checked {{ background: {PANEL}; color: {TEAL}; font-weight: 600; }}
QWidget#segbox {{ background: {SAND_2}; border-radius: 10px; }}

/* the one signal: coral means tap this, nothing else */
QPushButton#record, QPushButton#signal {{ background: {SIGNAL}; color: white; border: 0; border-radius: 22px;
              padding: 12px 26px; font-family: "Space Grotesk"; font-size: {BODY + 1}px; font-weight: 700; }}
QPushButton#record:hover, QPushButton#signal:hover {{ background: {SIGNAL_600}; }}
QPushButton#record:focus, QPushButton#signal:focus {{ border: 2px solid {TEAL_700}; }}
QPushButton#signal:disabled {{ background: {SAND_2}; color: {INK_MUTE}; }}

QCheckBox {{ spacing: 8px; font-size: {SMALL}px; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid #CFC3AC; border-radius: 4px; background: {PANEL}; }}
QCheckBox::indicator:hover {{ border-color: {TEAL}; }}
QCheckBox::indicator:checked {{ background: {TEAL}; border-color: {TEAL}; image: none; }}
QListWidget {{ background: transparent; border: 0; outline: 0; font-size: {SMALL}px; }}
QListWidget::item {{ border-radius: 10px; padding: 6px; margin: 1px 0; color: {INK}; }}
QListWidget::item:selected {{ background: {PANEL}; color: {TEAL}; border: 1px solid {LINE}; }}
QListWidget::item:hover:!selected {{ background: {FILL}; }}
QTextBrowser {{ background: {PANEL}; border: 1px solid {LINE}; border-radius: 14px; padding: 10px; font-size: {SMALL}px; }}
QSlider::groove:horizontal {{ height: 3px; background: {LINE}; border-radius: 1px; }}
QSlider::sub-page:horizontal {{ background: {TEAL}; border-radius: 1px; }}
QSlider::handle:horizontal {{ background: {TEAL}; width: 11px; height: 11px; margin: -4px 0; border-radius: 5px; }}
QSplitter::handle {{ background: {LINE}; width: 1px; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #D6CBB5; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {INK_MUTE}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; background: none; }}

/* recording bar: dark ink, the timer and status are sand, only Stop is coral */
QLabel#barTime {{ color: {SAND}; font-family: "JetBrains Mono"; font-size: {BODY + 2}px; min-width: 52px; }}
QPushButton#barGhost {{ color: {SAND}; border: 1px solid rgba(242,235,221,0.22); border-radius: 15px; padding: 5px 12px; }}
QPushButton#barGhost:hover {{ background: rgba(242,235,221,0.08); }}
QPushButton#barStop {{ background: {SIGNAL}; color: white; border: 0; border-radius: 15px; padding: 6px 16px; font-weight: 700; }}
QPushButton#barStop:hover {{ background: {SIGNAL_600}; }}
QToolTip {{ background: {INK}; color: {SAND}; border: 0; padding: 6px; font-size: {SMALL}px; }}
"""
