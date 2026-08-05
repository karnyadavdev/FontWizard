import ctypes
import re
import subprocess
import sys
import winreg
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QThread,
    QRect,
    QUrl,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QFontDatabase,
    QIcon,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QBoxLayout,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QStyleOptionButton,
    QVBoxLayout,
    QWidget,
    QLayout,
)

from settings import APP_GITHUB_URL, APP_NAME, WEIGHT_TARGETS
from core import FontWizardController
from font_detection import inspect_font
from operation import OperationResult

WM_SETTINGCHANGE = 0x001A
WM_THEMECHANGED = 0x031A
WM_DWMCOLORIZATIONCOLORCHANGED = 0x0320

def get_system_accent_color() -> tuple[str, str, str]:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Accent") as key:
            val, _ = winreg.QueryValueEx(key, "AccentColorMenu")
            r = val & 0xFF
            g = (val >> 8) & 0xFF
            b = (val >> 16) & 0xFF
            accent_hex = f"#{r:02X}{g:02X}{b:02X}"
            
            r_h = min(255, int(r * 1.15) + 15)
            g_h = min(255, int(g * 1.15) + 15)
            b_h = min(255, int(b * 1.15) + 15)
            accent_hover_hex = f"#{r_h:02X}{g_h:02X}{b_h:02X}"
            
            luminance = (r * 299 + g * 587 + b * 114) / 1000
            accent_text_hex = "#000000" if luminance > 130 else "#FFFFFF"
            return accent_hex, accent_hover_hex, accent_text_hex
    except Exception:
        pass
    return "#60CDFF", "#7AD7FF", "#000000"

def get_theme_colors(is_dark: bool) -> dict[str, str]:
    accent_color, accent_hover, accent_text = get_system_accent_color()
    if is_dark:
        return {
            "bg_card": "rgba(255, 255, 255, 0.05)",
            "bg_card_hover": "rgba(255, 255, 255, 0.08)",
            "bg_button": "rgba(255, 255, 255, 0.08)",
            "bg_button_hover": "rgba(255, 255, 255, 0.13)",
            "bg_button_pressed": "rgba(255, 255, 255, 0.04)",
            "border_card": "rgba(255, 255, 255, 0.09)",
            "border_button": "rgba(255, 255, 255, 0.12)",
            "text_primary": "#FFFFFF",
            "text_secondary": "rgba(255, 255, 255, 0.78)",
            "text_muted": "rgba(255, 255, 255, 0.50)",
            "accent": accent_color,
            "accent_hover": accent_hover,
            "accent_text": accent_text,
            "success": "#6CCB5F",
            "warning": accent_color,
            "danger": "#FF99A4",
            "bg_dialog": "#202020",
        }
    return {
        "bg_card": "rgba(0, 0, 0, 0.04)",
        "bg_card_hover": "rgba(0, 0, 0, 0.07)",
        "bg_button": "rgba(0, 0, 0, 0.05)",
        "bg_button_hover": "rgba(0, 0, 0, 0.09)",
        "bg_button_pressed": "rgba(0, 0, 0, 0.03)",
        "border_card": "rgba(0, 0, 0, 0.08)",
        "border_button": "rgba(0, 0, 0, 0.10)",
        "text_primary": "rgba(0, 0, 0, 0.9)",
        "text_secondary": "rgba(0, 0, 0, 0.6)",
        "text_muted": "rgba(0, 0, 0, 0.45)",
        "accent": accent_color,
        "accent_hover": accent_hover,
        "accent_text": accent_text,
        "success": "#0F7B0F",
        "warning": accent_color,
        "danger": "#C42B1C",
        "bg_dialog": "#FBFBFB",
    }

def get_asset_path(name):
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets" / name
    return Path(__file__).resolve().parent / "assets" / name

def _parse_qss_color(text) -> QColor:
    match = re.match(r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)", text)
    if match:
        r, g, b, a = match.groups()
        return QColor(int(r), int(g), int(b), int(round(float(a) * 255)))
    return QColor(text)

class MARGINS(ctypes.Structure):
    _fields_ = [
        ("cxLeftWidth", ctypes.c_int),
        ("cxRightWidth", ctypes.c_int),
        ("cyTopHeight", ctypes.c_int),
        ("cyBottomHeight", ctypes.c_int),
    ]

def apply_native_mica(hwnd_id, is_dark) -> bool:
    build = sys.getwindowsversion().build
    if build < 22000:
        return False
    try:
        dwmapi = ctypes.windll.dwmapi
        hwnd = wintypes.HWND(hwnd_id)
        dark_mode = ctypes.c_int(1 if is_dark else 0)
        dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark_mode), ctypes.sizeof(dark_mode))
        if build >= 22621:
            backdrop_type = ctypes.c_int(2) # 2 for Mica
            ok = dwmapi.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(backdrop_type), ctypes.sizeof(backdrop_type))
        else:
            mica_effect = ctypes.c_int(1)
            ok = dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(mica_effect), ctypes.sizeof(mica_effect))
        if ok != 0:
            return False
        margins = MARGINS(-1, -1, -1, -1)
        dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
        if build >= 22621:
            caption_color = ctypes.c_int(0xFFFFFFFE)
            dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption_color), ctypes.sizeof(caption_color))
        return True
    except Exception:
        return False

def is_system_dark_mode():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return value == 0
    except Exception:
        return True

def get_wizard_stylesheet(is_dark: bool, use_mica: bool = True) -> str:
    colors = get_theme_colors(is_dark)
    window_background = "transparent" if use_mica else colors["bg_dialog"]
    return f"""
    QMainWindow, #CentralWidget {{ background: {window_background}; }}
    QScrollArea, QScrollArea QWidget {{ background: transparent; }}
    QWidget {{ 
        color: {colors["text_primary"]}; 
        font-family: 'Segoe UI Variable Text', 'Segoe UI', sans-serif; 
        font-size: 14px; 
    }}
    #AppTitle {{ font-size: 28px; font-weight: 600; font-family: 'Segoe UI Variable Display', 'Segoe UI', sans-serif; letter-spacing: -0.5px; }}
    #AppSubtitle {{ color: {colors["text_secondary"]}; font-size: 14px; margin-top: 0px; }}
    #SectionHeader {{ font-weight: 600; font-size: 18px; padding: 0; font-family: 'Segoe UI Variable Display', 'Segoe UI', sans-serif; }}
    #SectionMeta {{ color: {colors["text_muted"]}; font-size: 13px; }}
    
    #Banner, #SetupCard, #VariantCard, #EmptyState {{ 
        background-color: {colors["bg_card"]}; 
        border: 1px solid {colors["border_card"]}; 
        border-radius: 8px; 
    }}
    #BannerIcon {{ font-family: 'Segoe Fluent Icons'; font-size: 20px; }}
    #BannerTitle {{ font-size: 14px; font-weight: 600; }}
    #BannerText {{ font-size: 13px; color: {colors["text_secondary"]}; }}
    
    #CardTitle {{ font-weight: 600; font-size: 14px; }}
    #CardDesc {{ color: {colors["text_secondary"]}; font-size: 12px; }}
    #SelectedFont {{ color: {colors["text_secondary"]}; font-size: 12px; }}
    #VariantPreview {{ color: {colors["text_primary"]}; font-size: 18px; }}
    #VariantMeta {{ color: {colors["text_muted"]}; font-size: 12px; }}
    
    QPushButton {{ 
        background-color: {colors["bg_button"]}; 
        border: 1px solid {colors["border_button"]}; 
        border-radius: 4px; 
        padding: 4px 12px; 
        min-height: 28px; 
        font-size: 13px; 
        font-weight: 450; 
    }}
    QPushButton:disabled {{ color: {colors["text_muted"]}; background-color: {colors["bg_card"]}; border-color: {colors["border_card"]}; }}
    
    QPushButton[buttonRole="primary"], QPushButton[buttonRole="warning"] {{ 
        background-color: {colors["accent"]}; 
        border: 1px solid {colors["accent"]}; 
        color: {colors["accent_text"]}; 
        font-weight: 600;
    }}
    
    QPushButton[buttonRole="danger"] {{ color: {colors["danger"]}; }}
    QPushButton[buttonRole="secondary"] {{ 
        background-color: {colors["bg_button"]}; 
        color: {colors["text_primary"]}; 
    }}
    #HeaderIconButton {{
        background-color: transparent;
        border: none;
        padding: 0;
        min-width: 32px;
        max-width: 32px;
        min-height: 32px;
        max-height: 32px;
    }}
    #HeaderIconButton:hover {{
        background-color: transparent;
        border: none;
    }}
    #VariantBrowseBtn {{
        font-family: 'Segoe Fluent Icons';
        font-size: 16px;
        background-color: transparent;
        border: none;
        padding: 0;
        min-height: 30px;
        max-height: 30px;
        min-width: 30px;
        max-width: 30px;
        color: {colors["accent"]};
    }}
    #VariantBrowseBtn:hover {{
        color: {colors["accent_hover"]};
    }}
    #HeaderIconButton:pressed {{
        background-color: transparent;
        border: none;
    }}
    
    QScrollBar:vertical {{ border: none; background: transparent; width: 12px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {colors["border_card"]}; border-radius: 3px; min-height: 30px; margin: 0 3px; }}
    QScrollBar::handle:vertical:hover {{ background: {colors["text_secondary"]}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ border: none; background: none; height: 0px; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
    """

class OperationThread(QThread):
    progress = Signal(int, str)
    done = Signal(object)
    def __init__(self, job, parent=None):
        super().__init__(parent)
        self._job = job
    def run(self):
        try:
            result = self._job(progress=self.progress.emit)
        except Exception as exc:
            result = OperationResult(False, "The operation failed before it could finish.", [str(exc)])
        self.done.emit(result)

class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, spacing=-1):
        super().__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self.itemList = []

    def addItem(self, item):
        self.itemList.append(item)
        self.invalidate()

    def count(self):
        return len(self.itemList)

    def itemAt(self, index):
        if index >= 0 and index < len(self.itemList):
            return self.itemList[index]
        return None

    def takeAt(self, index):
        if index >= 0 and index < len(self.itemList):
            item = self.itemList.pop(index)
            self.invalidate()
            return item
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self.doLayout(QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.doLayout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self.itemList:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _column_count(self, width):
        if not self.itemList:
            return 1
        spacing = max(0, self.spacing())
        min_width = max(item.minimumSize().width() for item in self.itemList)
        return max(1, (width + spacing) // (min_width + spacing))

    def doLayout(self, rect, testOnly):
        spacing = max(0, self.spacing())
        margins = self.contentsMargins()
        content_rect = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        columns = self._column_count(content_rect.width())
        item_width = max(0, (content_rect.width() - spacing * (columns - 1)) // columns)
        row_height = max((item.sizeHint().height() for item in self.itemList), default=0)

        for index, item in enumerate(self.itemList):
            row = index // columns
            column = index % columns
            x = content_rect.x() + column * (item_width + spacing)
            y = content_rect.y() + row * (row_height + spacing)

            if not testOnly:
                item.setGeometry(QRect(x, y, item_width, row_height))

        rows = (len(self.itemList) + columns - 1) // columns
        content_height = rows * row_height + max(0, rows - 1) * spacing
        return margins.top() + content_height + margins.bottom()


class _FadeMixin:
    def _setup_fade(self, duration=160):
        self._fade_duration = duration
        self._hover_amount = 0.0
        self._press_amount = 0.0
        self._hover_color = QColor(0, 0, 0, 0)
        self._press_color = QColor(0, 0, 0, 0)
        self._hover_anim = QVariantAnimation(self)
        self._hover_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._hover_anim.valueChanged.connect(self._set_hover_amount)
        self._press_anim = QVariantAnimation(self)
        self._press_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._press_anim.valueChanged.connect(self._set_press_amount)
        self.setAttribute(Qt.WA_Hover, True)

    def set_fade_colors(self, hover_color, press_color):
        self._hover_color = QColor(hover_color)
        self._press_color = QColor(press_color)

    def _animate_fade(self, anim, end_value):
        anim.stop()
        current = anim.currentValue()
        anim.setStartValue(float(current) if current is not None else 0.0)
        anim.setEndValue(end_value)
        anim.setDuration(self._fade_duration)
        anim.start()

    def _set_hover_amount(self, value):
        self._hover_amount = float(value)
        self.update()

    def _set_press_amount(self, value):
        self._press_amount = float(value)
        self.update()

    def enterEvent(self, event):
        super().enterEvent(event)
        if self.isEnabled():
            self._animate_fade(self._hover_anim, 1.0)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._animate_fade(self._hover_anim, 0.0)
        self._animate_fade(self._press_anim, 0.0)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self._animate_fade(self._hover_anim, 0.0)
        self._animate_fade(self._press_anim, 1.0)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self._animate_fade(self._press_anim, 0.0)
        if self.underMouse():
            self._animate_fade(self._hover_anim, 1.0)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.EnabledChange:
            self._hover_anim.stop()
            self._press_anim.stop()
            if self.isEnabled() and self.underMouse():
                self._hover_amount = 1.0
            else:
                self._hover_amount = 0.0
                self._press_amount = 0.0
            self.update()

    def _paint_fade_overlay(self, painter, radius=4.0):
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self._hover_amount > 0.001:
            color = QColor(self._hover_color)
            color.setAlpha(int(color.alpha() * self._hover_amount))
            painter.setBrush(color)
            painter.drawRoundedRect(rect, radius, radius)
        if self._press_amount > 0.001:
            color = QColor(self._press_color)
            color.setAlpha(int(color.alpha() * self._press_amount))
            painter.setBrush(color)
            painter.drawRoundedRect(rect, radius, radius)


class FadeButton(_FadeMixin, QPushButton):
    def __init__(self, *args, fade_radius=4.0, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_fade()
        self._busy = False
        self._fade_radius = fade_radius

    def set_busy(self, active):
        self._busy = active
        self.update()

    def paintEvent(self, event):
        option = QStyleOptionButton()
        self.initStyleOption(option)
        painter = QPainter(self)
        painter.setClipRect(self.rect())
        self.style().drawControl(QStyle.CE_PushButtonBevel, option, painter, self)
        self._paint_fade_overlay(painter, self._fade_radius)
        self.style().drawControl(QStyle.CE_PushButtonLabel, option, painter, self)
        painter.end()


class FadeFrame(_FadeMixin, QFrame):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_fade()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        self._paint_fade_overlay(painter, 8.0)
        painter.end()


class StatusBanner(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Banner")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(16)
        
        self.icon_lbl = QLabel()
        self.icon_lbl.setObjectName("BannerIcon")
        self.icon_lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        layout.addWidget(self.icon_lbl, 0, Qt.AlignVCenter)
        
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        
        self.title = QLabel("")
        self.title.setObjectName("BannerTitle")
        self.title.setWordWrap(True)
        self.title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.text = QLabel("")
        self.text.setObjectName("BannerText")
        self.text.setWordWrap(True)
        self.text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        text_layout.addWidget(self.title)
        text_layout.addWidget(self.text)
        layout.addLayout(text_layout, 1)

    def set_content(self, title, message):
        self.title.setText(title)
        self.text.setText(message)
        
    def set_icon(self, icon_char, color):
        self.icon_lbl.setText(icon_char)
        self.icon_lbl.setStyleSheet(f"color: {color};")

class WeightCard(FadeFrame):
    change_requested = Signal(str)
    reset_requested = Signal(str)

    def __init__(self, weight, font_path, parent=None, is_mono=False, has_override=False):
        super().__init__(parent)
        self.weight_key = weight
        self.setObjectName("VariantCard")
        self.setMinimumSize(300, 110)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._font_id = -1
        
        try:
            metadata = inspect_font(font_path)
            detected_weight = metadata.weight_class
            detected_italic = metadata.is_italic
        except Exception:
            detected_weight, detected_italic = WEIGHT_TARGETS.get(weight, (400, False))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)
        
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        title_str = "Monospaced" if is_mono else weight.replace("_", " ").title()
        title = QLabel(title_str)
        title.setObjectName("CardTitle")
        title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        header_layout.addWidget(title, 1)

        if has_override:
            self.action_btn = FadeButton("\uE8E6", fade_radius=15)
            self.action_btn.clicked.connect(lambda: self.reset_requested.emit(self.weight_key))
        else:
            self.action_btn = FadeButton("\uE8E5", fade_radius=15)
            self.action_btn.clicked.connect(lambda: self.change_requested.emit(self.weight_key))
        self.action_btn.setObjectName("VariantBrowseBtn")
        self.action_btn.setCursor(Qt.PointingHandCursor)
        self.action_btn.setFixedSize(30, 30)
        header_layout.addWidget(self.action_btn, 0, Qt.AlignVCenter)

        layout.addLayout(header_layout)

        preview_text = "The quick brown fox jumps over the lazy dog"
        self.preview = QLabel(preview_text)
        self.preview.setObjectName("VariantPreview")
        self.preview.setWordWrap(True)
        self._font_id = QFontDatabase.addApplicationFont(str(font_path))
        if self._font_id >= 0:
            families = QFontDatabase.applicationFontFamilies(self._font_id)
            if families:
                style_str = "italic" if detected_italic else "normal"
                self.preview.setStyleSheet(f"font-family: '{families[0]}'; font-weight: {detected_weight}; font-style: {style_str};")
        layout.addWidget(self.preview)

        font_filename = Path(font_path).name if font_path else "System Default"
        meta_text = (
            f"Monospaced | {font_filename}"
            if is_mono
            else f"Weight {detected_weight}" + (" italic" if detected_italic else "") + f" | {font_filename}"
        )
        meta = QLabel(meta_text)
        meta.setObjectName("VariantMeta")
        meta.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(meta)

    def cleanup(self):
        if hasattr(self, "preview") and self.preview:
            self.preview.setStyleSheet("")
            self.preview.setFont(QFont())
        if self._font_id >= 0:
            QFontDatabase.removeApplicationFont(self._font_id)
            self._font_id = -1

class FontWizardApp(QMainWindow):
    def __init__(self, controller=None):
        super().__init__()
        self._action_buttons = ()
        self._variant_cards = []
        self.controller = controller or FontWizardController()
        self.setWindowTitle(APP_NAME)
        icon_path = get_asset_path("font-wizard-icon.png")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"fontwizard.{APP_NAME}.1")

        self.setMinimumSize(600, 500)
        self.resize(920, 720)
        self._selection_dirty = False
        self._apply_action = "apply"
        self._restore_action = "restore"
        self._browse_action = "select"
        self._op_thread = None
        self._closing = False
        self._entrance_done = False
        self._compact_layout = None
        self.is_dark = is_system_dark_mode()
        self._use_mica = sys.getwindowsversion().build >= 22000
        self._mica_applied = False
        if self._use_mica:
            self.setAttribute(Qt.WA_TranslucentBackground)

        central = QWidget()
        central.setObjectName("CentralWidget")
        self.setCentralWidget(central)
        self.main_layout = QVBoxLayout(central)
        self.main_layout.setContentsMargins(40, 36, 40, 36)
        self.main_layout.setSpacing(24)

        self._build_header()
        self._build_font_setup()
        self._build_variants()
        self.main_layout.addStretch(1)
        self._action_buttons = (self.browse_btn, self.apply_btn, self.restore_btn)

        self.browse_btn.clicked.connect(self.on_browse)
        self.apply_btn.clicked.connect(self.on_apply_action)
        self.restore_btn.clicked.connect(self.on_restore_action)

        self._sync_responsive_layout()
        self._apply_theme(self.is_dark)
        self.refresh_all()

    def _build_header(self):
        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(16)

        title_container = QWidget()
        tc_layout = QHBoxLayout(title_container)
        tc_layout.setContentsMargins(0, 0, 0, 0)
        tc_layout.setSpacing(14)
        tc_layout.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        logo_lbl = QLabel()
        logo_size = 64
        logo_lbl.setFixedSize(QSize(logo_size, logo_size))
        logo_lbl.setAlignment(Qt.AlignCenter)
        logo_path = get_asset_path("font-wizard-icon.png")
        if logo_path.exists():
            pixmap = QPixmap(str(logo_path))
            dpr = self.devicePixelRatioF()
            target_w = int(logo_size * dpr)
            target_h = int(logo_size * dpr)
            scaled_pixmap = pixmap.scaled(target_w, target_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            scaled_pixmap.setDevicePixelRatio(dpr)
            logo_lbl.setPixmap(scaled_pixmap)
        tc_layout.addWidget(logo_lbl, 0, Qt.AlignVCenter)

        text_container = QWidget()
        text_container.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(0)
        text_layout.setSizeConstraint(QLayout.SetFixedSize)

        title_row = QWidget()
        title_row_layout = QHBoxLayout(title_row)
        title_row_layout.setContentsMargins(0, 0, 0, 0)
        title_row_layout.setSpacing(8)

        title = QLabel(APP_NAME)
        title.setObjectName("AppTitle")
        title.setFixedHeight(34)
        title.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
        title.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        title_row_layout.addWidget(title, 0, Qt.AlignBottom)

        github_btn = QPushButton()
        github_btn.setObjectName("HeaderIconButton")
        github_btn.setFlat(True)
        github_icon_path = get_asset_path("github-mark.svg")
        if github_icon_path.exists():
            github_btn.setIcon(QIcon(str(github_icon_path)))
        github_btn.setIconSize(QSize(20, 20))
        github_btn.setCursor(Qt.PointingHandCursor)
        github_btn.setAccessibleName("GitHub")
        github_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(APP_GITHUB_URL)))
        title_row_layout.addWidget(github_btn, 0, Qt.AlignBottom)
        text_layout.addWidget(title_row, 0, Qt.AlignLeft)

        subtitle = QLabel("Customize your system font")
        subtitle.setObjectName("AppSubtitle")
        subtitle.setFixedHeight(20)
        subtitle.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        subtitle.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        text_layout.addWidget(subtitle, 0, Qt.AlignLeft)

        tc_layout.addWidget(text_container, 0, Qt.AlignVCenter)
        header_layout.addWidget(title_container)

        self.banner = StatusBanner()
        header_layout.addWidget(self.banner)
        self.main_layout.addWidget(header)

    def _build_font_setup(self):
        self.setup_card = QFrame(objectName="SetupCard")
        self.setup_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        
        self.setup_layout = QVBoxLayout(self.setup_card)
        self.setup_layout.setContentsMargins(20, 12, 20, 12)
        self.setup_layout.setSpacing(0)

        # Main System Font Section
        self.interface_row = QWidget()
        self.interface_layout = QHBoxLayout(self.interface_row)
        self.interface_layout.setContentsMargins(4, 8, 4, 8)
        self.interface_layout.setSpacing(16)

        font_text = QVBoxLayout()
        font_text.setContentsMargins(0, 0, 0, 0)
        font_text.setSpacing(4)

        title = QLabel("System Font")
        title.setObjectName("CardTitle")
        font_text.addWidget(title)

        self.cur_font_lbl = QLabel("No font selected")
        self.cur_font_lbl.setObjectName("SelectedFont")
        self.cur_font_lbl.setWordWrap(True)
        self.cur_font_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
        font_text.addWidget(self.cur_font_lbl)

        self.browse_btn = FadeButton("Select Font")
        self.browse_btn.setFixedHeight(30)
        self.browse_btn.setMinimumWidth(110)
        self.browse_btn.setCursor(Qt.PointingHandCursor)
        self._set_button_role(self.browse_btn, "secondary")

        self.apply_btn = FadeButton("Apply Changes")
        self.apply_btn.setFixedHeight(32)
        self.apply_btn.setFixedWidth(180)
        self.apply_btn.setCursor(Qt.PointingHandCursor)

        self.restore_btn = FadeButton("Restore Original Fonts")
        self.restore_btn.setFixedHeight(32)
        self.restore_btn.setFixedWidth(180)
        self.restore_btn.setCursor(Qt.PointingHandCursor)

        self.interface_layout.addLayout(font_text, 1)
        self.interface_layout.addWidget(self.browse_btn, 0, Qt.AlignVCenter)
        self.interface_layout.addWidget(self.apply_btn, 0, Qt.AlignVCenter)
        self.interface_layout.addWidget(self.restore_btn, 0, Qt.AlignVCenter)

        self.setup_layout.addWidget(self.interface_row)
        self.main_layout.addWidget(self.setup_card)

        self.error_banner = StatusBanner()
        self.error_banner.hide()
        self.main_layout.addWidget(self.error_banner)

    def _build_variants(self):
        self.variants_header = QWidget()
        v_layout = QHBoxLayout(self.variants_header)
        v_layout.setContentsMargins(0, 0, 0, 0)
        v_layout.setSpacing(12)

        text_lbl = QLabel("Style Variants", objectName="SectionHeader")
        self.variant_count_lbl = QLabel("")
        self.variant_count_lbl.setObjectName("SectionMeta")
        v_layout.addWidget(text_lbl)
        v_layout.addWidget(self.variant_count_lbl)
        v_layout.addStretch()
        self.main_layout.addWidget(self.variants_header)

        self.empty_variants = QFrame(objectName="EmptyState")
        self.empty_variants.setMinimumHeight(140)
        self.empty_variants.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        empty_layout = QVBoxLayout(self.empty_variants)
        empty_layout.setContentsMargins(24, 24, 24, 24)
        empty_layout.setSpacing(8)
        empty_title = QLabel("No style variants yet")
        empty_title.setObjectName("CardTitle")
        empty_desc = QLabel("Select a font to preview detected styles.")
        empty_desc.setObjectName("CardDesc")
        empty_desc.setWordWrap(True)
        empty_layout.addWidget(empty_title)
        empty_layout.addWidget(empty_desc)
        empty_layout.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.empty_variants, 1000)

        self.weight_scroll = QScrollArea()
        self.weight_scroll.setWidgetResizable(True)
        self.weight_scroll.setFrameShape(QFrame.NoFrame)
        self.weight_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.weight_scroll.hide()

        self.weight_widget = QWidget()
        self.weight_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.weight_layout = FlowLayout(self.weight_widget, margin=0, spacing=16)
        self.weight_layout.setContentsMargins(0, 0, 0, 0)

        self.weight_scroll.setWidget(self.weight_widget)
        self.main_layout.addWidget(self.weight_scroll, 1000)

    def _set_button_role(self, button, role):
        if button.property("buttonRole") == role:
            return
        button.setProperty("buttonRole", role)
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()
        if hasattr(button, "set_fade_colors"):
            colors = get_theme_colors(self.is_dark)
            if role in ("primary", "warning"):
                button.set_fade_colors(
                    QColor(colors["accent_hover"]),
                    QColor(colors["accent"]).darker(112),
                )
            else:
                button.set_fade_colors(
                    _parse_qss_color(colors["bg_button_hover"]),
                    _parse_qss_color(colors["bg_button_pressed"]),
                )

    def _apply_widget_theme(self):
        for button in self._action_buttons:
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()

        for card in getattr(self, "_variant_cards", ()):
            self._apply_card_fade(card)

    def _apply_theme(self, is_dark: bool):
        self.is_dark = is_dark
        mica_active = False
        if self._use_mica and self.isVisible():
            mica_active = apply_native_mica(int(self.winId()), is_dark)
            if mica_active:
                self._mica_applied = True
        self.setStyleSheet(get_wizard_stylesheet(is_dark, mica_active))
        self._apply_widget_theme()

    def showEvent(self, event):
        super().showEvent(event)
        if self._use_mica and not self._mica_applied:
            if apply_native_mica(int(self.winId()), self.is_dark):
                self._mica_applied = True
                self.setStyleSheet(get_wizard_stylesheet(self.is_dark, True))
                self._apply_widget_theme()
        if not self._entrance_done:
            self._entrance_done = True
            effect = QGraphicsOpacityEffect(self.centralWidget())
            effect.setOpacity(0.0)
            self.centralWidget().setGraphicsEffect(effect)
            self._entrance_anim = QPropertyAnimation(effect, b"opacity", self)
            self._entrance_anim.setDuration(220)
            self._entrance_anim.setStartValue(0.0)
            self._entrance_anim.setEndValue(1.0)
            self._entrance_anim.setEasingCurve(QEasingCurve.OutCubic)

            def _remove_entrance_effect():
                self.centralWidget().setGraphicsEffect(None)

            self._entrance_anim.finished.connect(_remove_entrance_effect)
            self._entrance_anim.start()

    def _sync_theme(self):
        current_dark = is_system_dark_mode()
        if current_dark != self.is_dark:
            self._apply_theme(current_dark)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_responsive_layout()
        self._sync_variant_layout_height()

    def _sync_responsive_layout(self):
        if not hasattr(self, "interface_layout"):
            return

        is_compact = self.width() < 640
        if self._compact_layout == is_compact:
            return

        self._compact_layout = is_compact
        if is_compact:
            self.main_layout.setContentsMargins(20, 20, 20, 20)
            self.main_layout.setSpacing(16)
        else:
            self.main_layout.setContentsMargins(40, 36, 40, 36)
            self.main_layout.setSpacing(24)
        self.interface_layout.setDirection(QBoxLayout.LeftToRight)

        self.setup_card.updateGeometry()
        self.banner.updateGeometry()

    def _sync_variant_layout_height(self):
        if not hasattr(self, "weight_scroll"):
            return
        if not self.weight_scroll.isVisible() or self.weight_layout.count() == 0:
            self.weight_widget.setMinimumHeight(0)
            self.weight_widget.setMaximumHeight(16777215)
            return

        viewport_width = self.weight_scroll.viewport().width()
        if viewport_width <= 0:
            viewport_width = self.weight_scroll.width()
        content_height = self.weight_layout.heightForWidth(viewport_width)
        self.weight_widget.setMinimumHeight(content_height)
        self.weight_widget.setMaximumHeight(content_height)
        self.weight_widget.updateGeometry()

    def nativeEvent(self, event_type, message):
        if event_type != b"windows_generic_MSG":
            return super().nativeEvent(event_type, message)

        try:
            msg = wintypes.MSG.from_address(int(message))
        except Exception:
            return super().nativeEvent(event_type, message)

        if msg.message == WM_DWMCOLORIZATIONCOLORCHANGED:
            self._apply_theme(self.is_dark)
        elif msg.message in {WM_SETTINGCHANGE, WM_THEMECHANGED}:
            self._sync_theme()

        return super().nativeEvent(event_type, message)

    def _show_error(self, title, message, icon="\uE7BA", color="danger"):
        colors = get_theme_colors(self.is_dark)
        self.error_banner.set_icon(icon, colors.get(color, colors["danger"]))
        self.error_banner.set_content(title, message)
        self.error_banner.show()

    def _hide_error(self):
        if hasattr(self, "error_banner"):
            self.error_banner.hide()

    def _friendly_font_error(self, exc):
        text = str(exc)
        if ".otf" in text.lower():
            return "OpenType (.otf) fonts are not supported. Choose a static .ttf font"
        if "unsupported font type" in text.lower():
            return "This file type is not supported. Choose a static .ttf font"
        if "variable" in text.lower():
            return "Variable fonts are not supported. Choose a static .ttf font"
        if "truetype-outline" in text.lower() or "unable to read" in text.lower():
            return "Unable to read the font file. Choose a valid static .ttf font"
        return text

    def on_browse(self):
        if self._browse_action == "restart":
            self.on_restart()
            return
        font_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Static TrueType Font",
            "",
            "Font files (*.ttf *.otf);;All files (*)",
        )
        if font_path:
            try:
                self.controller.set_regular_font(font_path)
            except (ValueError, OSError) as exc:
                self._show_error("Font not supported", self._friendly_font_error(exc), color="warning")
                return
            self._selection_dirty = True
            self.refresh_all()

    def _on_change_variant_font(self, weight_key):
        title_str = "Monospaced" if weight_key == "monospace" else weight_key.replace("_", " ").title()
        font_path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select Font File for {title_str}",
            "",
            "Font files (*.ttf *.otf);;All files (*)",
        )
        if font_path:
            try:
                if weight_key == "monospace":
                    self.controller.set_monospace_font(font_path)
                elif weight_key == "regular":
                    self.controller.set_regular_font(font_path)
                else:
                    metadata = inspect_font(font_path)
                    if metadata.is_variable:
                        raise ValueError(
                            "Variable fonts are not supported. Choose a static .ttf font"
                        )
                    self.controller.selection.paths[weight_key] = font_path
                    self.controller.selection.labels[weight_key] = "manual"
                self._selection_dirty = True
                self.refresh_all()
            except (ValueError, OSError) as exc:
                self._show_error("Font not supported", self._friendly_font_error(exc), color="warning")

    def _on_reset_variant_font(self, weight_key):
        if weight_key == "monospace":
            self.controller.clear_monospace_font()
        else:
            self.controller.selection.labels[weight_key] = "auto-detected"
            regular_path = self.controller.selection.paths.get("regular")
            if regular_path:
                self.controller.set_regular_font(regular_path)
        self._selection_dirty = True
        self.refresh_all()

    def on_apply_action(self):
        if self._apply_action == "restart":
            self.on_restart()
            return
        self.on_apply()

    def on_restore_action(self):
        if self._restore_action == "restart":
            self.on_restart()
            return
        self.on_restore()

    def _run_operation(self, func, btn, text):
        if self._op_thread and self._op_thread.isRunning():
            return

        for button in self._action_buttons:
            button.setEnabled(False)
        btn.setText(text)
        self._set_button_role(btn, "warning")
        btn.set_busy(True)
        self._op_thread = OperationThread(func, self)
        self._op_thread.done.connect(lambda r: self._on_operation_done(r, btn))
        self._op_thread.finished.connect(self._op_thread.deleteLater)
        self._op_thread.start()

    def _on_operation_done(self, result, btn):
        self._op_thread = None
        btn.set_busy(False)

        if not isinstance(result, OperationResult):
            result = OperationResult(
                False,
                "The operation finished with an unexpected result.",
                [repr(result)],
            )

        if self._closing:
            return

        if btn == self.apply_btn and result.success:
            self._selection_dirty = False

        error_info = None
        if not result.success:
            error_info = (
                "Apply failed" if btn is self.apply_btn else "Restore failed",
                result.message,
                "\uE783",
            )
        self.refresh_all()
        if error_info:
            self._show_error(*error_info)

    def closeEvent(self, event):
        self._closing = True
        thread = self._op_thread
        if thread is not None and thread.isRunning():
            thread.wait(2000)
        super().closeEvent(event)

    def on_apply(self):
        self._run_operation(self.controller.apply, self.apply_btn, "Applying\u2026")

    def on_restore(self):
        self._run_operation(self.controller.restore, self.restore_btn, "Restoring\u2026")

    def on_restart(self):
        try:
            subprocess.run(["shutdown", "/r", "/t", "0"], check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception:
            self._show_error(
                "Restart failed",
                "Could not initiate Windows restart. Please restart your computer manually to finish the setup.",
                "\uE777",
            )

    def refresh_all(self):
        report = self.controller.refresh_preflight()
        colors = get_theme_colors(self.is_dark)
        self._hide_error()

        is_pending = report.install_state in ("pending_reboot_apply", "pending_reboot_recovery")
        if report.install_state == "managed":
            self.banner.set_icon("\uE73E", colors["accent"])
        elif is_pending:
            self.banner.set_icon("\uE777", colors["warning"])
        elif report.issues:
            self.banner.set_icon("\uE783", colors["danger"])
        else:
            self.banner.set_icon("\uE946", colors["accent"])

        self.banner.set_content(report.headline, report.summary)

        regular_font = self.controller.selection.paths.get("regular")
        can_apply = report.can_apply_changes and regular_font is not None
        has_selected_font = regular_font is not None
        is_apply_pending = report.install_state == "pending_reboot_apply"
        is_recovery_pending = report.install_state == "pending_reboot_recovery"

        if is_recovery_pending:
            self._browse_action = "select"
            self._apply_action = "apply"
            self._restore_action = "restart"
            browse_text = "Select Font"
            apply_text = "Apply Changes"
            restore_text = "Restart"
            apply_visible = False
            restore_visible = True
        elif is_apply_pending:
            self._browse_action = "select"
            self._restore_action = "restore"
            if has_selected_font and self._selection_dirty:
                self._apply_action = "apply"
                apply_text = "Apply Changes"
            else:
                self._apply_action = "restart"
                apply_text = "Restart"
            browse_text = "Select Font"
            restore_text = "Restore Original Fonts"
            apply_visible = True
            restore_visible = False
        else:
            self._browse_action = "select"
            self._apply_action = "apply"
            self._restore_action = "restore"
            browse_text = "Select Font"
            apply_text = "Apply Changes"
            restore_text = "Restore Original Fonts"
            apply_visible = has_selected_font
            restore_visible = not has_selected_font

        action_is_restart = self._apply_action == "restart"
        apply_available = apply_visible and (action_is_restart or can_apply)
        restore_available = restore_visible and report.can_restore_defaults

        self.browse_btn.setText(browse_text)
        self.browse_btn.setEnabled(True)
        self.browse_btn.setVisible(True)

        self.apply_btn.setText(apply_text)
        self.apply_btn.setEnabled(apply_available)
        self.apply_btn.setVisible(apply_visible)

        self.restore_btn.setEnabled(restore_available)
        self.restore_btn.setVisible(restore_visible)
        self.restore_btn.setText(restore_text)

        browse_role = "warning" if self._browse_action == "restart" else ("secondary" if has_selected_font else "primary")
        self._set_button_role(self.browse_btn, browse_role)
        self._set_button_role(self.apply_btn, "warning" if action_is_restart else "primary")
        self._set_button_role(self.restore_btn, "warning" if self._restore_action == "restart" else "primary")

        self.cur_font_lbl.setText(Path(regular_font).name if regular_font else "No font selected")

        self._variant_cards = []
        while self.weight_layout.count():
            item = self.weight_layout.takeAt(0)
            widget = item.widget()
            if widget:
                if hasattr(widget, "cleanup"):
                    widget.cleanup()
                widget.hide()
                widget.deleteLater()

        cards_added = 0
        for weight, font_path in self.controller.selection.paths.items():
            if font_path and weight != "variable":
                try:
                    has_override = (
                        weight != "regular"
                        and self.controller.selection.labels.get(weight) == "manual"
                    )
                    card = WeightCard(weight, font_path, has_override=has_override)
                    card.change_requested.connect(self._on_change_variant_font)
                    card.reset_requested.connect(self._on_reset_variant_font)
                    self.weight_layout.addWidget(card)
                    card.show()
                    self._apply_card_fade(card)
                    self._variant_cards.append(card)
                    cards_added += 1
                except (ValueError, OSError):
                    pass

        if has_selected_font:
            mono_path = self.controller.monospace_font_path or regular_font
            if mono_path:
                try:
                    mono_card = WeightCard(
                        "monospace",
                        mono_path,
                        is_mono=True,
                        has_override=self.controller.monospace_font_path is not None,
                    )
                    mono_card.change_requested.connect(self._on_change_variant_font)
                    mono_card.reset_requested.connect(self._on_reset_variant_font)
                    self.weight_layout.addWidget(mono_card)
                    mono_card.show()
                    self._apply_card_fade(mono_card)
                    self._variant_cards.append(mono_card)
                    cards_added += 1
                except (ValueError, OSError):
                    pass

        show_variant_section = has_selected_font and not is_recovery_pending
        has_variants = show_variant_section and cards_added > 0
        self.variant_count_lbl.setText(f"{cards_added} styles" if has_variants else "No preview")
        self.variants_header.setVisible(show_variant_section)
        self.empty_variants.setVisible(show_variant_section and not has_variants)
        self.weight_scroll.setVisible(has_variants)
        if has_variants:
            self.weight_widget.show()
        self._sync_variant_layout_height()
        self.weight_layout.activate()
        self.weight_widget.update()

    def _apply_card_fade(self, card):
        colors = get_theme_colors(self.is_dark)
        card.set_fade_colors(
            _parse_qss_color(colors["bg_card_hover"]),
            _parse_qss_color(colors["bg_button_pressed"]),
        )
        if hasattr(card, "action_btn"):
            card.action_btn.set_fade_colors(
                _parse_qss_color(colors["bg_button_hover"]),
                _parse_qss_color(colors["bg_button_pressed"]),
            )

    def run(self):
        self.show()
        return QApplication.instance().exec()

if __name__ == "__main__":
    from main import main
    sys.exit(main())
