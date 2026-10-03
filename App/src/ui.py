import ctypes
import math
import re
import subprocess
import sys
import time
import winreg
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QSize, QPoint, QPointF, QRect, QRectF, QUrl, QTimer, QEvent, QPropertyAnimation, QAbstractAnimation, QEasingCurve, QVariantAnimation
from PySide6.QtGui import QDesktopServices, QFont, QFontDatabase, QFontMetrics, QIcon, QImage, QLinearGradient, QRadialGradient, QColor, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QBoxLayout,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QLayout,
)

from settings import APP_GITHUB_URL, APP_NAME, WEIGHT_TARGETS, GITHUB_FONTS_REPO, GITHUB_FONTS_BRANCH, GITHUB_FONTS_URL
from core import FontWizardController
from font_detection import inspect_font
from operation import OperationResult

WM_SETTINGCHANGE = 0x001A
WM_THEMECHANGED = 0x031A
WM_DWMCOLORIZATIONCOLORCHANGED = 0x0320

def is_windows_11() -> bool:
    try:
        winver = sys.getwindowsversion()
        return winver.major == 10 and winver.build >= 22000
    except Exception:
        return False

def get_windows_accent_color(is_dark: bool = True) -> tuple[str, str, str, str]:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Accent") as key:
            palette, _ = winreg.QueryValueEx(key, "AccentPalette")
            if len(palette) >= 32:
                colors = []
                for i in range(0, 32, 4):
                    chunk = palette[i:i+4]
                    colors.append(f"#{chunk[0]:02X}{chunk[1]:02X}{chunk[2]:02X}")
                if is_dark:
                    return colors[3], colors[2], "#FFFFFF", colors[1]
                else:
                    return colors[4], colors[3], "#FFFFFF", colors[5]
    except Exception:
        pass
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\DWM") as key:
            val, _ = winreg.QueryValueEx(key, "AccentColor")
            r = val & 0xFF
            g = (val >> 8) & 0xFF
            b = (val >> 16) & 0xFF
            if is_dark:
                r_h = min(255, int(r * 1.25 + 30))
                g_h = min(255, int(g * 1.25 + 30))
                b_h = min(255, int(b * 1.25 + 30))
                r_i = min(255, int(r * 1.45 + 50))
                g_i = min(255, int(g * 1.45 + 50))
                b_i = min(255, int(b * 1.45 + 50))
            else:
                r_h = max(0, int(r * 0.85))
                g_h = max(0, int(g * 0.85))
                b_h = max(0, int(b * 0.85))
                r_i = r
                g_i = g
                b_i = b
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            text_color = "#000000" if lum > 160 else "#FFFFFF"
            return f"#{r:02X}{g:02X}{b:02X}", f"#{r_h:02X}{g_h:02X}{b_h:02X}", text_color, f"#{r_i:02X}{g_i:02X}{b_i:02X}"
    except Exception:
        pass
    return ("#2993CC", "#59C5FF", "#FFFFFF", "#80D2FF") if is_dark else ("#006499", "#2993CC", "#FFFFFF", "#004B73")

def get_theme_colors(is_dark: bool, is_win11: bool = True) -> dict[str, str]:
    accent, accent_hover, accent_text, accent_icon = get_windows_accent_color(is_dark)
    if is_dark:
        return {
            "bg_window": "transparent" if is_win11 else "#202020",
            "bg_card": "rgba(255, 255, 255, 0.04)" if is_win11 else "#2B2B2B",
            "bg_card_hover": "rgba(255, 255, 255, 0.07)" if is_win11 else "#353535",
            "bg_button": "rgba(255, 255, 255, 0.06)" if is_win11 else "#2D2D2D",
            "bg_button_hover": "rgba(255, 255, 255, 0.09)" if is_win11 else "#383838",
            "bg_button_pressed": "rgba(255, 255, 255, 0.03)" if is_win11 else "#242424",
            "border_card": "rgba(255, 255, 255, 0.08)" if is_win11 else "#383838",
            "border_button": "rgba(255, 255, 255, 0.08)" if is_win11 else "#383838",

            "text_primary": "#FFFFFF",
            "text_secondary": "rgba(255, 255, 255, 0.78)" if is_win11 else "#CCCCCC",
            "text_muted": "rgba(255, 255, 255, 0.55)" if is_win11 else "#888888",
            "accent": accent,
            "accent_hover": accent_hover,
            "accent_text": accent_text,
            "accent_icon": accent_icon,
            "success": accent,
            "success_hover": accent_hover,
            "warning": accent,
            "warning_hover": accent_hover,
            "warning_text": accent_text,
            "danger": accent,
            "danger_hover": accent_hover,
            "danger_text": accent_text,
            "bg_dialog": "#202020",
        }
    return {
        "bg_window": "transparent" if is_win11 else "#F3F3F3",
        "bg_card": "rgba(255, 255, 255, 0.7)" if is_win11 else "#FFFFFF",
        "bg_card_hover": "rgba(0, 0, 0, 0.05)" if is_win11 else "#F0F0F0",
        "bg_button": "rgba(255, 255, 255, 0.7)" if is_win11 else "#E5E5E5",
        "bg_button_hover": "rgba(0, 0, 0, 0.07)" if is_win11 else "#D8D8D8",
        "bg_button_pressed": "rgba(0, 0, 0, 0.13)" if is_win11 else "#C4C4C4",
        "border_card": "rgba(0, 0, 0, 0.06)" if is_win11 else "#E0E0E0",
        "border_button": "rgba(0, 0, 0, 0.06)" if is_win11 else "#D0D0D0",

        "text_primary": "rgba(0, 0, 0, 0.9)" if is_win11 else "#1A1A1A",
        "text_secondary": "rgba(0, 0, 0, 0.6)" if is_win11 else "#555555",
        "text_muted": "rgba(0, 0, 0, 0.45)" if is_win11 else "#777777",
        "accent": accent,
        "accent_hover": accent_hover,
        "accent_text": accent_text,
        "accent_icon": accent_icon,
        "success": accent,
        "success_hover": accent_hover,
        "warning": accent,
        "warning_hover": accent_hover,
        "warning_text": accent_text,
        "danger": accent,
        "danger_hover": accent_hover,
        "danger_text": accent_text,
        "bg_dialog": "#F3F3F3",
    }

def get_asset_path(name):
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets" / name
    return Path(__file__).parent / "assets" / name

class MARGINS(ctypes.Structure):
    _fields_ = [
        ("cxLeftWidth", ctypes.c_int),
        ("cxRightWidth", ctypes.c_int),
        ("cyTopHeight", ctypes.c_int),
        ("cyBottomHeight", ctypes.c_int),
    ]

def apply_native_mica(hwnd_id, is_dark):
    try:
        dwmapi = ctypes.windll.dwmapi
        hwnd = wintypes.HWND(hwnd_id)
        dark_mode = ctypes.c_int(1 if is_dark else 0)
        res = dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark_mode), ctypes.sizeof(dark_mode))
        if res != 0:
            dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(dark_mode), ctypes.sizeof(dark_mode))

        if is_windows_11():
            backdrop_type = ctypes.c_int(2)  # 2 for Mica (DWMSBT_MAINWINDOW on Win 11 22H2 / 23H2 / 24H2)
            res_backdrop = dwmapi.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(backdrop_type), ctypes.sizeof(backdrop_type))
            if res_backdrop != 0:
                # Fallback for Windows 11 Build 22000 (21H2)
                mica_val = ctypes.c_int(1)
                dwmapi.DwmSetWindowAttribute(hwnd, 1029, ctypes.byref(mica_val), ctypes.sizeof(mica_val))

            margins = MARGINS(-1, -1, -1, -1)
            dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
            caption_color = ctypes.c_int(0xFFFFFFFE)
            dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption_color), ctypes.sizeof(caption_color))
    except Exception:
        pass

def is_system_dark_mode():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return value == 0
    except Exception:
        return True


def _solid_color(foreground, background):
    match = re.match(
        r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([0-9.]+)\s*\)",
        foreground,
    )
    if not match:
        return foreground
    red, green, blue, alpha = (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)),
        float(match.group(4)),
    )
    base = background.lstrip("#")
    base_red, base_green, base_blue = (int(base[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02X%02X%02X" % (
        round(red * alpha + base_red * (1.0 - alpha)),
        round(green * alpha + base_green * (1.0 - alpha)),
        round(blue * alpha + base_blue * (1.0 - alpha)),
    )


def _opaque_window_bg(is_dark):
    return "#202020" if is_dark else "#F3F3F3"


def _accent_signature():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Accent") as key:
            palette, _ = winreg.QueryValueEx(key, "AccentPalette")
            return bytes(bytearray(palette))
    except Exception:
        pass
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\DWM") as key:
            value, _ = winreg.QueryValueEx(key, "AccentColor")
            return int(value).to_bytes(4, "little", signed=False)
    except Exception:
        return b""


_github_icon_cache = {}

def get_wizard_stylesheet(is_dark: bool) -> str:
    is_win11 = is_windows_11()
    colors = get_theme_colors(is_dark, is_win11)
    win_bg = colors["bg_window"]
    font_stack = "'Segoe UI Variable Text', 'Segoe UI', sans-serif" if is_win11 else "'Segoe UI', sans-serif"
    title_font_stack = "'Segoe UI Variable Display', 'Segoe UI', sans-serif" if is_win11 else "'Segoe UI', sans-serif"

    return f"""
    QMainWindow {{ background-color: {win_bg}; }}
    QWidget#CentralWidget {{ background-color: {win_bg}; }}
    QScrollArea#WeightScrollArea {{ 
        background: transparent; 
        background-color: transparent; 
        border: none; 
    }}
    QWidget#WeightContainer {{ 
        background: transparent; 
        background-color: transparent; 
        border: none; 
    }}
    QScrollArea {{ 
        background: transparent; 
        background-color: transparent; 
        border: none; 
    }}
    QWidget {{ 
        color: {colors["text_primary"]}; 
        font-family: {font_stack}; 
        font-size: 14px; 
    }}
    QDialog, QMessageBox, QToolTip {{ 
        background-color: {colors["bg_dialog"]}; 
        border: 1px solid {colors["border_card"]}; 
        border-radius: 8px;
    }}
    #AppTitle {{ font-size: 28px; font-weight: 600; font-family: {title_font_stack}; letter-spacing: -0.5px; }}
    #AppSubtitle {{ color: {colors["text_secondary"]}; font-size: 14px; margin-top: 0px; }}
    #SectionHeader {{ font-weight: 600; font-size: 18px; padding: 0; font-family: {title_font_stack}; }}
    #SectionMeta {{ color: {colors["text_muted"]}; font-size: 13px; }}
    
    #Banner, #SetupCard, #VariantCard, #EmptyState {{ 
        background-color: {colors["bg_card"]}; 
        border: 1px solid {colors["border_card"]}; 
        border-radius: 8px; 
    }}
    #VariantCard:hover {{ 
        background-color: {colors["bg_card_hover"]}; 
    }}
    #BannerIcon {{ font-family: 'Segoe Fluent Icons'; font-size: 20px; }}
    #BannerTitle {{ font-size: 15px; font-weight: 600; }}
    #BannerText {{ font-size: 14px; color: {colors["text_secondary"]}; }}
    
    #CardTitle {{ font-weight: 600; font-size: 15px; }}
    #CardDesc {{ color: {colors["text_secondary"]}; font-size: 14px; }}
    #SelectedFont {{ color: {colors["text_secondary"]}; font-size: 14px; }}
    #VariantPreview {{ color: {colors["text_primary"]}; font-size: 18px; }}
    #VariantMeta {{ color: {colors["text_muted"]}; font-size: 12px; }}
    
    #CardChangeBtn {{
        background-color: transparent;
        border: none;
        border-radius: 4px;
        padding: 0 0 2px 0;
        min-width: 28px;
        max-width: 28px;
        min-height: 28px;
        max-height: 28px;
        font-family: 'Segoe Fluent Icons', 'Segoe MDL2 Assets';
        font-size: 18px;
        font-weight: 400;
        color: {colors["accent_icon"]};
        outline: none;
    }}
    #CardChangeBtn:hover {{
        background-color: {colors["bg_button_hover"]};
        color: {colors["accent_hover"]};
    }}
    #CardChangeBtn:pressed {{
        background-color: {colors["bg_button_pressed"]};
    }}
    
    QPushButton {{ 
        background-color: {colors["bg_button"]}; 
        border: 1px solid {colors["border_button"]}; 
        border-radius: 4px; 
        padding: 0 16px; 
        min-height: 34px; 
        max-height: 34px; 
        font-weight: 600; 
        font-size: 13px;
        outline: none;
    }}
    QPushButton:focus {{ outline: none; }}
    #ActionButton {{
        background-color: {colors["bg_button"]};
        border: 1px solid {colors["border_button"]};
        border-radius: 4px;
    }}
    #ActionButton[buttonRole="primary"] {{
        background-color: {colors["accent"]};
        border: 1px solid {colors["accent"]};
    }}
    #ActionButton:hover {{
        background-color: {colors["bg_button_hover"]};
    }}
    #ActionButton[buttonRole="primary"]:hover {{
        background-color: {colors["accent_hover"]};
        border-color: {colors["accent_hover"]};
    }}
    #ActionButton[pressed="true"] {{
        background-color: {colors["bg_button_pressed"]};
    }}
    #ActionButton:disabled {{
        background-color: {colors["bg_card"]};
        border-color: {colors["border_card"]};
    }}
    #ActionButton #ActionIconLocal {{
        color: {colors["accent_icon"]};
        background: transparent;
        border: none;
        font-family: 'Segoe MDL2 Assets';
        font-size: 18px;
        font-weight: 400;
    }}
    #ActionButton #ActionIconFetch {{
        color: {colors["accent_icon"]};
        background: transparent;
        border: none;
        font-family: 'Segoe MDL2 Assets';
        font-size: 24px;
        font-weight: 400;
    }}
    #ActionButton #ActionText {{
        color: {colors["text_primary"]};
        background: transparent;
        border: none;
        font-family: 'Segoe UI';
        font-size: 13px;
        font-weight: 700;
    }}
    QPushButton:hover {{ background-color: {colors["bg_button_hover"]}; }}
    QPushButton:pressed {{ background-color: {colors["bg_button_pressed"]}; }}
    QPushButton:disabled {{ color: {colors["text_muted"]}; background-color: {colors["bg_card"]}; border-color: {colors["border_card"]}; }}
    
    QPushButton[buttonRole="primary"] {{ 
        background-color: {colors["accent"]}; 
        border: 1px solid {colors["accent"]}; 
        color: {colors["accent_text"]}; 
        outline: none;
    }}
    QPushButton[buttonRole="primary"]:hover {{ background-color: {colors["accent_hover"]}; border-color: {colors["accent_hover"]}; }}
    
    QPushButton[buttonRole="warning"] {{ 
        background-color: {colors["accent"]}; 
        border: 1px solid {colors["accent"]}; 
        color: {colors["accent_text"]}; 
        outline: none;
    }}
    QPushButton[buttonRole="warning"]:hover {{ 
        background-color: {colors["accent_hover"]}; 
        border-color: {colors["accent_hover"]}; 
    }}
    
    QPushButton[buttonRole="danger"] {{ 
        background-color: {colors["bg_card"]}; 
        border: 1px solid {colors["border_card"]}; 
        color: {colors["text_primary"]}; 
    }}
    QPushButton[buttonRole="danger"]:hover {{ 
        background-color: {colors["bg_button_hover"]}; 
        border-color: {colors["border_button"]}; 
    }}
    QPushButton[buttonRole="secondary"] {{ 
        background-color: {colors["bg_card"]}; 
        color: {colors["text_primary"]}; 
    }}
    QPushButton[buttonRole="secondary"]:hover {{ background-color: {colors["bg_button_hover"]}; }}
    QPushButton:disabled,
    QPushButton[buttonRole="primary"]:disabled,
    QPushButton[buttonRole="warning"]:disabled,
    QPushButton[buttonRole="danger"]:disabled,
    QPushButton[buttonRole="secondary"]:disabled {{ 
        color: {colors["text_muted"]}; 
        background-color: {colors["bg_card"]}; 
        border-color: {colors["border_card"]}; 
    }}
    #HeaderIconButton {{
        background-color: transparent;
        border: none;
        padding: 0;
        min-width: 32px;
        max-width: 32px;
        min-height: 32px;
        max-height: 32px;
        border-radius: 4px;
    }}
    #HeaderIconButton:hover {{
        background-color: {colors["bg_button_hover"]};
    }}
    #HeaderIconButton:pressed {{
        background-color: {colors["bg_button_pressed"]};
    }}
    
    QScrollBar:vertical {{ border: none; background: transparent; width: 12px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {colors["border_card"]}; border-radius: 3px; min-height: 30px; margin: 0 3px; }}
    QScrollBar::handle:vertical:hover {{ background: {colors["text_secondary"]}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ border: none; background: none; height: 0px; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
    #CloudPanel {{
        background-color: {colors["bg_card"]};
        border: 1px solid {colors["border_card"]};
        border-radius: 8px;
    }}
    #CloudPanel #CloudTitle {{
        font-weight: 600;
        font-size: 14px;
        color: {colors["text_primary"]};
    }}
    #CloudPanel #CloudMeta {{
        color: {colors["text_muted"]};
        font-size: 12px;
    }}
    #CloudPanel QPushButton {{
        background-color: {colors["bg_button"]};
        border: 1px solid {colors["border_button"]};
        border-radius: 4px;
        color: {colors["text_primary"]};
        font-family: 'Segoe UI';
        font-size: 13px;
        font-weight: 600;
        padding: 6px 12px;
    }}
    #CloudPanel QPushButton:hover {{
        background-color: {colors["bg_button_hover"]};
    }}
    #CloudPanel QPushButton:disabled {{
        color: {colors["text_muted"]};
        background-color: {colors["bg_card"]};
        border-color: {colors["border_card"]};
    }}
    #CloudPanel #IconBtn {{
        font-family: 'Segoe Fluent Icons', 'Segoe MDL2 Assets';
        font-size: 10px;
        font-weight: 400;
        color: {colors["accent_icon"]};
        background-color: transparent;
        border: none;
        padding: 0;
        min-width: 28px;
        max-width: 28px;
        min-height: 28px;
        max-height: 28px;
    }}
    #CloudPanel #IconBtn:hover {{
        background-color: {colors["bg_button_hover"]};
    }}
    #CloudPanel #IconBtn:disabled {{
        color: {colors["text_muted"]};
        background-color: {colors["bg_card"]};
        border-color: {colors["border_card"]};
    }}
    #CloudPanel #IconBtnRefresh {{
        font-family: 'Segoe Fluent Icons', 'Segoe MDL2 Assets';
        font-size: 13px;
        font-weight: 400;
        color: {colors["accent_icon"]};
        background-color: transparent;
        border: none;
        padding: 0;
        min-width: 28px;
        max-width: 28px;
        min-height: 28px;
        max-height: 28px;
    }}
    #CloudPanel #IconBtnRefresh:hover {{
        background-color: {colors["bg_button_hover"]};
    }}
    #CloudPanel #IconBtnRefresh:disabled {{
        color: {colors["text_muted"]};
        background-color: {colors["bg_card"]};
        border-color: {colors["border_card"]};
    }}
    #CloudFolderRow {{
        background-color: {colors["bg_button"]};
        border: 1px solid {colors["border_button"]};
        border-radius: 6px;
        text-align: left;
        padding: 0px;
    }}
    #CloudFolderRow:hover {{
        background-color: {colors["bg_button_hover"]};
        border-color: {colors["accent"]};
    }}
    #CloudFolderRow:disabled {{
        background-color: {colors["bg_card"]};
        border-color: {colors["border_card"]};
    }}
    #CloudFolderName {{
        color: {colors["text_secondary"]};
        font-family: 'Segoe UI';
        font-size: 13px;
        font-weight: 600;
        background: transparent;
    }}
    #CloudFolderRow:hover #CloudFolderName {{
        color: {colors["text_primary"]};
    }}
    #CloudFolderRow:disabled #CloudFolderName {{
        color: {colors["text_muted"]};
    }}
    #CloudFolderPreview {{
        color: {colors["text_primary"]};
        font-size: 22px;
        font-weight: 400;
        background: transparent;
    }}
    #CloudFolderRow:disabled #CloudFolderPreview {{
        color: {colors["text_muted"]};
    }}
    #CloudScroll {{
        border: none;
        background: transparent;
    }}
    #CloudScroll::viewport {{
        background: transparent;
    }}
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


class BoldIconLabel(QLabel):
    BANNER_ICON_PX = 20

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ink = QColor("#FFFFFF")
        self._icon_font = QFont("Segoe Fluent Icons")
        self._icon_font.setPixelSize(self.BANNER_ICON_PX)
        self.setAlignment(Qt.AlignCenter)

    def set_ink(self, color):
        self._ink = QColor(color)
        self.update()

    def sizeHint(self):
        metrics = QFontMetrics(self._icon_font)
        text = self.text() or " "
        width = metrics.horizontalAdvance(text)
        height = metrics.ascent() + metrics.descent()
        return QSize(int(width) + 8, height + 8)

    def paintEvent(self, event):
        # Plain glyph rendering (no outline stroke), matching the weight of
        # the other chrome icons in the app.
        text = self.text()
        if not text:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setFont(self._icon_font)
        painter.setPen(self._ink)
        painter.drawText(self.rect(), Qt.AlignCenter, text)
        painter.end()


class StatusBanner(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Banner")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(16)
        
        self.icon_lbl = BoldIconLabel()
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
        self.text.hide()
        text_layout.addWidget(self.title)
        text_layout.addWidget(self.text)
        layout.addLayout(text_layout, 1)

    def set_content(self, title, message):
        self.title.setText(title)
        self.text.setText(message)
        self.text.hide()

    def set_icon(self, icon_char, color):
        self.icon_lbl.setText(icon_char)
        self.icon_lbl.set_ink(QColor(color))

class WeightCard(QFrame):
    def __init__(self, weight, font_path, is_manual=False, is_dark=False, on_change=None, on_reset=None, parent=None):
        super().__init__(parent)
        self.setObjectName("VariantCard")
        self.setMinimumSize(280, 140)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._font_id = -1
        self.weight = weight
        self.on_change = on_change
        self.on_reset = on_reset
        colors = get_theme_colors(is_dark, is_windows_11())
        
        try:
            metadata = inspect_font(font_path)
            detected_weight = metadata.weight_class
            detected_italic = metadata.is_italic
        except Exception:
            detected_weight, detected_italic = WEIGHT_TARGETS.get(weight, (400, False))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        
        header_row = QWidget()
        header_layout = QHBoxLayout(header_row)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        if weight == "variable":
            is_var_file = getattr(metadata, "is_variable", False)
            title_str = "Variable UI Font"
        elif weight.startswith("consolas_"):
            title_str = "Monospaced " + weight.replace("consolas_", "").replace("_", " ").title()
        else:
            title_str = weight.replace("_", " ").title()

        title = QLabel(title_str)
        title.setObjectName("CardTitle")
        title.setStyleSheet(f"color: {colors['text_primary']}; font-weight: 600; font-size: 14px;")
        header_layout.addWidget(title, 0, Qt.AlignVCenter)

        header_layout.addStretch(1)

        action_btn = QPushButton("\uE7A7" if is_manual else "\uE7C3")
        action_btn.setObjectName("CardChangeBtn")
        action_btn.setProperty("isCustom", "true" if is_manual else "false")
        action_btn.setCursor(Qt.PointingHandCursor)
        action_btn.setFocusPolicy(Qt.NoFocus)
        if is_manual:
            if on_reset:
                action_btn.clicked.connect(lambda: on_reset(self.weight))
        else:
            if on_change:
                action_btn.clicked.connect(lambda: on_change(self.weight))
        header_layout.addWidget(action_btn, 0, Qt.AlignVCenter)

        layout.addWidget(header_row)
        
        is_mono = weight.startswith("consolas_")
        sample_text = "The quick brown fox jumps over the lazy dog"
        self.preview = QLabel(sample_text)
        self.preview.setObjectName("VariantPreview")
        self.preview.setWordWrap(True)
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        self._font_id = QFontDatabase.addApplicationFont(str(font_path))
        font_family_name = ""
        if self._font_id >= 0:
            families = QFontDatabase.applicationFontFamilies(self._font_id)
            if families:
                font_family_name = families[0]

        style_str = "italic" if detected_italic else "normal"
        font_family_rule = f"font-family: '{font_family_name}', monospace;" if is_mono and font_family_name else (f"font-family: '{font_family_name}', sans-serif;" if font_family_name else "")
        self.preview.setStyleSheet(
            f"color: {colors['text_primary']}; "
            f"font-size: 16px; "
            f"{font_family_rule} "
            f"font-weight: {detected_weight}; "
            f"font-style: {style_str};"
        )
        layout.addWidget(self.preview)

        filename_str = Path(font_path).name
        if weight == "variable":
            if is_var_file:
                meta_text = f"Variable Font • {filename_str}"
            else:
                meta_text = f"Static Fallback • Weight {detected_weight} • {filename_str}"
        else:
            meta_text = f"Weight {detected_weight}" + (" • Italic" if detected_italic else "") + f" • {filename_str}"
        meta = QLabel(meta_text)
        meta.setObjectName("VariantMeta")
        meta.setStyleSheet(f"color: {colors['text_muted']}; font-size: 11px;")
        meta.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(meta)

    def cleanup(self):
        if hasattr(self, "preview") and self.preview:
            self.preview.setStyleSheet("")
        if self._font_id >= 0:
            QFontDatabase.removeApplicationFont(self._font_id)
            self._font_id = -1


class _FetchFoldersThread(QThread):
    finished_ok = Signal(list)
    finished_err = Signal(str)

    def __init__(self, repo, branch, parent=None):
        super().__init__(parent)
        self._repo = repo
        self._branch = branch

    def run(self):
        try:
            from github_fonts import list_remote_folders

            folders = list_remote_folders(repo=self._repo, branch=self._branch)
            self.finished_ok.emit(folders)
        except Exception as exc:
            self.finished_err.emit(str(exc))


class _DownloadFolderThread(QThread):
    progress = Signal(int, str)
    finished_ok = Signal(list)
    finished_err = Signal(str)

    def __init__(self, folder, parent=None):
        super().__init__(parent)
        self._folder = folder

    def run(self):
        try:
            from github_fonts import download_folder

            local_paths = download_folder(self._folder, progress=self.progress.emit)
            self.finished_ok.emit([str(p) for p in local_paths])
        except Exception as exc:
            self.finished_err.emit(str(exc))


class _LoadPreviewsThread(QThread):
    preview_ready = Signal(str, str)

    def __init__(self, folders, parent=None):
        super().__init__(parent)
        self._folders = folders

    def run(self):
        try:
            from github_fonts import pick_regular_remote, download_remote_font
            for folder in self._folders:
                if self.isInterruptionRequested():
                    break
                try:
                    reg = pick_regular_remote(folder.fonts)
                    path = download_remote_font(reg)
                    if self.isInterruptionRequested():
                        break
                    self.preview_ready.emit(folder.name, str(path))
                except Exception:
                    pass
        except Exception:
            pass


class CloudFolderRow(QPushButton):
    """Button representing a font folder with folder name and live font preview."""

    def __init__(self, folder, parent=None):
        super().__init__(parent)
        self.folder = folder
        self._family_name = ""
        self.setObjectName("CloudFolderRow")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self.setFixedHeight(58)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(20)

        self.name_label = QLabel(folder.name)
        self.name_label.setObjectName("CloudFolderName")
        self.name_label.setFixedWidth(175)
        self.name_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay.addWidget(self.name_label)

        self.preview_label = QLabel("The quick brown fox jumps over the lazy dog")
        self.preview_label.setObjectName("CloudFolderPreview")
        self.preview_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.preview_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        lay.addWidget(self.preview_label, 1)

        self.refresh_theme()

    def refresh_theme(self):
        window = self.window()
        is_dark = getattr(window, "is_dark", None)
        if is_dark is None:
            is_dark = is_system_dark_mode()
        colors = get_theme_colors(is_dark, is_windows_11())
        text_color = colors["text_primary"] if self.isEnabled() else colors["text_muted"]
        self.name_label.setStyleSheet(
            f"color: {text_color}; font-size: 13px; font-weight: 600; font-family: 'Segoe UI', sans-serif; background: transparent;"
        )
        fam = f"font-family: '{self._family_name}', sans-serif;" if self._family_name else "font-family: 'Segoe UI', sans-serif;"
        self.preview_label.setStyleSheet(
            f"color: {text_color}; {fam} font-size: 22px; background: transparent;"
        )

    def set_font_family(self, family_name: str):
        if not family_name:
            return
        self._family_name = family_name
        self.refresh_theme()

    def setEnabled(self, enabled):
        super().setEnabled(enabled)
        self.refresh_theme()


class LocalFontsGuide(QWidget):
    """Informational guide displayed in the empty space when no font is selected and cloud panel is closed."""

    POINTS = (
        "Keep all .ttf files in a folder and select Regular file, all other weights including mono will be auto detected",
        "If your font lacks some weights like black italic or variable, closest suited weights will be selected for them",
        "You have full control over weights detection, you can override all selected weights with your choice",
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LocalFontsGuideContainer")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        outer_lay = QVBoxLayout(self)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.addStretch(1)

        h_center = QHBoxLayout()
        h_center.setContentsMargins(0, 0, 0, 0)
        h_center.addStretch(1)

        self._inner = QWidget()
        inner_lay = QVBoxLayout(self._inner)
        inner_lay.setContentsMargins(0, 0, 0, 0)
        inner_lay.setSpacing(14)

        self._title_lbl = QLabel("Guide to Applying Local Fonts")
        self._title_lbl.setAlignment(Qt.AlignCenter)
        self._title_lbl.setStyleSheet("font-size: 15px; font-weight: 600; font-family: 'Segoe UI';")
        inner_lay.addWidget(self._title_lbl)

        points_lay = QVBoxLayout()
        points_lay.setSpacing(10)

        self._labels = []

        for html_text in self.POINTS:
            lbl = QLabel()
            lbl.setTextFormat(Qt.RichText)
            lbl.setText(html_text)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setWordWrap(False)
            points_lay.addWidget(lbl, 0, Qt.AlignCenter)
            self._labels.append(lbl)

        inner_lay.addLayout(points_lay)
        h_center.addWidget(self._inner)
        h_center.addStretch(1)

        outer_lay.addLayout(h_center)
        outer_lay.addStretch(1)

    def refresh_theme(self, is_dark: bool):
        colors = get_theme_colors(is_dark, is_windows_11())
        self._title_lbl.setStyleSheet(
            f"color: {colors['text_muted']}; font-size: 14px; font-weight: 600; font-family: 'Segoe UI';"
        )
        for lbl in self._labels:
            lbl.setStyleSheet(f"color: {colors['text_muted']}; font-size: 13px; font-family: 'Segoe UI';")


class IconActionButton(QFrame):
    """Standalone action button with an MDL2 glyph icon and a text label.

    Styling matches the old split-button halves exactly: per-icon glyph
    size at regular weight with accent ink, plus a bold Segoe UI caption.
    Unlike the old split control, the whole button is clickable.
    """

    clicked = Signal()

    _LEFT_PAD = 12
    _ICON_GAP = 8
    _RIGHT_PAD = 16

    def __init__(self, icon_char, icon_px, icon_object_name, text, parent=None):
        super().__init__(parent)
        self.setObjectName("ActionButton")
        # 36px total so the frame lines up exactly with real QPushButtons
        # (34px QSS content height + 1px border on each side).
        self.setFixedHeight(36)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setCursor(Qt.ArrowCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(True)
        self.setAccessibleName(text)
        self._enabled = True
        self._hover = False
        self._pressed = False
        self.setProperty("pressed", False)
        self._icon_px = icon_px
        self._icon_label = QLabel(icon_char, self)
        self._icon_label.setObjectName(icon_object_name)
        self._icon_label.setAlignment(Qt.AlignCenter)
        self._icon_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._text_label = QLabel(text, self)
        self._text_label.setObjectName("ActionText")
        self._text_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self._text_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._icon_label.raise_()
        self._text_label.raise_()
        self._sync_width()
        self.refresh_action_style()

    def text(self):
        try:
            return self._text_label.text()
        except RuntimeError:
            return ""

    def _sync_width(self):
        # Frame width follows the caption: pad + icon + gap + text + pad.
        try:
            metrics = QFontMetrics(self._text_label.font())
            text_w = int(metrics.horizontalAdvance(self.text()))
        except RuntimeError:
            text_w = 90
        icon_w = self._icon_px + 12
        total = self._LEFT_PAD + icon_w + self._ICON_GAP + text_w + self._RIGHT_PAD
        try:
            self.setFixedWidth(max(110, int(total)))
        except RuntimeError:
            pass
        self._layout_content()

    def _layout_content(self):
        try:
            width, height = self.width(), self.height()
        except RuntimeError:
            return
        icon_w = self._icon_px + 12
        try:
            self._icon_label.setGeometry(self._LEFT_PAD, 1, icon_w, max(1, height - 2))
            tx = self._LEFT_PAD + icon_w + self._ICON_GAP
            self._text_label.setGeometry(
                tx, 1, max(1, width - tx - self._RIGHT_PAD + 4), max(1, height - 2))
        except RuntimeError:
            pass

    def setEnabled(self, enabled):
        super().setEnabled(enabled)
        self._enabled = bool(enabled)
        if not enabled:
            self._hover = False
            self._pressed = False
        self._paint_pressed(False)
        self.refresh_action_style()

    def hideEvent(self, event):
        self._hover = False
        self._pressed = False
        self._paint_pressed(False)
        super().hideEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_content()

    def showEvent(self, event):
        super().showEvent(event)
        # QSS font resolves on polish: re-measure once it is real.
        self._sync_width()

    def refresh_action_style(self):
        """Caption/icon ink follows state/role (set in code, not QSS).

        Qt mis-applies ancestor pseudo-state selectors (e.g. a disabled
        parent greying labels out like disabled controls), so the ink is
        set here instead of in QSS.
        """
        window = self.window()
        is_dark = getattr(window, "is_dark", None)
        if is_dark is None:
            is_dark = is_system_dark_mode()
        colors = get_theme_colors(is_dark)
        role = self.property("buttonRole") or "secondary"
        if not self._enabled:
            icon_ink = colors["text_muted"]
            text_ink = colors["text_muted"]
        elif role in ("primary", "warning"):
            icon_ink = colors["accent_text"]
            text_ink = colors["accent_text"]
        else:
            icon_ink = colors["accent_icon"]
            text_ink = colors["text_primary"]
        try:
            self._icon_label.setStyleSheet(f"color: {icon_ink};")
            self._text_label.setStyleSheet(f"color: {text_ink};")
        except RuntimeError:
            pass

    def _paint_pressed(self, pressed):
        # QFrame gets no :pressed pseudo-state, so the press fill is
        # driven by a dynamic property + QSS. Never an inline
        # stylesheet: an inline background on the frame cascades onto
        # the transparent icon/caption labels and double-darkens them
        # in patches (grey boxes behind icon and text on click).
        if not self._enabled:
            pressed = False
        try:
            if bool(self.property("pressed")) != bool(pressed):
                self.setProperty("pressed", bool(pressed))
                self.style().unpolish(self)
                self.style().polish(self)
                self.update()
        except RuntimeError:
            pass

    def mouseMoveEvent(self, event):
        if self._enabled:
            try:
                inside = self.rect().contains(
                    int(event.position().x()), int(event.position().y()))
            except (AttributeError, RuntimeError):
                inside = True
            self._hover = bool(inside)
            self.setCursor(Qt.PointingHandCursor if inside else Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def enterEvent(self, event):
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self._pressed = False
        self.setCursor(Qt.ArrowCursor)
        self._paint_pressed(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._enabled:
            self._pressed = True
            self._paint_pressed(True)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            pressed = self._pressed
            self._pressed = False
            self._paint_pressed(False)
            if pressed and self._enabled and self.rect().contains(int(event.position().x()), int(event.position().y())):
                event.accept()
                self.clicked.emit()
                return
            event.accept()
            return
        super().mouseReleaseEvent(event)


class CloudFolderPanel(QFrame):
    """Inline (non-popup) dropdown listing the folders of the GitHub fonts repo."""

    downloaded = Signal(list)
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CloudPanel")
        self.hide()
        self._folders = []
        self._fetch_thread = None
        self._dl_thread = None
        self._preview_thread = None
        self._preview_font_ids = []
        self._row_map = {}
        self._is_hiding = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel("Download fonts to apply")
        title.setObjectName("CloudTitle")
        header.addWidget(title)
        header.addStretch(1)
        refresh_btn = QPushButton(chr(0xE7AD))
        refresh_btn.setObjectName("IconBtnRefresh")
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.setToolTip("Refresh folder list")
        refresh_btn.setAccessibleName("Refresh folder list")
        refresh_btn.clicked.connect(lambda: self.start_fetch(force=True))
        header.addWidget(refresh_btn)
        close_btn = QPushButton(chr(0xE8BB))
        close_btn.setObjectName("IconBtn")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setToolTip("Close")
        close_btn.setAccessibleName("Close cloud panel")
        close_btn.clicked.connect(self._on_close)
        header.addWidget(close_btn)
        layout.addLayout(header)

        self.status_lbl = QLabel("Loading folder list…")
        self.status_lbl.setObjectName("CloudMeta")
        self.status_lbl.setWordWrap(True)
        layout.addWidget(self.status_lbl)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("CloudScroll")
        # The scroll area itself otherwise paints an opaque palette.Window
        # fill, which shows as window-colored stripes in the row gaps.
        self.scroll.setAutoFillBackground(False)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # The viewport otherwise paints an opaque palette background, which
        # turns the translucent row colors opaque (white rows in dark mode).
        self.scroll.viewport().setAutoFillBackground(False)
        self._scroll_geom_key = None
        self._rows_container = QWidget()
        self._rows_container.setAutoFillBackground(False)
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(8)
        self._rows_layout.addStretch(1)
        self.scroll.setWidget(self._rows_container)
        # setWidget() re-enables auto-fill on the widget: switch it back
        # off or the palette.Window fill shows in the row gaps.
        self._rows_container.setAutoFillBackground(False)
        layout.addWidget(self.scroll)

    def showEvent(self, event):
        super().showEvent(event)
        # The page layout may have shifted (e.g. preview cards appearing),
        # so re-measure after this show settles.
        QTimer.singleShot(0, self.sync_height)

    def sync_height(self, window_height=None):
        try:
            lay = self._rows_container.layout()
            heights = []
            spacing = 0
            margins = 0
            if lay is not None:
                spacing = int(lay.spacing())
                try:
                    cm = lay.contentsMargins()
                    margins = int(cm.top()) + int(cm.bottom())
                except RuntimeError:
                    margins = 0
                for i in range(lay.count()):
                    item = lay.itemAt(i)
                    if item is None:
                        continue
                    widget = item.widget()
                    if widget is None:
                        continue
                    try:
                        # Polish first: an unpolished row reports its unstyled
                        # sizeHint (~25px) instead of the real QSS height (~48px),
                        # which used to pin the viewport far too small.
                        widget.ensurePolished()
                        heights.append(max(0, int(widget.sizeHint().height())))
                    except RuntimeError:
                        continue
            content = sum(heights)
            if len(heights) > 1:
                content += spacing * (len(heights) - 1)
            # The layout margins are real pixels the container needs; leaving
            # them out pinned the viewport 1px short and produced a scrollbar
            # with a ~1px range that moved nothing.
            content += margins
            if heights:
                content += 6
            # Show up to 5 rows; anything beyond that scrolls inside the list.
            shown = heights[:5]
            target = sum(shown)
            if len(shown) > 1:
                target += spacing * (len(shown) - 1)
            if shown:
                target += margins + 6
        except RuntimeError:
            content = 0
            target = 0
        if window_height is None:
            try:
                win = self.window()
                window_height = win.height() if win is not None else 650
            except RuntimeError:
                window_height = 650
        try:
            cap = max(60, min(560, int(round(float(window_height) * 0.45))))
        except (TypeError, ValueError):
            cap = 360
        # Never let the panel overflow the window: measure what the visible
        # siblings (banner, setup card, variant cards…) already occupy and
        # cap the list to what is actually left.
        try:
            win_h = int(round(float(window_height)))
            parent = self.parentWidget()
            play = parent.layout() if parent is not None else None
            if play is not None and win_h > 0:
                used = 0
                sibs = 0
                for j in range(play.count()):
                    sub = play.itemAt(j)
                    sib = sub.widget() if sub is not None else None
                    if sib is None or sib is self or not sib.isVisibleTo(parent):
                        continue
                    used += max(0, int(sib.height()))
                    sibs += 1
                try:
                    pm = play.contentsMargins()
                    used += int(pm.top()) + int(pm.bottom())
                except RuntimeError:
                    pass
                try:
                    used += int(play.spacing()) * max(0, sibs)
                except RuntimeError:
                    pass
                if used > 0:
                    avail = win_h - used - 16
                    panel_chrome = 0
                    lay_self = self.layout()
                    if lay_self is not None:
                        cm_self = lay_self.contentsMargins()
                        panel_chrome += int(cm_self.top()) + int(cm_self.bottom())
                        spacing_self = int(lay_self.spacing())
                        for k in range(lay_self.count()):
                            item_self = lay_self.itemAt(k)
                            w_self = item_self.widget() if item_self is not None else None
                            if w_self is not None and w_self is not self.scroll:
                                if w_self.isVisible() and (not isinstance(w_self, QLabel) or w_self.text()):
                                    panel_chrome += max(0, int(w_self.sizeHint().height())) + spacing_self
                            elif item_self is not None and item_self.layout() is not None:
                                panel_chrome += max(0, int(item_self.layout().sizeHint().height())) + spacing_self
                    avail_for_scroll = max(60, avail - panel_chrome)
                    cap = min(cap, avail_for_scroll)
        except (RuntimeError, TypeError, ValueError):
            pass
        content = max(0, int(content))
        target = max(0, int(target))
        # Pin the container to at least the measured row stack. If the
        # layout ever goes stale-short, rows overflow the container and the
        # scrollbar maximum strands users above the last row (first-row
        # sliver on top, cut last row at max scroll). A minimum height equal
        # to the real content makes scroll-end exact by construction; when
        # healthy it equals the layout height, i.e. a no-op.
        try:
            self._rows_container.setMinimumHeight(content)
        except RuntimeError:
            pass
        if getattr(self, "_scroll_geom_key", None) == (cap, content):
            return
        self._scroll_geom_key = (cap, content)
        height = min(target, cap)
        try:
            self.scroll.setMinimumHeight(height)
            self.scroll.setMaximumHeight(height)
            # One full row pitch per wheel notch; the default step stops
            # mid-row and feels stuck.
            self.scroll.verticalScrollBar().setSingleStep(66)
            self.scroll.updateGeometry()
        except RuntimeError:
            pass
        try:
            win = self.window()
            if win is not None and win.layout() is not None:
                win.layout().activate()
        except RuntimeError:
            pass

    def start_fetch(self, force=False):
        if self._fetch_thread and self._fetch_thread.isRunning():
            return
        if not force and self._folders and self._rows_layout.count() > 1:
            self.sync_height()
            return
        if not self._folders or self._rows_layout.count() <= 1:
            self._clear_rows()
            self._set_status("Loading fonts…")
        else:
            self._set_status("Refreshing fonts…")
        self._fetch_thread = _FetchFoldersThread(GITHUB_FONTS_REPO, GITHUB_FONTS_BRANCH, self)
        self._fetch_thread.finished_ok.connect(self._on_fetch_ok)
        self._fetch_thread.finished_err.connect(self._on_fetch_err)
        self._fetch_thread.finished.connect(self._fetch_thread.deleteLater)
        self._fetch_thread.start()

    def _on_fetch_ok(self, folders):
        self._fetch_thread = None
        self._folders = folders
        self._clear_rows()
        if not folders:
            self._set_status("Fonts couldn't be loaded.")
            return
        self._row_map = {}
        for folder in folders:
            row = CloudFolderRow(folder)
            row.clicked.connect(lambda _checked=False, f=folder: self._on_folder_clicked(f))
            self._rows_layout.insertWidget(self._rows_layout.count() - 1, row)
            self._row_map[folder.name] = row
        self._set_status("")
        self.sync_height()
        # Re-measure once the event loop has polished and laid out the new
        # rows (folder list arriving while preview cards shift the page).
        QTimer.singleShot(0, self.sync_height)
        self._start_preview_loading(folders)

    def _start_preview_loading(self, folders):
        uncached_folders = []
        try:
            from github_fonts import get_cache_dir, _safe_folder_name, pick_regular_remote
            cache_root = get_cache_dir()
            for folder in folders:
                try:
                    reg = pick_regular_remote(folder.fonts)
                    target = cache_root / _safe_folder_name(folder.folder) / reg.name
                    if target.exists() and reg.size and target.stat().st_size == reg.size:
                        self._apply_preview_font(folder.name, str(target))
                    else:
                        uncached_folders.append(folder)
                except Exception:
                    uncached_folders.append(folder)
        except Exception:
            uncached_folders = list(folders)

        if uncached_folders:
            if self._preview_thread and self._preview_thread.isRunning():
                try:
                    self._preview_thread.requestInterruption()
                    self._preview_thread.quit()
                    self._preview_thread.wait(300)
                except Exception:
                    pass
            self._preview_thread = _LoadPreviewsThread(uncached_folders, self)
            self._preview_thread.preview_ready.connect(self._apply_preview_font)
            self._preview_thread.finished.connect(self._preview_thread.deleteLater)
            self._preview_thread.start()

    def _apply_preview_font(self, folder_name: str, path_str: str):
        row = self._row_map.get(folder_name)
        if not row:
            return
        try:
            font_id = QFontDatabase.addApplicationFont(path_str)
            if font_id >= 0:
                self._preview_font_ids.append(font_id)
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    row.set_font_family(families[0])
        except Exception:
            pass

    def _set_status(self, text):
        # An empty status takes no space, keeping the first entry tight
        # under the header instead of leaving a dead gap.
        self.status_lbl.setText(text or "")
        self.status_lbl.setVisible(bool(text))

    def _on_fetch_err(self, message):
        self._fetch_thread = None
        text = str(message or "")
        if "403" in text or "rate limit" in text.lower():
            self._set_status("Fonts couldn't be loaded. Please try again in an hour.")
        else:
            self._set_status("Fonts couldn't be loaded. Check your internet connection.")

    def _row_text(self, folder):
        return folder.name.replace("&", "&&")

    def _clear_rows(self):
        self._row_map.clear()
        while self._rows_layout.count() > 1:
            item = self._rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.sync_height()

    def _set_rows_enabled(self, enabled):
        for i in range(self._rows_layout.count() - 1):
            widget = self._rows_layout.itemAt(i).widget()
            if widget is not None:
                widget.setEnabled(enabled)

    def _on_folder_clicked(self, folder):
        if self._dl_thread and self._dl_thread.isRunning():
            return
        self._set_rows_enabled(False)
        self._set_status("Downloading…")
        self._dl_thread = _DownloadFolderThread(folder, self)
        self._dl_thread.progress.connect(self._on_dl_progress)
        self._dl_thread.finished_ok.connect(self._on_dl_ok)
        self._dl_thread.finished_err.connect(self._on_dl_err)
        self._dl_thread.finished.connect(self._dl_thread.deleteLater)
        self._dl_thread.start()

    def _on_dl_progress(self, pct, name):
        self._set_status(f"Downloading… {int(pct)}%")

    def _on_dl_ok(self, local_paths):
        self._dl_thread = None
        self._set_rows_enabled(True)
        self._set_status("")
        self.downloaded.emit(local_paths)
        QTimer.singleShot(0, self.sync_height)

    def _on_dl_err(self, message):
        self._dl_thread = None
        self._set_rows_enabled(True)
        # Never surface file names, counts, or errnos: tell the user what
        # to do instead. Throttling backs off on its own; anything else is
        # almost always the connection.
        lowered = (message or "").lower()
        if "403" in lowered or "429" in lowered or "rate limit" in lowered:
            self._set_status("Too many downloads right now. Try again in an hour.")
        else:
            self._set_status("Download failed. Check your internet and try again.")

    def refresh_theme(self):
        for i in range(self._rows_layout.count() - 1):
            widget = self._rows_layout.itemAt(i).widget()
            if isinstance(widget, CloudFolderRow):
                widget.refresh_theme()

    def _on_close(self):
        self.animate_hide()

    def reset(self):
        if self._dl_thread and self._dl_thread.isRunning():
            return False
        self._kill_anim()
        self._is_hiding = False
        self.setMaximumHeight(16777215)
        self.setEnabled(True)
        self._set_status("")
        self.hide()
        return True

    def _kill_anim(self):
        anim = getattr(self, "_height_anim", None)
        if anim is not None:
            try:
                anim.stop()
            except RuntimeError:
                pass
            self._height_anim = None

    def animate_show(self, window_height=None):
        """Expand the panel smoothly with a slide-down animation."""
        if self._dl_thread and self._dl_thread.isRunning():
            return False
        self._kill_anim()
        self._is_hiding = False
        self.setEnabled(True)
        self._set_status("")
        self.sync_height(window_height)
        target = max(60, self.sizeHint().height())
        self.setMaximumHeight(0)
        self.show()
        self.raise_()
        anim = QPropertyAnimation(self, b"maximumHeight", self)
        anim.setStartValue(0)
        anim.setEndValue(target)
        anim.setDuration(200)
        anim.setEasingCurve(QEasingCurve.OutCubic)

        def _on_show_done():
            self._height_anim = None
            self.setMaximumHeight(16777215)
            self.sync_height()

        anim.finished.connect(_on_show_done)
        self._height_anim = anim
        anim.start()
        return True

    def animate_hide(self):
        """Collapse the panel with a short animation. Refuses (False) while
        a download is running, so the list can't be yanked away mid-fetch."""
        if self._dl_thread and self._dl_thread.isRunning():
            return False
        if not self.isVisible():
            return True
        self._kill_anim()
        self._is_hiding = True
        self.setEnabled(False)
        start = max(1, self.height())
        self.setMaximumHeight(start)
        anim = QPropertyAnimation(self, b"maximumHeight", self)
        anim.setStartValue(start)
        anim.setEndValue(0)
        anim.setDuration(180)
        anim.setEasingCurve(QEasingCurve.InCubic)
        anim.finished.connect(self._on_hide_anim_done)
        self._height_anim = anim
        anim.start()
        return True

    def _on_hide_anim_done(self):
        self._is_hiding = False
        self._height_anim = None
        self.setMaximumHeight(16777215)
        self.setEnabled(True)
        self._set_status("")
        self.hide()
        self.closed.emit()


def _star_outline_3d():
    points = []
    for i in range(10):
        radius = 1.0 if i % 2 == 0 else 0.44
        angle = math.radians(-90.0 + i * 36.0)
        points.append((radius * math.cos(angle), radius * math.sin(angle)))
    return points


def _render_star_satin(px=96, palette=None):
    """Option 1 Clean Satin Star in accent theme color.
    Smooth vertical gradient, zero white glare in middle, no dark outline stroke.
    """
    image = QImage(px, px, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    center = px / 2.0
    scale = px * 0.42
    outline = _star_outline_3d()
    pts = [QPointF(center + x * scale, center - y * scale) for x, y in outline]
    poly = QPolygonF(pts)

    grad = QLinearGradient(center, center - scale, center, center + scale)
    hi = (palette.get("hi") if isinstance(palette, dict) else None) or "#60CDFF"
    mid = (palette.get("mid") if isinstance(palette, dict) else None) or "#0078D4"
    grad.setColorAt(0.0, QColor(hi))
    grad.setColorAt(1.0, QColor(mid))

    painter.setPen(Qt.NoPen)
    painter.setBrush(grad)
    painter.drawPolygon(poly)
    painter.end()
    return QPixmap.fromImage(image)


def _render_star_flat(angle_deg=0.0, px=96):
    return _render_star3d(angle_deg, px=px)


def _render_star3d(angle_deg, px=96, palette=None):
    if palette is None:
        colors = get_theme_colors(True)
        base = QColor(colors.get("accent", "#0078D4"))
        hi = QColor(colors.get("accent_icon", colors.get("accent", "#60CDFF")))
        if hi == base:
            hi = base.lighter(135)
        pal = {
            "hi": hi,
            "mid": base,
            "deep": base.darker(135),
            "edge": base.darker(165),
            "side": base.lighter(110),
        }
    else:
        pal = {
            "hi": QColor(palette["hi"]),
            "mid": QColor(palette["mid"]),
            "deep": QColor(palette["deep"]),
            "edge": QColor(palette["edge"]),
            "side": QColor(palette["side"]),
        }
    theta = math.radians(angle_deg)
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    half = 0.20
    light_len = math.sqrt(0.45 * 0.45 + 0.55 * 0.55 + 0.75 * 0.75)
    light = (-0.45 / light_len, 0.55 / light_len, 0.75 / light_len)

    def rotate_point(point):
        x, y, z = point
        return (x * cos_t + z * sin_t, y, -x * sin_t + z * cos_t)

    def face_facing(normal):
        nx, ny, nz = normal
        rx = nx * cos_t + nz * sin_t
        ry = ny
        rz = -nx * sin_t + nz * cos_t
        return rx * light[0] + ry * light[1] + rz * light[2]

    outline = _star_outline_3d()
    count = len(outline)
    faces = [
        {"pts": [(x, y, half) for x, y in outline], "normal": (0.0, 0.0, 1.0), "kind": "front"},
        {"pts": [(x, y, -half) for x, y in outline], "normal": (0.0, 0.0, -1.0), "kind": "back"},
    ]
    for i in range(count):
        x0, y0 = outline[i]
        x1, y1 = outline[(i + 1) % count]
        dx = x1 - x0
        dy = y1 - y0
        length = math.hypot(dx, dy) or 1.0
        faces.append({
            "pts": [(x0, y0, half), (x1, y1, half), (x1, y1, -half), (x0, y0, -half)],
            "normal": (dy / length, -dx / length, 0.0),
            "kind": "side",
        })

    scale = px * 0.40
    center = px / 2.0

    def to_screen(point):
        rx, ry, rz = rotate_point(point)
        return (center + rx * scale, center - ry * scale, rz)

    layers = {"front": None, "back": None, "sides": []}
    for face in faces:
        shown = [to_screen(p) for p in face["pts"]]
        depth = sum(p[2] for p in shown) / len(shown)
        entry = (depth, face, shown)
        if face["kind"] == "front":
            layers["front"] = entry
        elif face["kind"] == "back":
            layers["back"] = entry
        else:
            layers["sides"].append(entry)
    layers["sides"].sort(key=lambda item: item[0])
    if cos_t >= 0.0:
        ordered = [layers["back"], *layers["sides"], layers["front"]]
    else:
        ordered = [layers["front"], *layers["sides"], layers["back"]]

    def shaded(color, facing_value):
        c = QColor(color)
        brightness = 0.65 + 0.35 * max(0.0, facing_value)
        return QColor(
            max(0, min(255, int(c.red() * brightness))),
            max(0, min(255, int(c.green() * brightness))),
            max(0, min(255, int(c.blue() * brightness))),
        )

    image = QImage(px, px, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(pal["edge"])
    pen.setWidthF(max(1.0, px * 0.022))
    pen.setJoinStyle(Qt.RoundJoin)
    front_facing_camera = cos_t >= 0.0
    for _, face, shown in ordered:
        poly = QPolygonF([QPointF(sx, sy) for sx, sy, _ in shown])
        facing_value = face_facing(face["normal"])
        kind = face["kind"]
        is_camera_facing_star = (kind == "front" and front_facing_camera) or (kind == "back" and not front_facing_camera)
        if is_camera_facing_star:
            puff = QRadialGradient(center, center - scale * 0.30, scale * 1.15)
            puff.setColorAt(0.0, pal["hi"])
            puff.setColorAt(0.55, pal["mid"])
            puff.setColorAt(1.0, pal["deep"])
            painter.setBrush(puff)
            painter.setPen(pen)
            painter.drawPolygon(poly)
            painter.save()
            clip = QPainterPath()
            clip.addPolygon(poly)
            painter.setClipPath(clip)
            painter.setPen(Qt.NoPen)
            shade_grad = QLinearGradient(0, center - scale * 0.1, 0, center + scale)
            shade_grad.setColorAt(0.0, QColor(pal["deep"].red(), pal["deep"].green(), pal["deep"].blue(), 0))
            shade_grad.setColorAt(1.0, QColor(pal["deep"].red(), pal["deep"].green(), pal["deep"].blue(), 85))
            painter.setBrush(shade_grad)
            painter.drawRect(int(center - scale), int(center - scale), int(scale * 2), int(scale * 2))
            spec = QRadialGradient(center - scale * 0.22, center - scale * 0.32, scale * 0.65)
            spec.setColorAt(0.0, QColor(255, 255, 255, 120))
            spec.setColorAt(0.45, QColor(255, 255, 255, 35))
            spec.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setBrush(spec)
            painter.drawRect(int(center - scale), int(center - scale), int(scale * 2), int(scale * 2))
            painter.restore()
        else:
            base = pal["mid"] if kind in ("front", "back") else pal["side"]
            painter.setPen(pen if kind in ("front", "back") else Qt.NoPen)
            painter.setBrush(shaded(base, facing_value))
            painter.drawPolygon(poly)
    painter.end()
    return QPixmap.fromImage(image)


class FontWizardApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self._action_buttons = ()
        self.controller = FontWizardController()
        self.setWindowTitle(APP_NAME)
        icon_path = get_asset_path("font-wizard-icon.png")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"fontwizard.{APP_NAME}.1")

        self.setMinimumSize(980, 600)
        self.resize(1050, 650)
        self._selection_dirty = False
        self._hide_applied_variants = True
        self._apply_action = "apply"
        self._browse_action = "select"
        self._op_thread = None
        self._armed_button = None
        self._armed_action = None
        self._armed_face = None
        self._arm_labels = None
        self._op_cover = None
        self._op_cover_btn = None
        self._armed_at = 0.0
        self._star_active = False
        self._cloud_open = False
        self._cards_sig = None
        self._last_theme_sig = None
        self._variant_geom_key = None
        self._compact_layout = None
        self.is_dark = is_system_dark_mode()
        if is_windows_11():
            self.setAttribute(Qt.WA_TranslucentBackground)

        central = QWidget(objectName="CentralWidget")
        self.setCentralWidget(central)
        self.main_layout = QVBoxLayout(central)
        self.main_layout.setContentsMargins(40, 36, 40, 36)
        self.main_layout.setSpacing(24)

        self._build_header()
        self._build_font_setup()
        self._build_variants()
        self.main_layout.addStretch(1)
        self._action_buttons = (self.local_btn, self.fetch_btn, self.apply_btn, self.restore_btn)

        self.local_btn.clicked.connect(self._on_local_pick)
        self.fetch_btn.clicked.connect(self._on_cloud_toggle)
        self.cloud_panel.downloaded.connect(self._on_cloud_downloaded)
        self.cloud_panel.closed.connect(self._on_cloud_closed)
        self.apply_btn.clicked.connect(self.on_apply_action)
        self.restore_btn.clicked.connect(self.on_restore)

        self._sync_responsive_layout()
        self._apply_theme(self.is_dark)

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

        self.github_btn = QPushButton()
        self.github_btn.setObjectName("HeaderIconButton")
        self.github_btn.setFlat(True)
        self.github_btn.setIconSize(QSize(20, 20))
        self.github_btn.setCursor(Qt.PointingHandCursor)
        self.github_btn.setAccessibleName("GitHub")
        self.github_btn.clicked.connect(self._on_github_clicked)
        self._star_timer = QTimer(self)
        self._star_timer.setSingleShot(True)
        self._star_timer.timeout.connect(self._restore_github_logo)
        self._update_github_icon()
        title_row_layout.addWidget(self.github_btn, 0, Qt.AlignBottom)
        text_layout.addWidget(title_row, 0, Qt.AlignLeft)

        subtitle = QLabel("Customize your system fonts")
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
        self.setup_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setup_layout = QHBoxLayout(self.setup_card)
        self.setup_layout.setContentsMargins(20, 14, 20, 14)
        self.setup_layout.setSpacing(16)

        self.font_summary = QWidget()
        summary_layout = QVBoxLayout(self.font_summary)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(2)

        title = QLabel("Interface Font")
        title.setObjectName("CardTitle")
        summary_layout.addWidget(title)

        self.cur_font_lbl = QLabel("No font selected")
        self.cur_font_lbl.setObjectName("SelectedFont")
        self.cur_font_lbl.setWordWrap(True)
        summary_layout.addWidget(self.cur_font_lbl)

        self.setup_layout.addWidget(self.font_summary, 1, Qt.AlignVCenter)

        self.actions_widget = QWidget()
        self.actions_layout = QHBoxLayout(self.actions_widget)
        self.actions_layout.setContentsMargins(0, 0, 0, 0)
        self.actions_layout.setSpacing(10)

        self.local_btn = IconActionButton(chr(0xE8E5), 18, "ActionIconLocal", "Local Fonts")
        self.fetch_btn = IconActionButton(chr(0xE753), 24, "ActionIconFetch", "Fetch Fonts")
        self.apply_btn = QPushButton("Apply Changes")
        self.restore_btn = QPushButton("Restore Original Fonts")

        self.local_btn.setToolTip("From this PC")
        self.fetch_btn.setToolTip("From cloud")
        for button in (self.apply_btn, self.restore_btn):
            button.setFixedHeight(34)
            button.setMinimumWidth(150)
        for button in (self.local_btn, self.fetch_btn, self.apply_btn, self.restore_btn):
            button.setCursor(Qt.PointingHandCursor)
            button.setFocusPolicy(Qt.NoFocus)
            button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            button.installEventFilter(self)
            self.actions_layout.addWidget(button, 0, Qt.AlignVCenter)

        self.setup_layout.addWidget(self.actions_widget, 0, Qt.AlignVCenter)
        self.main_layout.addWidget(self.setup_card)

        self.cloud_panel = CloudFolderPanel()
        self.main_layout.addWidget(self.cloud_panel)

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

        self.weight_scroll = QScrollArea(objectName="WeightScrollArea")
        # Same opaque-fill hazard as the cloud list: keep it transparent.
        self.weight_scroll.setAutoFillBackground(False)
        self.weight_scroll.setWidgetResizable(True)
        self.weight_scroll.setFrameShape(QFrame.NoFrame)
        self.weight_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.weight_scroll.viewport().setAutoFillBackground(False)
        self.weight_scroll.hide()

        self.weight_widget = QWidget(objectName="WeightContainer")
        self.weight_widget.setAutoFillBackground(False)
        self.weight_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.weight_layout = FlowLayout(self.weight_widget, margin=0, spacing=16)
        self.weight_layout.setContentsMargins(0, 0, 0, 0)

        self.weight_scroll.setWidget(self.weight_widget)
        # setWidget() re-enables auto-fill on the widget (see cloud list).
        self.weight_widget.setAutoFillBackground(False)
        self.weight_scroll.viewport().installEventFilter(self)
        self.main_layout.addWidget(self.weight_scroll, 1000)

        self.local_fonts_guide = LocalFontsGuide()
        self.main_layout.addWidget(self.local_fonts_guide, 1000)

    def _set_button_role(self, button, role):
        if button.property("buttonRole") == role:
            return
        button.setProperty("buttonRole", role)
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()
        refresh = getattr(button, "refresh_action_style", None)
        if refresh:
            refresh()

    def _apply_widget_theme(self):
        for button in self._action_buttons:
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()
            refresh = getattr(button, "refresh_action_style", None)
            if refresh:
                refresh()
        if hasattr(self, "cloud_panel"):
            self.cloud_panel.refresh_theme()
        if hasattr(self, "local_fonts_guide"):
            self.local_fonts_guide.refresh_theme(self.is_dark)

    def _update_github_icon(self):
        if not hasattr(self, "github_btn"):
            return
        if getattr(self, "_star_active", False):
            return
        if self.is_dark not in _github_icon_cache:
            fill_color = "#FFFFFF" if self.is_dark else "#1F2328"
            svg_path = get_asset_path("github-mark.svg")
            pixmap = QPixmap()
            try:
                if svg_path.exists():
                    svg_content = svg_path.read_text(encoding="utf-8").replace("#ffffff", fill_color).replace("#FFFFFF", fill_color)
                    if not pixmap.loadFromData(svg_content.encode("utf-8"), "SVG"):
                        pixmap = QPixmap()
            except Exception:
                pixmap = QPixmap()
            _github_icon_cache[self.is_dark] = pixmap
        pixmap = _github_icon_cache.get(self.is_dark)
        if pixmap and not pixmap.isNull():
            try:
                self.github_btn.setIcon(QIcon(pixmap))
                return
            except Exception:
                pass
        try:
            self.github_btn.setIcon(QIcon(str(get_asset_path("github-mark.svg"))))
        except Exception:
            pass

    _STAR_REST_PX = 28
    _STAR_SHOW_MS = 13000
    _STAR_SPIN_DELAY_MS = 350

    def _star_palette(self):
        """Accent-derived palette for the 3D coin-flip star (theme-dynamic)."""
        colors = get_theme_colors(self.is_dark)
        base = QColor(colors["accent"])
        hi = QColor(colors.get("accent_icon", colors["accent"]))
        if hi == base:
            hi = base.lighter(135)
        return {
            "hi": hi,
            "mid": base,
            "deep": base.darker(135),
            "edge": base.darker(165),
            "side": base.lighter(110),
        }

    def _on_github_clicked(self):
        QDesktopServices.openUrl(QUrl(APP_GITHUB_URL))
        if getattr(self, "_star_active", False):
            self._restore_github_logo()

    def _stop_star_anim(self):
        try:
            self._star_timer.stop()
        except (RuntimeError, AttributeError):
            pass
        spin = getattr(self, "_star_spin_anim", None)
        if spin is not None:
            try:
                spin.stop()
            except RuntimeError:
                pass
            self._star_spin_anim = None
        button = getattr(self, "github_btn", None)
        if button is not None:
            try:
                button.setGraphicsEffect(None)
            except RuntimeError:
                pass

    def _morph_to_star(self):
        if getattr(self, "_star_active", False):
            self._star_timer.start(self._STAR_SHOW_MS)
            return
        self._star_active = True
        self._star_timer.start(self._STAR_SHOW_MS)
        button = self.github_btn
        button.setAccessibleName("Star Font Wizard on GitHub")
        effect = QGraphicsOpacityEffect(button)
        button.setGraphicsEffect(effect)
        fade_out = QPropertyAnimation(effect, b"opacity", self)
        fade_out.setDuration(120)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)

        def _swap_to_star():
            if not self._star_active:
                return
            button.setIcon(QIcon(_render_star3d(0.0, palette=self._star_palette())))
            self._star_angle = 0.0
            button.setIconSize(QSize(12, 12))
            button.setText("")
            fade_in = QPropertyAnimation(effect, b"opacity", self)
            fade_in.setDuration(160)
            fade_in.setStartValue(0.0)
            fade_in.setEndValue(1.0)
            fade_in.finished.connect(lambda: button.setGraphicsEffect(None))
            fade_in.start(QAbstractAnimation.DeleteWhenStopped)
            pop = QPropertyAnimation(button, b"iconSize", self)
            pop.setDuration(280)
            pop.setStartValue(QSize(12, 12))
            pop.setEndValue(QSize(self._STAR_REST_PX, self._STAR_REST_PX))
            pop.setEasingCurve(QEasingCurve.OutBack)
            pop.start(QAbstractAnimation.DeleteWhenStopped)
            QTimer.singleShot(self._STAR_SPIN_DELAY_MS, self._start_star_spin)

        fade_out.finished.connect(_swap_to_star)
        fade_out.start(QAbstractAnimation.DeleteWhenStopped)

    def _start_star_spin(self):
        if not getattr(self, "_star_active", False):
            return
        spin = QVariantAnimation(self)
        spin.setDuration(1200)
        spin.setStartValue(0.0)
        spin.setEndValue(360.0)
        spin.setEasingCurve(QEasingCurve.InOutQuad)
        spin.valueChanged.connect(self._spin_star_frame)
        spin.finished.connect(self._finish_star_spin)
        self._star_spin_anim = spin
        spin.start(QAbstractAnimation.DeleteWhenStopped)

    def _spin_star_frame(self, angle):
        if not getattr(self, "_star_active", False):
            return
        try:
            self._star_angle = float(angle)
            self.github_btn.setIcon(QIcon(_render_star3d(angle, palette=self._star_palette())))
        except Exception:
            pass

    def _finish_star_spin(self):
        self._star_spin_anim = None
        if not getattr(self, "_star_active", False):
            return
        try:
            self._star_angle = 0.0
            self.github_btn.setIcon(QIcon(_render_star3d(0.0, palette=self._star_palette())))
        except Exception:
            pass

    def _restore_github_logo(self):
        if not getattr(self, "_star_active", False):
            return
        self._star_active = False
        try:
            self._star_timer.stop()
        except RuntimeError:
            pass
        button = self.github_btn
        button.setGraphicsEffect(None)
        button.setText("")
        button.setAccessibleName("GitHub")
        button.setIconSize(QSize(20, 20))
        self._update_github_icon()
        # Instant swap, then fade the logo back in (mirrors the 160ms
        # fade-in the star uses on the way out).
        try:
            effect = QGraphicsOpacityEffect(button)
            effect.setOpacity(0.0)
            button.setGraphicsEffect(effect)
            fade_in = QPropertyAnimation(effect, b"opacity", self)
            fade_in.setDuration(160)
            fade_in.setStartValue(0.0)
            fade_in.setEndValue(1.0)
            fade_in.finished.connect(lambda: button.setGraphicsEffect(None))
            fade_in.start(QAbstractAnimation.DeleteWhenStopped)
        except (RuntimeError, AttributeError):
            try:
                button.setGraphicsEffect(None)
            except RuntimeError:
                pass

    def _apply_theme(self, is_dark: bool):
        if getattr(self, "_is_updating_theme", False):
            return
        self._is_updating_theme = True
        try:
            self.is_dark = is_dark
            self.setStyleSheet(get_wizard_stylesheet(is_dark))
            apply_native_mica(int(self.winId()), is_dark)
            self._update_github_icon()
            self._apply_widget_theme()
            self.refresh_all()
            if getattr(self, "_star_active", False):
                try:
                    self.github_btn.setIcon(QIcon(_render_star3d(getattr(self, "_star_angle", 0.0), palette=self._star_palette())))
                except Exception:
                    pass
        finally:
            self._is_updating_theme = False

    def _sync_theme(self):
        if getattr(self, "_is_updating_theme", False):
            return
        current_dark = is_system_dark_mode()
        theme_sig = (current_dark, _accent_signature())
        if theme_sig == getattr(self, "_last_theme_sig", None):
            return
        self._last_theme_sig = theme_sig
        self._apply_theme(current_dark)

    def keyPressEvent(self, event):
        if self._armed_button is not None:
            if event.key() == Qt.Key_Escape:
                self._disarm()
                event.accept()
                return
            if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
                self._confirm_armed()
                event.accept()
                return
        super().keyPressEvent(event)

    def eventFilter(self, watched, event):
        try:
            weight_vp = (
                self.weight_scroll.viewport()
                if getattr(self, "weight_scroll", None) is not None
                else None
            )
        except RuntimeError:
            # Widget already destroyed during teardown; never touch it.
            weight_vp = None
        if (
            weight_vp is not None
            and watched is weight_vp
            and event.type() == QEvent.Type.Resize
        ):
            # A scrollbar showing/hiding re-wraps the flow into a different
            # row count; re-pin the container after Qt settles so the pinned
            # height can never drift from the real layup.
            QTimer.singleShot(0, self._resync_variant_height)
        if watched is self._armed_button:
            etype = event.type()
            if etype in (QEvent.Type.Enter, QEvent.Type.MouseMove):
                try:
                    x = event.position().x()
                except AttributeError:
                    x = event.pos().x()
                half = self._arm_half_at(x, watched.width())
                if getattr(self, "_armed_hover_half", None) != half:
                    self._armed_hover_half = half
                    self._paint_arm_halves(half)
            elif etype == QEvent.Type.Leave:
                if getattr(self, "_armed_hover_half", None) is not None:
                    self._armed_hover_half = None
                    self._paint_arm_halves(None)
        if (
            watched is self._armed_button
            and event.type() == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.MouseButton.LeftButton
        ):
            try:
                pos = event.position()
                x, y = pos.x(), pos.y()
            except AttributeError:
                x, y = event.pos().x(), event.pos().y()
            inside = watched.rect().contains(int(x), int(y))
            left_half = x < watched.width() * self._CONFIRM_FRACTION
            ready = time.monotonic() - self._armed_at >= self._ARM_DELAY_S
            if inside and left_half and ready:
                action = self._armed_action
                self._disarm()
                action()
            elif inside and left_half:
                # Early left-half click: ignore and stay armed, so a fast
                # double-click reads as "confirm" rather than "cancel".
                pass
            else:
                self._disarm()
            return True
        return super().eventFilter(watched, event)

    def changeEvent(self, event):
        super().changeEvent(event)
        if getattr(self, "_is_updating_theme", False):
            return
        if event.type() in (QEvent.ThemeChange, QEvent.ApplicationPaletteChange):
            self._sync_theme()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_responsive_layout()
        self._sync_variant_layout_height()
        panel = getattr(self, "cloud_panel", None)
        if panel is not None:
            try:
                panel.sync_height(self.height())
            except RuntimeError:
                pass
        if self._armed_button is not None:
            self._layout_arm_halves()
        cover = getattr(self, "_op_cover", None)
        cover_btn = getattr(self, "_op_cover_btn", None)
        if cover is not None and cover_btn is not None:
            try:
                cover.setGeometry(1, 1, max(1, cover_btn.width() - 2), max(1, cover_btn.height() - 2))
            except RuntimeError:
                pass

    def _sync_responsive_layout(self):
        if not hasattr(self, "setup_layout"):
            return

        is_compact = self.width() < 700
        if self._compact_layout == is_compact:
            return

        self._compact_layout = is_compact
        if is_compact:
            self.main_layout.setContentsMargins(24, 20, 24, 20)
            self.main_layout.setSpacing(16)
        else:
            self.main_layout.setContentsMargins(36, 28, 36, 28)
            self.main_layout.setSpacing(20)

        self.setup_card.updateGeometry()
        self.banner.updateGeometry()

    def _sync_variant_layout_height(self):
        if not hasattr(self, "weight_scroll"):
            return
        if not self.weight_scroll.isVisible() or self.weight_layout.count() == 0:
            self.weight_widget.setMinimumHeight(0)
            self.weight_widget.setMaximumHeight(16777215)
            # Forget the key while hidden: the next show must re-pin.
            # Keeping it let a later sync early-return while the container
            # was unpinned (collapsed to the viewport), which made the list
            # scroll through dead space past the last card.
            self._variant_geom_key = None
            return

        # Pin to the height the cards ACTUALLY occupy. A separate
        # heightForWidth() pass can disagree with the real layup (stale
        # viewport width, different column count after a scrollbar toggles,
        # unpolished cards), and any leftover shows up as empty rows past
        # the last card plus extra scroll range.
        content_height = 0
        for i in range(self.weight_layout.count()):
            item = self.weight_layout.itemAt(i)
            card = item.widget() if item is not None else None
            if card is None:
                continue
            try:
                g = card.geometry()
            except RuntimeError:
                continue
            content_height = max(content_height, g.y() + g.height())
        if content_height <= 0:
            # Cards not laid out yet (first build): estimate from the flow.
            viewport_width = self.weight_scroll.viewport().width()
            if viewport_width <= 0:
                viewport_width = self.weight_scroll.width()
            content_height = max(
                0, int(self.weight_layout.heightForWidth(max(0, viewport_width)))
            )

        geom_key = (self.weight_layout.count(), content_height)
        if geom_key == getattr(self, "_variant_geom_key", None):
            return
        self._variant_geom_key = geom_key
        try:
            self.weight_widget.setMinimumHeight(content_height)
            self.weight_widget.setMaximumHeight(content_height)
        except RuntimeError:
            return
        self.weight_widget.updateGeometry()

    def _resync_variant_height(self):
        try:
            if not hasattr(self, "weight_scroll"):
                return
            if self.weight_scroll.isVisible() and self.weight_layout.count():
                self.weight_layout.activate()
            self._sync_variant_layout_height()
        except RuntimeError:
            pass

    def nativeEvent(self, event_type, message):
        if event_type != b"windows_generic_MSG":
            return super().nativeEvent(event_type, message)

        try:
            msg = wintypes.MSG.from_address(int(message))
        except Exception:
            return super().nativeEvent(event_type, message)

        if msg.message in {
            WM_SETTINGCHANGE,
            WM_THEMECHANGED,
            WM_DWMCOLORIZATIONCOLORCHANGED,
        }:
            self._sync_theme()

        return super().nativeEvent(event_type, message)

    _ARMED_TICK = chr(0xE73E)
    _ARMED_CROSS = chr(0xE711)
    _ARMED_FONT_FAMILY = "Segoe MDL2 Assets"
    _ARMED_FONT_SIZE = 24
    _ARMED_CROSS_SIZE = 20
    _ARM_DELAY_S = 0.3
    _CONFIRM_FRACTION = 0.5

    def _arm_or_confirm(self, button, kind):
        now = time.monotonic()
        if self._armed_button is button:
            if now - self._armed_at < self._ARM_DELAY_S:
                return
            action = self._armed_action
            self._disarm()
            action()
            return
        self._arm(button, kind)

    def _arm(self, button, kind):
        self._disarm()
        self._armed_button = button
        self._armed_action = {
            "apply": self.on_apply,
            "restore": self._start_restore_op,
            "restart": self._do_restart,
        }[kind]
        colors = get_theme_colors(self.is_dark)
        window_bg = _opaque_window_bg(self.is_dark)
        role = button.property("buttonRole") or "secondary"
        face = {
            "primary": ("accent", "accent_hover", "accent_text"),
            "warning": ("accent", "accent_hover", "warning_text"),
        }.get(role, ("bg_card", "bg_button_hover", "text_primary"))
        self._armed_face = {
            "bg": _solid_color(colors[face[0]], window_bg),
            "hover": _solid_color(colors[face[1]], window_bg),
            "ink": colors[face[2]],
        }
        yes_label = QLabel(self._ARMED_TICK, button)
        no_label = QLabel(self._ARMED_CROSS, button)
        self._arm_labels = (yes_label, no_label)
        for label in self._arm_labels:
            label.setAttribute(Qt.WA_TransparentForMouseEvents)
            label.setAlignment(Qt.AlignCenter)
        self._armed_hover_half = None
        try:
            button.setMouseTracking(True)
        except RuntimeError:
            pass
        self._layout_arm_halves()
        self._paint_arm_halves(None)
        for label in self._arm_labels:
            label.show()
        button.setAccessibleDescription("Armed. Activate the left side or press Enter to confirm, or press Escape to cancel.")
        self._armed_at = time.monotonic()

    def _layout_arm_halves(self):
        button = self._armed_button
        labels = getattr(self, "_arm_labels", None)
        if button is None or not labels:
            return
        try:
            width, height = button.width(), button.height()
            mid = width // 2
            labels[0].setGeometry(0, 0, mid, height)
            labels[1].setGeometry(mid, 0, width - mid, height)
        except RuntimeError:
            pass

    def _arm_half_at(self, x, width):
        try:
            return 0 if float(x) < float(width) * self._CONFIRM_FRACTION else 1
        except (TypeError, ValueError):
            return 0

    def _paint_arm_halves(self, half):
        labels = getattr(self, "_arm_labels", None)
        face = getattr(self, "_armed_face", None)
        if not labels or not face:
            return
        for index, label in enumerate(labels):
            background = face["hover"] if index == half else face["bg"]
            try:
                size = self._ARMED_CROSS_SIZE if index == 1 else self._ARMED_FONT_SIZE
                divider = "border: none;"
                radius_css = (
                    "border-top-left-radius: 4px; border-bottom-left-radius: 4px; border-top-right-radius: 0px; border-bottom-right-radius: 0px;"
                    if index == 0
                    else "border-top-right-radius: 4px; border-bottom-right-radius: 4px; border-top-left-radius: 0px; border-bottom-left-radius: 0px;"
                )
                label.setText(self._ARMED_TICK if index == 0 else self._ARMED_CROSS)
                label.setStyleSheet(
                    f"font-family: '{self._ARMED_FONT_FAMILY}'; "
                    f"font-size: {size}px; "
                    f"color: {face['ink']}; background-color: {background}; {divider} {radius_css}"
                )
            except RuntimeError:
                pass

    def _confirm_armed(self):
        if self._armed_button is None:
            return
        if time.monotonic() - self._armed_at >= self._ARM_DELAY_S:
            action = self._armed_action
            self._disarm()
            action()

    def _disarm(self):
        button = self._armed_button
        self._armed_button = None
        self._armed_action = None
        self._armed_face = None
        self._armed_hover_half = None
        for label in (getattr(self, "_arm_labels", None) or ()):
            try:
                label.hide()
                label.deleteLater()
            except RuntimeError:
                pass
        self._arm_labels = None
        if button is not None:
            try:
                button.setAccessibleDescription("")
            except RuntimeError:
                pass
            try:
                button.setMouseTracking(False)
            except RuntimeError:
                pass

    def _on_local_pick(self):
        font_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Static TrueType Font",
            "",
            "Static TrueType fonts (*.ttf)",
        )
        if not font_path:
            return
        # A local pick replaces the cloud list — hide it (unless a cloud
        # download is actively running, in which case animate_hide() refuses).
        self._set_cloud_closed()
        self.cloud_panel.animate_hide()
        self._select_regular(font_path)

    def _select_regular(self, font_path):
        try:
            self.controller.set_regular_font(font_path)
        except Exception as exc:
            QMessageBox.warning(self, "Font not supported", str(exc))
            return False
        self._selection_dirty = True
        self._hide_applied_variants = False
        self.refresh_all()
        return True

    def _on_cloud_toggle(self):
        # The fetch button only ever shows the panel; hiding is the close
        # button's job, so a second click must not toggle it away.
        if self.cloud_panel.isVisible() and not getattr(self.cloud_panel, "_is_hiding", False):
            return
        # Preview cards step aside while the cloud list is open; the
        # panel's height cap reads sibling sizes, so it grows into the
        # freed space on its own.
        self._cloud_open = True
        self.refresh_all()
        self.cloud_panel.sync_height(self.height())
        self.cloud_panel.animate_show(self.height())
        self.cloud_panel.start_fetch(force=False)

    def _set_cloud_closed(self):
        self._cloud_open = False
        self.refresh_all()

    def _on_cloud_closed(self):
        self._set_cloud_closed()

    def _on_cloud_downloaded(self, local_paths):
        if not local_paths:
            return
        try:
            from github_fonts import pick_regular

            primary = pick_regular([Path(p) for p in local_paths])
        except Exception:
            primary = Path(local_paths[0])
        self._set_cloud_closed()
        if self._select_regular(str(primary)):
            self.cloud_panel.animate_hide()

    def on_apply_action(self):
        if self._apply_action == "restart":
            self._arm_or_confirm(self.apply_btn, "restart")
        else:
            self._arm_or_confirm(self.apply_btn, "apply")

    def _run_operation(self, func, btn, text):
        self._disarm()
        if self._op_thread and self._op_thread.isRunning():
            return

        for button in self._action_buttons:
            button.setEnabled(False)
        colors = get_theme_colors(self.is_dark)
        cover = QLabel(text, btn)
        cover.setAlignment(Qt.AlignCenter)
        cover.setGeometry(0, 0, btn.width(), btn.height())
        cover.setStyleSheet(
            "font-family: 'Segoe UI'; font-size: 13px; font-weight: 600; "
            f"color: {colors['accent_text']}; background-color: {colors['accent']}; "
            f"border: 1px solid {colors['accent']}; border-radius: 4px;"
        )
        cover.show()
        self._op_cover = cover
        self._op_cover_btn = btn
        self._set_button_role(btn, "primary")
        self._op_thread = OperationThread(func, self)
        self._op_thread.done.connect(lambda r: self._on_operation_done(r, btn))
        self._op_thread.finished.connect(self._op_thread.deleteLater)
        self._op_thread.start()

    def _on_operation_done(self, result, btn):
        cover = getattr(self, "_op_cover", None)
        self._op_cover = None
        self._op_cover_btn = None
        if cover is not None:
            try:
                cover.hide()
                cover.deleteLater()
            except RuntimeError:
                pass
        self._op_thread = None

        if not isinstance(result, OperationResult):
            result = OperationResult(
                False,
                "The operation finished with an unexpected result.",
                [repr(result)],
            )

        if btn == self.apply_btn and result.success:
            self._selection_dirty = False

        if not result.success:
            QMessageBox.warning(self, "Result", result.message)
        self.refresh_all()
        if btn == self.apply_btn and result.success:
            self._morph_to_star()

    def on_apply(self):
        self._run_operation(self.controller.apply, self.apply_btn, "Applying...")

    def on_restore(self):
        if getattr(self, "_restore_action", "restore") == "restart":
            self._arm_or_confirm(self.restore_btn, "restart")
            return
        self._arm_or_confirm(self.restore_btn, "restore")

    def _start_restore_op(self):
        self._run_operation(self.controller.restore, self.restore_btn, "Restoring...")

    def _do_restart(self):
        try:
            subprocess.run(["shutdown", "/r", "/t", "0"], check=True)
        except Exception as exc:
            QMessageBox.warning(self, "Restart Failed", f"Could not initiate Windows restart: {exc}\n\nPlease restart your computer manually to finish the setup.")

    def refresh_all(self):
        self._disarm()
        report = self.controller.refresh_preflight()
        colors = get_theme_colors(self.is_dark)

        is_pending = report.install_state in ("pending_reboot_apply", "pending_reboot_recovery")
        if not report.is_supported:
            self.banner.set_icon("\uEA39", colors["accent_icon"])
        elif not report.is_admin:
            self.banner.set_icon("\uE83D", colors["accent_icon"])
        elif is_pending:
            self.banner.set_icon("\uE895", colors["accent_icon"])
        elif report.install_state == "managed":
            self.banner.set_icon("\uE930", colors["accent_icon"])
        elif report.install_state == "partial":
            self.banner.set_icon("\uEA39", colors["accent_icon"])
        elif report.issues:
            self.banner.set_icon("\uEA39", colors["accent_icon"])
        else:
            self.banner.set_icon("\uE930", colors["accent_icon"])

        self.banner.set_content(report.headline, report.summary)

        regular_font = self.controller.selection.paths.get("regular")
        can_apply = report.can_apply_changes and regular_font is not None
        has_selected_font = regular_font is not None
        is_apply_pending = report.install_state == "pending_reboot_apply"
        is_recovery_pending = report.install_state == "pending_reboot_recovery"

        if is_recovery_pending:
            self._browse_action = "select"
            self._apply_action = "restart"
            self._restore_action = "restart"
            apply_text = "Restart Windows"
            restore_text = "Restart Windows"
            apply_visible = True
            restore_visible = False
            apply_available = True
            restore_available = True
        elif is_apply_pending:
            self._browse_action = "select"
            self._restore_action = "restore"
            if has_selected_font and self._selection_dirty:
                self._apply_action = "apply"
                apply_text = "Apply Changes"
                apply_available = can_apply
            else:
                self._apply_action = "restart"
                apply_text = "Restart Windows"
                apply_available = True
            restore_text = "Restore Original Fonts"
            apply_visible = True
            restore_visible = False
            restore_available = False
        else:
            self._browse_action = "select"
            self._apply_action = "apply"
            self._restore_action = "restore"
            apply_text = "Apply Changes"
            apply_available = can_apply
            restore_text = "Restore Original Fonts"
            apply_visible = has_selected_font
            restore_visible = report.install_state in ("managed", "partial")
            apply_available = apply_visible and can_apply
            restore_available = restore_visible and report.can_restore_defaults

        self.local_btn.setEnabled(not is_recovery_pending)
        self.local_btn.setVisible(not is_recovery_pending)
        self.fetch_btn.setEnabled(not is_recovery_pending)
        self.fetch_btn.setVisible(not is_recovery_pending)

        self.apply_btn.setText(apply_text)
        self.apply_btn.setEnabled(apply_available)
        self.apply_btn.setVisible(apply_visible)

        self.restore_btn.setEnabled(restore_available)
        self.restore_btn.setVisible(restore_visible)
        self.restore_btn.setText(restore_text)

        if not can_apply and self._apply_action != "restart":
            if not regular_font:
                self.apply_btn.setToolTip("Select a font to apply.")
            else:
                self.apply_btn.setToolTip(
                    "\n".join(report.issues) if report.issues else "Cannot apply changes right now."
                )
        else:
            self.apply_btn.setToolTip("")

        if not self.restore_btn.isEnabled() and self._restore_action != "restart":
            self.restore_btn.setToolTip("Cannot restore fonts right now.")
        else:
            self.restore_btn.setToolTip("")

        fetch_role = "secondary" if (has_selected_font or is_pending) else "primary"
        apply_role = "primary"
        restore_role = "secondary"

        self._set_button_role(self.local_btn, "secondary")
        self._set_button_role(self.fetch_btn, fetch_role)
        self._set_button_role(self.apply_btn, apply_role)
        self._set_button_role(self.restore_btn, restore_role)

        self.cur_font_lbl.setText(Path(regular_font).name if regular_font else "No font selected")

        cards_sig = (
            tuple(sorted((key, str(value)) for key, value in self.controller.selection.paths.items())),
            tuple(sorted((key, value) for key, value in self.controller.selection.labels.items())),
            self.is_dark,
        )
        rebuild_cards = cards_sig != getattr(self, "_cards_sig", None)
        if rebuild_cards:
            self._cards_sig = cards_sig
            self._variant_geom_key = None
            while self.weight_layout.count():
                item = self.weight_layout.takeAt(0)
                widget = item.widget()
                if widget:
                    if hasattr(widget, "cleanup"):
                        widget.cleanup()
                    widget.deleteLater()

        def _handle_card_change(w):
            current_path = self.controller.selection.paths.get(w) or self.controller.selection.paths.get("regular") or "."
            start_dir = str(Path(current_path).parent)
            if w == "variable":
                display_name = "Variable UI Font"
            else:
                display_name = w.replace("consolas_", "Consolas ").replace("_", " ").title()
            chosen_file, _ = QFileDialog.getOpenFileName(
                self,
                f"Select Font File for {display_name}",
                start_dir,
                "TrueType Fonts (*.ttf);;All Files (*.*)",
            )
            if chosen_file:
                try:
                    self.controller.set_card_override(w, chosen_file)
                    self._selection_dirty = True
                    self.refresh_all()
                except Exception as exc:
                    QMessageBox.warning(self, "Invalid Font", str(exc))

        def _handle_card_reset(w):
            self.controller.reset_card_override(w)
            self._selection_dirty = True
            self.refresh_all()

        cards_added = 0
        if rebuild_cards:
            for weight, font_path in self.controller.selection.paths.items():
                if font_path:
                    try:
                        is_manual = (self.controller.selection.labels.get(weight) == "manual")
                        card = WeightCard(
                            weight,
                            font_path,
                            is_manual=is_manual,
                            is_dark=self.is_dark,
                            on_change=_handle_card_change,
                            on_reset=_handle_card_reset,
                        )
                        self.weight_layout.addWidget(card)
                        card.show()
                        cards_added += 1
                    except (ValueError, OSError):
                        pass
        else:
            cards_added = self.weight_layout.count()

        show_variant_section = (
            has_selected_font
            and not is_recovery_pending
            and not getattr(self, "_cloud_open", False)
        )
        has_variants = show_variant_section and cards_added > 0
        self.variant_count_lbl.setText(f"{cards_added} styles" if has_variants else "No preview")

        self.variants_header.setVisible(show_variant_section)
        self.empty_variants.setVisible(show_variant_section and not has_variants)
        self.weight_scroll.setVisible(has_variants)
        if hasattr(self, "local_fonts_guide"):
            show_guide = (
                not has_selected_font
                and not is_recovery_pending
                and not getattr(self, "_cloud_open", False)
            )
            self.local_fonts_guide.setVisible(show_guide)
        if has_variants:
            self.weight_widget.show()
        # Lay the cards first, then pin to their real geometry: syncing
        # before activate() measured a stale or estimated layup.
        self.weight_layout.activate()
        self._sync_variant_layout_height()
        self.weight_widget.update()

    def closeEvent(self, event):
        op_thread = getattr(self, "_op_thread", None)
        if op_thread is not None and op_thread.isRunning():
            event.ignore()
            return
        try:
            self._stop_star_anim()
        except Exception:
            pass
        try:
            panel = getattr(self, "cloud_panel", None)
            if panel is not None:
                panel._kill_anim()
                preview_thread = getattr(panel, "_preview_thread", None)
                if preview_thread is not None and preview_thread.isRunning():
                    try:
                        preview_thread.requestInterruption()
                        preview_thread.wait(200)
                    except Exception:
                        pass
                fetch_thread = getattr(panel, "_fetch_thread", None)
                if fetch_thread is not None and fetch_thread.isRunning():
                    try:
                        fetch_thread.wait(200)
                    except Exception:
                        pass
                dl_thread = getattr(panel, "_dl_thread", None)
                if dl_thread is not None and dl_thread.isRunning():
                    try:
                        dl_thread.wait(200)
                    except Exception:
                        pass
        except Exception:
            pass
        event.accept()

    def run(self):
        self.show()
        # Re-assert the default size once native: creating the native
        # window during __init__ (mica/winId) eats ~20px of height.
        self.resize(1050, 650)
        return QApplication.instance().exec()

if __name__ == "__main__":
    from main import main
    sys.exit(main())
