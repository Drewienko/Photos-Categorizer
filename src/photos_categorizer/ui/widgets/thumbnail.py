from PySide6.QtGui import QPixmap, QPixmapCache

from photos_categorizer.db.manager import DatabaseManager


def load_thumbnail(photo_id: int, db: DatabaseManager) -> QPixmap:
    """Return cached pixmap or load from DB and insert into cache."""
    cache_key = f"{photo_id}:256"
    pixmap = QPixmap()
    if QPixmapCache.find(cache_key, pixmap):
        return pixmap
    raw = db.get_thumbnail(photo_id)
    if raw:
        pixmap.loadFromData(raw)
        QPixmapCache.insert(cache_key, pixmap)
    return pixmap
