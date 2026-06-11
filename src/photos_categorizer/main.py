import sys
from pathlib import Path

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from photos_categorizer.ui.main_window import MainWindow


def _dark_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor("#0a0b0d"))
    p.setColor(QPalette.ColorRole.WindowText, QColor("#e6e8ec"))
    p.setColor(QPalette.ColorRole.Base, QColor("#101216"))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor("#14161a"))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor("#1c1f24"))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor("#e6e8ec"))
    p.setColor(QPalette.ColorRole.Text, QColor("#e6e8ec"))
    p.setColor(QPalette.ColorRole.Button, QColor("#1c1f24"))
    p.setColor(QPalette.ColorRole.ButtonText, QColor("#e6e8ec"))
    p.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.Link, QColor("#2a9df4"))
    p.setColor(QPalette.ColorRole.Highlight, QColor("#2a9df4"))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor("#4a4d55"))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#4a4d55"))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#4a4d55"))
    return p


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Photos Categorizer")
    app.setOrganizationName("photos-categorizer")
    app.setStyle("Fusion")
    app.setPalette(_dark_palette())

    # sys._MEIPASS is set by PyInstaller; fall back to package path in dev
    _base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    qss_path = _base / "ui" / "style.qss"
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
