import sys
import cv2
import socket
import threading
import struct
import pickle
import os
from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, 
                             QComboBox, QGraphicsView, QGraphicsScene, 
                            QGraphicsItem, QGraphicsProxyWidget)
from PyQt5.QtGui import QImage, QPixmap, QPainter
from PyQt5.QtCore import (Qt, QRectF)

# Отключаем предупреждения OpenCV
os.environ['OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS'] = '0'
os.environ['OPENCV_VIDEOIO_DEBUG'] = '0'

# Константы для стилей
BUTTON_STYLE = """
    QPushButton {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                        stop:0 rgba(45, 45, 45, 0.95),
                                        stop:1 rgba(30, 30, 30, 0.95));
        color: white;
        border: 2px solid rgba(255, 255, 255, 0.2);
        border-radius: 15px;
        padding: 10px 20px;
        font-size: 14px;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                        stop:0 rgba(60, 60, 60, 0.95),
                                        stop:1 rgba(45, 45, 45, 0.95));
        border: 2px solid rgba(255, 255, 255, 0.4);
    }
    QPushButton:pressed {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                        stop:0 rgba(35, 35, 35, 0.95),
                                        stop:1 rgba(25, 25, 25, 0.95));
        border: 2px solid rgba(255, 255, 255, 0.3);
        padding-top: 12px;
        padding-bottom: 8px;
    }
    QPushButton:disabled {
        background-color: rgba(40, 40, 40, 0.5);
        border-color: rgba(100, 100, 100, 0.3);
        color: rgba(150, 150, 150, 0.5);
    }
"""

COMBO_STYLE = """
    QComboBox {
        background-color: rgba(30, 30, 30, 0.95);
        color: white;
        border: 2px solid rgba(255, 255, 255, 0.2);
        border-radius: 10px;
        padding: 5px 10px;
        font-size: 13px;
        font-weight: bold;
    }
    QComboBox:hover {
        background-color: rgba(40, 40, 40, 0.95);
        border: 2px solid rgba(255, 255, 255, 0.4);
    }
    QComboBox::drop-down {
        border: none;
        width: 20px;
    }
    QComboBox::down-arrow {
        image: none;
        border: none;
        width: 0;
        height: 0;
    }
    QComboBox QAbstractItemView {
        background-color: rgba(30, 30, 30, 0.95);
        color: white;
        border: 2px solid rgba(255, 255, 255, 0.3);
        border-radius: 10px;
        selection-background-color: rgba(60, 60, 60, 0.95);
        selection-color: white;
        outline: none;
        padding: 5px;
    }
    QComboBox QAbstractItemView::item {
        padding: 5px 10px;
        border-radius: 5px;
    }
    QComboBox QAbstractItemView::item:hover {
        background-color: rgba(50, 50, 50, 0.95);
    }
"""

def get_available_cameras():
    """Get list of available cameras"""
    available_cameras = []
    for i in range(10):  # Check first 10 indexes
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                available_cameras.append(i)
            cap.release()
    return available_cameras

class BaseGraphicsItem(QGraphicsItem):
    """Базовый класс для графических элементов"""
    def __init__(self, width, height, parent=None):
        super().__init__(parent)
        self.width = width
        self.height = height
        self.setFlag(QGraphicsItem.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        
    def boundingRect(self):
        return QRectF(0, 0, self.width, self.height)
        
    def paint(self, painter, option, widget):
        pass

class ControlButton(BaseGraphicsItem):
    def __init__(self, text, parent=None):
        super().__init__(130, 50, parent)
        self.setZValue(2)
        
        self.button = QPushButton(text)
        self.button.setFixedSize(self.width, self.height)
        self.button.setStyleSheet(BUTTON_STYLE)
        
        self.proxy = QGraphicsProxyWidget(self)
        self.proxy.setWidget(self.button)
        
    def setEnabled(self, enabled):
        self.button.setEnabled(enabled)
        
    def connect(self, slot):
        self.button.clicked.connect(slot)
        
    def mousePressEvent(self, event):
        self.proxy.mousePressEvent(event)
        
    def mouseReleaseEvent(self, event):
        self.proxy.mouseReleaseEvent(event)
        
    def mouseMoveEvent(self, event):
        self.proxy.mouseMoveEvent(event)

class CameraSelectLayer(BaseGraphicsItem):
    def __init__(self, parent=None):
        super().__init__(200, 35, parent)
        self.setZValue(2)
        
        self.combo = QComboBox()
        self.combo.setFixedSize(self.width, self.height)
        self.combo.setStyleSheet(COMBO_STYLE)
        
        self.proxy = QGraphicsProxyWidget(self)
        self.proxy.setWidget(self.combo)

class VideoLayer(BaseGraphicsItem):
    def __init__(self, width, height, parent=None, is_background=False):
        super().__init__(width, height, parent)
        self.is_background = is_background
        
        if is_background:
            self.setZValue(0)
            self.setAcceptHoverEvents(False)
            self.setAcceptedMouseButtons(Qt.NoButton)
        else:
            self.setZValue(1)
            
        self.label = QLabel()
        self.label.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 0, 0, 0.8);
                border: 2px solid rgba(255, 255, 255, 0.2);
                border-radius: 15px;
            }
        """)
        self.label.setFixedSize(width, height)
        self.proxy = QGraphicsProxyWidget(self)
        self.proxy.setWidget(self.label)
        
    def update_frame(self, frame):
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = frame.shape
        bytes_per_line = ch * w
        qt_img = QImage(frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_img).scaled(
            self.width, self.height,
            Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.label.setPixmap(pixmap)
        
    def mousePressEvent(self, event):
        if not self.is_background:
            super().mousePressEvent(event)
            
    def mouseMoveEvent(self, event):
        if not self.is_background:
            super().mouseMoveEvent(event)
            
    def mouseReleaseEvent(self, event):
        if not self.is_background:
            super().mouseReleaseEvent(event)

class VideoChat(QWidget):
    def __init__(self, mode, host, port):
        super().__init__()
        self.mode = mode
        self.host = host
        self.port = port
        self.running = False
        self.local_running = False
        self.current_camera = None
        self.sock = None
        self.conn = None
        self.addr = None

        self._init_ui()
        self._setup_networking()
        
    def _init_ui(self):
        """Инициализация пользовательского интерфейса"""
        self.setWindowTitle(f'PyQt Video Chat - {self.mode.capitalize()}')
        self.resize(1200, 800)

        # Create graphics scene and view
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setStyleSheet("background-color: black;")
        
        # Create main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)

        # Create layers
        self.remote_video = VideoLayer(1200, 800, is_background=True)
        self.local_video = VideoLayer(320, 240)
        self.camera_select = CameraSelectLayer()
        self.start_button = ControlButton('Start Call')
        self.end_button = ControlButton('End Call')
        self.end_button.setEnabled(False)

        # Add layers to scene
        self.scene.addItem(self.remote_video)
        self.scene.addItem(self.local_video)
        self.scene.addItem(self.camera_select)
        self.scene.addItem(self.start_button)
        self.scene.addItem(self.end_button)

        # Position layers
        self._position_elements()

        # Connect signals
        self.start_button.connect(self.start_call)
        self.end_button.connect(self.end_call)
        self.camera_select.combo.currentIndexChanged.connect(self.camera_changed)

        # Populate camera combo
        self._populate_camera_combo()
        
    def _position_elements(self):
        """Позиционирование элементов интерфейса"""
        self.local_video.setPos(20, 20)
        self.camera_select.setPos(20, 270)
        
        button_spacing = 20
        total_width = self.start_button.width + self.end_button.width + button_spacing
        start_x = (self.width() - total_width) // 2
        button_y = self.height() - self.start_button.height - 20
        
        self.start_button.setPos(start_x, button_y)
        self.end_button.setPos(start_x + self.start_button.width + button_spacing, button_y)
        
    def _populate_camera_combo(self):
        """Заполнение списка доступных камер"""
        self.camera_select.combo.addItem("Select camera", None)
        for camera_id in get_available_cameras():
            self.camera_select.combo.addItem(f'Camera {camera_id}', camera_id)
            
    def _setup_networking(self):
        """Настройка сетевого подключения"""
        if self.mode == 'server':
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.bind((self.host, self.port))
            self.sock.listen(1)
            print(f'Server listening on {self.host}:{self.port}')

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.view.setFixedSize(self.size())
        self.scene.setSceneRect(0, 0, self.width(), self.height())
        self.remote_video.width = self.width()
        self.remote_video.height = self.height()
        self.remote_video.update()
        self._position_elements()

    def display_frame(self, frame):
        self.remote_video.update_frame(frame)

    def display_local_frame(self, frame):
        self.local_video.update_frame(frame)

    def camera_changed(self, index):
        if self.running:
            self.end_call()
        
        if self.local_running:
            self.local_running = False
        
        self.current_camera = self.camera_select.combo.currentData()
        
        if self.current_camera is not None:
            self.local_running = True
            self.local_video.label.clear()
            self.start_button.setEnabled(True)
            threading.Thread(target=self.handle_local_video, daemon=True).start()
        else:
            self.local_video.label.setText("Select camera to start preview")
            self.start_button.setEnabled(False)

    def start_call(self):
        if self.mode == 'client':
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            threading.Thread(target=self.connect_to_server, daemon=True).start()
        else:  # server mode
            threading.Thread(target=self.accept_connection, daemon=True).start()

        self.running = True
        self.start_button.setEnabled(False)
        self.end_button.setEnabled(True)

    def accept_connection(self):
        self.conn, self.addr = self.sock.accept()
        print(f'Accepted connection from {self.addr}')
        threading.Thread(target=self.handle_receive, daemon=True).start()
        threading.Thread(target=self.handle_send, daemon=True).start()

    def connect_to_server(self):
        self.sock.connect((self.host, self.port))
        self.conn = self.sock
        print(f'Connected to server at {self.host}:{self.port}')
        threading.Thread(target=self.handle_receive, daemon=True).start()
        threading.Thread(target=self.handle_send, daemon=True).start()

    def handle_send(self):
        cap = cv2.VideoCapture(self.current_camera)
        while self.running:
            ret, frame = cap.read()
            if not ret:
                continue
            data = pickle.dumps(frame)
            length = struct.pack('!I', len(data))
            try:
                self.conn.sendall(length + data)
            except Exception as e:
                print(f'Send error: {e}')
                break
        cap.release()

    def handle_receive(self):
        data_buffer = b''
        payload_size = struct.calcsize('!I')
        while self.running:
            while len(data_buffer) < payload_size:
                packet = self.conn.recv(4096)
                if not packet:
                    return
                data_buffer += packet
            packed_size = data_buffer[:payload_size]
            data_buffer = data_buffer[payload_size:]
            msg_size = struct.unpack('!I', packed_size)[0]

            while len(data_buffer) < msg_size:
                packet = self.conn.recv(4096)
                if not packet:
                    return
                data_buffer += packet
            frame_data = data_buffer[:msg_size]
            data_buffer = data_buffer[msg_size:]

            frame = pickle.loads(frame_data)
            self.display_frame(frame)

    def handle_local_video(self):
        cap = cv2.VideoCapture(self.current_camera)
        while self.local_running:
            ret, frame = cap.read()
            if not ret:
                continue
            self.display_local_frame(frame)
        cap.release()

    def end_call(self):
        self.running = False
        self.start_button.setEnabled(True)
        self.end_button.setEnabled(False)
        if self.conn:
            self.conn.close()
        if self.sock:
            self.sock.close()
        self.remote_video.label.clear()
        self.remote_video.label.setStyleSheet('background-color: black;')
        self.local_video.label.clear()
        self.local_video.label.setStyleSheet('background-color: black;')

    def closeEvent(self, event):
        self.local_running = False
        if self.running:
            self.end_call()
        event.accept()

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='PyQt Video Chat')
    parser.add_argument('mode', choices=['server', 'client'], help='Run as server or client')
    parser.add_argument('--host', default='127.0.0.1', help='Host IP')
    parser.add_argument('--port', type=int, default=9999, help='Port number')
    args = parser.parse_args()

    app = QApplication(sys.argv)
    window = VideoChat(args.mode, args.host, args.port)
    window.show()
    sys.exit(app.exec_())
