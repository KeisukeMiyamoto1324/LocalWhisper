# floating_ui.py

import sys
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QPainter, QColor, QPen
import pyqtgraph as pg
import numpy as np

class WaveformWidget(QWidget):
    """A simple widget to draw a waveform using QPainter."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.waveform_data = np.array([])
        self.pen = QPen(QColor(255, 255, 255, 180), 1.5) # White, semi-transparent pen
        self.setMinimumSize(200, 60)
        self.setMaximumSize(200, 60)

    def update_waveform(self, data):
        self.waveform_data = data
        self.update() # Triggers a repaint

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw a rounded rectangle as the background
        painter.setBrush(QColor(0, 0, 0, 150)) # Black, semi-transparent background
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 15, 15)

        # Draw the waveform
        if self.waveform_data.size > 0:
            painter.setPen(self.pen)
            
            # Prepare points for the polyline
            h = self.height()
            w = self.width()
            center_y = h / 2
            
            # Map data points to screen coordinates
            points = []
            num_points = len(self.waveform_data)
            for i in range(num_points):
                x = (i / (num_points - 1)) * w if num_points > 1 else w / 2
                # Scale the y-value based on the data, clamping to prevent it going outside the widget
                y_val = self.waveform_data[i]
                scaled_y = center_y - (y_val * h * 0.8) # Use 80% of height for amplitude
                points.append(QPoint(int(x), int(scaled_y)))

            painter.drawPolyline(*points)


class FloatingUI(QWidget):
    # Signal to update the waveform, carrying a NumPy array
    update_waveform_signal = pyqtSignal(np.ndarray)

    def __init__(self):
        super().__init__()
        
        # Set window flags for a floating, frameless UI
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |    # No window border or title bar
            Qt.WindowType.WindowStaysOnTopHint |   # Always on top of other windows
            Qt.WindowType.Tool                     # Doesn't appear in the taskbar/dock
        )
        # Make the window background transparent
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Main layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # Custom waveform widget
        self.waveform_widget = WaveformWidget(self)
        self.layout.addWidget(self.waveform_widget)

        # Connect the signal to the update slot of the waveform widget
        self.update_waveform_signal.connect(self.waveform_widget.update_waveform)

    def update_position(self, x, y):
        """Moves the window to the specified coordinates."""
        self.move(x, y)