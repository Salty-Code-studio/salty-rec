SAND, TEAL, CORAL, SKY, INK = "#F2EBDD", "#0E3A40", "#FF6F59", "#4FA8C9", "#1C2B2E"
CARD, LINE, MUTED = "#FBF7EF", "rgba(14,58,64,0.16)", "rgba(28,43,46,0.62)"

QSS = f"""
* {{ font-family: "Inter", "Helvetica Neue"; font-size: 13px; color: {INK}; }}
QMainWindow, QWidget#root, QWidget#library, QMessageBox, QDialog {{ background: {SAND}; }}
QLabel#brand {{ font-family: "Space Grotesk"; font-size: 18px; font-weight: 600; color: {TEAL}; }}
QLabel#h1 {{ font-family: "Space Grotesk"; font-size: 22px; font-weight: 600; color: {TEAL}; }}
QLabel#label {{ font-family: "JetBrains Mono"; font-size: 10px; letter-spacing: 1.5px; color: {MUTED}; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#status {{ color: {TEAL}; font-family: "JetBrains Mono"; font-size: 11px; }}
QFrame#card {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 14px; }}
QComboBox, QLineEdit {{ background: white; border: 1px solid {LINE}; border-radius: 9px; padding: 7px 10px; min-height: 22px; }}
QComboBox:focus, QLineEdit:focus {{ border-color: {SKY}; }}
QComboBox::drop-down {{ border: 0; width: 22px; }}
QComboBox QAbstractItemView {{ background: white; selection-background-color: {SAND}; selection-color: {TEAL}; }}
QPushButton {{ background: transparent; border: 1px solid {LINE}; border-radius: 9px; padding: 7px 14px; color: {TEAL}; font-weight: 500; }}
QPushButton:hover {{ background: rgba(14,58,64,0.05); }}
QPushButton:disabled {{ color: rgba(14,58,64,0.35); }}
QPushButton#seg {{ border: 0; border-radius: 7px; padding: 7px 8px; color: {MUTED}; }}
QPushButton#seg:checked {{ background: white; color: {TEAL}; }}
QWidget#segbox {{ background: rgba(14,58,64,0.07); border-radius: 10px; }}
QPushButton#record {{ background: {CORAL}; color: white; border: 0; border-radius: 20px; padding: 11px; min-height: 18px; font-family: "Space Grotesk"; font-size: 15px; font-weight: 600; }}
QPushButton#record:hover {{ background: #F25E48; }}
QPushButton#primary {{ background: {TEAL}; color: {SAND}; border: 0; }}
QPushButton#primary:hover {{ background: #134a52; }}
QPushButton#danger {{ color: #B3402F; }}
QCheckBox {{ spacing: 8px; }}
QListWidget {{ background: transparent; border: 0; outline: 0; }}
QListWidget::item {{ border-radius: 10px; padding: 6px; margin: 2px 0; }}
QListWidget::item:selected {{ background: white; color: {INK}; }}
QListWidget::item:hover:!selected {{ background: rgba(255,255,255,0.5); }}
QTextBrowser {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 12px; padding: 10px; }}
QSlider::groove:horizontal {{ height: 4px; background: rgba(14,58,64,0.15); border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {TEAL}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {CORAL}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }}
QLabel#barTime {{ color: {SAND}; font-family: "JetBrains Mono"; font-size: 15px; min-width: 52px; }}
QPushButton#barGhost {{ color: {SAND}; border: 1px solid rgba(242,235,221,0.25); border-radius: 15px; padding: 5px 12px; }}
QPushButton#barGhost:hover {{ background: rgba(242,235,221,0.08); }}
QPushButton#barStop {{ background: {CORAL}; color: white; border: 0; border-radius: 15px; padding: 6px 16px; font-weight: 600; }}
QToolTip {{ background: {INK}; color: {SAND}; border: 0; padding: 6px; }}
"""
