"""Small painted navigation icons, independent of emoji/font availability."""
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPen, QColor, QPolygonF


def navigation_icon(name):
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor('#72aaff'), 1.5))
    if name in ('dashboard', 'traffic_reports'):
        painter.drawRoundedRect(3, 3, 18, 18, 2, 2)
        for x, y in ((7, 12), (12, 7), (17, 10)):
            painter.drawLine(x, y, x, 19)
    elif name == 'issue_reports':
        painter.drawPolygon(QPolygonF([QPointF(12, 3), QPointF(22, 21), QPointF(2, 21)]))
        painter.drawLine(12, 9, 12, 14)
        painter.drawPoint(12, 18)
    elif name == 'settings':
        painter.drawEllipse(5, 5, 14, 14)
        painter.drawEllipse(9, 9, 6, 6)
        for x1, y1, x2, y2 in ((12,1,12,5),(12,19,12,23),(1,12,5,12),(19,12,23,12)):
            painter.drawLine(x1,y1,x2,y2)
    elif name == 'admin_users':
        painter.drawEllipse(8, 3, 8, 8)
        painter.drawArc(4, 12, 16, 16, 0, 180*16)
        painter.drawLine(4, 20, 20, 20)
    elif name == 'brand':
        painter.drawRoundedRect(7, 1, 10, 22, 4, 4)
        for y in (4, 10, 16):
            painter.drawEllipse(10, y, 4, 4)
    else:
        painter.drawRoundedRect(5, 2, 14, 20, 2, 2)
        for y in (7, 11, 15, 19):
            painter.drawLine(8, y, 16, y)
    painter.end()
    return QIcon(pixmap)
