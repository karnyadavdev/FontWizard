import ctypes
import math
import re
import subprocess
import sys
import time
import winreg
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QSize, QPoint, QPointF, QRect, QRectF, QUrl, QTimer, QEvent, QObject, QPropertyAnimation, QAbstractAnimation, QEasingCurve, QVariantAnimation, QParallelAnimationGroup
from PySide6.QtGui import (
    QBrush,
    QDesktopServices,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QIcon,
    QImage,
    QLinearGradient,
    QRadialGradient,
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QRegion,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QApplication,
    QAbstractButton,
    QCheckBox,
    QDialog,
    QFileDialog,
    QBoxLayout,
    QFrame,
    QGraphicsDropShadowEffect,
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

from settings import APP_GITHUB_URL, APP_NAME, WEIGHT_TARGETS, GITHUB_FONTS_REPO, GITHUB_FONTS_BRANCH, GITHUB_FONTS_URL, FONTS_DIR
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
            "bg_card": "rgba(255, 255, 255, 0.05)" if is_win11 else "#2B2B2B",
            "bg_card_hover": "rgba(255, 255, 255, 0.08)" if is_win11 else "#353535",
            "bg_button": "rgba(255, 255, 255, 0.06)" if is_win11 else "#2D2D2D",
            "bg_button_hover": "rgba(255, 255, 255, 0.09)" if is_win11 else "#383838",
            "bg_button_pressed": "rgba(255, 255, 255, 0.08)" if is_win11 else "#353535",
            "border_card": "rgba(255, 255, 255, 0.04)" if is_win11 else "#262626",
            "border_card_top": "rgba(255, 255, 255, 0.04)" if is_win11 else "#262626",
            "border_card_bottom": "rgba(255, 255, 255, 0.04)" if is_win11 else "#262626",
            "border_button": "rgba(255, 255, 255, 0.04)" if is_win11 else "#262626",
            "border_button_top": "rgba(255, 255, 255, 0.04)" if is_win11 else "#262626",
            "border_button_bottom": "rgba(255, 255, 255, 0.04)" if is_win11 else "#262626",

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
            "bg_dialog": "#2B2B2B",
            "bg_dialog_footer": "#242424",
            "tip_bg": "#2C2C2C",
            "tip_border": "rgba(255, 255, 255, 0.08)",
        }
    return {
        "bg_window": "transparent" if is_win11 else "#F3F3F3",
        "bg_card": "rgba(255, 255, 255, 0.7)" if is_win11 else "#FFFFFF",
        "bg_card_hover": "rgba(0, 0, 0, 0.05)" if is_win11 else "#F0F0F0",
        "bg_button": "rgba(255, 255, 255, 0.7)" if is_win11 else "#E5E5E5",
        "bg_button_hover": "rgba(0, 0, 0, 0.07)" if is_win11 else "#D8D8D8",
        "bg_button_pressed": "rgba(0, 0, 0, 0.04)" if is_win11 else "#DCDCDC",
        "border_card": "rgba(0, 0, 0, 0.05)" if is_win11 else "#E0E0E0",
        "border_card_top": "rgba(0, 0, 0, 0.05)" if is_win11 else "#E0E0E0",
        "border_card_bottom": "rgba(0, 0, 0, 0.05)" if is_win11 else "#E0E0E0",
        "border_button": "rgba(0, 0, 0, 0.05)" if is_win11 else "#E0E0E0",
        "border_button_top": "rgba(0, 0, 0, 0.05)" if is_win11 else "#E0E0E0",
        "border_button_bottom": "rgba(0, 0, 0, 0.05)" if is_win11 else "#E0E0E0",

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
        "bg_dialog": "#FFFFFF",
        "bg_dialog_footer": "#F9F9F9",
        "tip_bg": "#F9F9F9",
        "tip_border": "rgba(0, 0, 0, 0.05)",
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
    QDialog, QMessageBox {{ 
        background-color: {colors["bg_dialog"]}; 
        border: 1px solid {colors["border_card"]}; 
        border-radius: 8px;
    }}
    QToolTip {{
        background-color: {"#2C2C2C" if is_dark else "#F9F9F9"};
        color: {"#FFFFFF" if is_dark else "#1A1A1A"};
        border: 1px solid {"rgba(255, 255, 255, 0.12)" if is_dark else "rgba(0, 0, 0, 0.10)"};
        border-radius: 4px;
        padding: 4px 8px;
        font-size: 12px;
        font-family: {font_stack};
    }}
    #AppTitle {{ font-size: 28px; font-weight: 600; font-family: {title_font_stack}; letter-spacing: -0.5px; }}
    #AppSubtitle {{ color: {colors["text_secondary"]}; font-size: 14px; margin-top: 0px; }}
    #SectionHeader {{ font-weight: 600; font-size: 18px; padding: 0; font-family: {title_font_stack}; }}
    #SectionMeta {{ color: {colors["text_muted"]}; font-size: 13px; }}
    
    #Banner, #SetupCard, #VariantCard, #EmptyState, #CloudPanel {{ 
        background-color: {colors["bg_card"]}; 
        border-top: 1px solid {colors["border_card_top"]}; 
        border-bottom: 1px solid {colors["border_card_bottom"]}; 
        border-left: 1px solid {colors["border_card"]}; 
        border-right: 1px solid {colors["border_card"]}; 
        border-radius: 4px; 
    }}
    #VariantCard:hover {{ 
        background-color: {colors["bg_card_hover"]}; 
    }}
    #BannerIcon {{ font-family: 'Segoe Fluent Icons'; font-size: 20px; }}
    #BannerTitle {{ font-family: 'Segoe UI Variable Text', 'Segoe UI', sans-serif; font-size: 13.5px; font-weight: 600; color: {colors["text_primary"]}; }}
    #BannerText {{ font-family: 'Segoe UI Variable Text', 'Segoe UI', sans-serif; font-size: 13px; color: {colors["text_secondary"]}; }}
    
    #CardTitle {{ font-weight: 600; font-size: 15px; }}
    #CardDesc {{ color: {colors["text_secondary"]}; font-size: 14px; }}
    #SelectedFont {{ color: {colors["text_secondary"]}; font-size: 14px; }}
    #VariantPreview {{ color: {colors["text_primary"]}; font-size: 18px; }}
    #VariantMeta {{ color: {colors["text_muted"]}; font-size: 12px; }}
    
    #CardChangeBtn {{
        background-color: transparent;
        border: none;
        border-radius: 4px;
        padding: 0;
        min-width: 32px;
        max-width: 32px;
        min-height: 32px;
        max-height: 32px;
        outline: none;
    }}
    #CardChangeBtn:hover {{
        background-color: {colors["bg_button_hover"]};
    }}
    #CardChangeBtn:pressed {{
        background-color: {colors["bg_button_pressed"]};
    }}
    
    QPushButton {{ 
        background-color: {colors["bg_button"]}; 
        border-top: 1px solid {colors["border_card_top"]}; 
        border-left: 1px solid {colors["border_card"]}; 
        border-right: 1px solid {colors["border_card"]}; 
        border-bottom: 1px solid {colors["border_card_bottom"]}; 
        border-radius: 4px; 
        padding: 0 14px 1px 14px; 
        min-height: 32px; 
        max-height: 32px; 
        font-family: 'Segoe UI Variable Text', 'Segoe UI', sans-serif;
        font-weight: 500; 
        font-size: 13.5px;
        color: {colors["text_primary"]};
        outline: none;
    }}
    QPushButton:focus {{
        border: 2px solid {colors["accent"]};
    }}
    QPushButton:hover {{ 
        background-color: {colors["bg_button_hover"]}; 
        border-top: 1px solid {colors["border_card_top"]}; 
        border-left: 1px solid {colors["border_card"]}; 
        border-right: 1px solid {colors["border_card"]}; 
        border-bottom: 1px solid {colors["border_card_bottom"]}; 
    }}
    QPushButton:pressed {{ 
        background-color: {colors["bg_button_hover"]}; 
        border: 1px solid {colors["border_card"]}; 
        padding: 0 14px 1px 14px;
    }}
    QPushButton:disabled {{ 
        color: {colors["text_muted"]}; 
        background-color: {colors["bg_button"]}; 
        border-top: 1px solid {colors["border_card_top"]}; 
        border-left: 1px solid {colors["border_card"]}; 
        border-right: 1px solid {colors["border_card"]}; 
        border-bottom: 1px solid {colors["border_card_bottom"]}; 
    }}
    #ActionButton {{
        background-color: {colors["bg_button"]};
        border-top: 1px solid {colors["border_card_top"]}; 
        border-left: 1px solid {colors["border_card"]}; 
        border-right: 1px solid {colors["border_card"]}; 
        border-bottom: 1px solid {colors["border_card_bottom"]}; 
        border-radius: 4px;
        min-height: 32px;
        max-height: 32px;
        outline: none;
    }}
    #ActionButton:focus {{
        border: 2px solid {colors["accent"]};
    }}
    #ActionButton[buttonRole="primary"] {{
        background-color: {colors["bg_button"]};
        border-top: 1px solid {colors["border_card_top"]}; 
        border-left: 1px solid {colors["border_card"]}; 
        border-right: 1px solid {colors["border_card"]}; 
        border-bottom: 1px solid {colors["border_card_bottom"]}; 
    }}
    #ActionButton:hover {{
        background-color: {colors["bg_button_hover"]};
        border-top: 1px solid {colors["border_card_top"]}; 
        border-left: 1px solid {colors["border_card"]}; 
        border-right: 1px solid {colors["border_card"]}; 
        border-bottom: 1px solid {colors["border_card_bottom"]}; 
    }}
    #ActionButton[buttonRole="primary"]:hover {{
        background-color: {colors["bg_button_hover"]};
        border-top: 1px solid {colors["border_card_top"]}; 
        border-left: 1px solid {colors["border_card"]}; 
        border-right: 1px solid {colors["border_card"]}; 
        border-bottom: 1px solid {colors["border_card_bottom"]}; 
    }}
    #ActionButton[pressed="true"] {{
        background-color: {colors["bg_button_hover"]};
        border: 1px solid {colors["border_card"]};
    }}
    #ActionButton:disabled {{
        background-color: {colors["bg_button"]};
        border-top: 1px solid {colors["border_card_top"]}; 
        border-left: 1px solid {colors["border_card"]}; 
        border-right: 1px solid {colors["border_card"]}; 
        border-bottom: 1px solid {colors["border_card_bottom"]}; 
    }}
    #ActionButton #ActionIconLocal {{
        background: transparent;
        border: none;
    }}
    #ActionButton #ActionIconFetch {{
        background: transparent;
        border: none;
    }}
    #ActionButton #ActionText {{
        color: {colors["text_primary"]};
        background: transparent;
        border: none;
        font-family: 'Segoe UI Variable Text', 'Segoe UI', sans-serif;
        font-size: 13.5px;
        font-weight: 500;
    }}
    
    QPushButton[buttonRole="primary"] {{ 
        background-color: {colors["accent"]}; 
        border: 1px solid {colors["accent"]}; 
        color: {colors["accent_text"]}; 
        font-family: 'Segoe UI Variable Text', 'Segoe UI', sans-serif;
        font-weight: 600;
        font-size: 13.5px;
        outline: none;
    }}
    QPushButton[buttonRole="primary"]:hover {{ 
        background-color: {colors["accent_hover"]}; 
        border: 1px solid {colors["accent_hover"]}; 
    }}
    QPushButton[buttonRole="primary"]:pressed {{ 
        background-color: {colors["accent_hover"]}; 
        border: 1px solid {colors["accent_hover"]}; 
    }}
    
    QPushButton[buttonRole="warning"] {{ 
        background-color: {colors["accent"]}; 
        border: 1px solid {colors["accent"]}; 
        color: {colors["accent_text"]}; 
        font-family: 'Segoe UI Variable Text', 'Segoe UI', sans-serif;
        font-weight: 600;
        outline: none;
    }}
    QPushButton[buttonRole="warning"]:hover {{ 
        background-color: {colors["accent_hover"]}; 
        border: 1px solid {colors["accent_hover"]}; 
    }}
    QPushButton[buttonRole="warning"]:pressed {{ 
        background-color: {colors["accent_hover"]}; 
        border: 1px solid {colors["accent_hover"]}; 
    }}
    
    QPushButton[buttonRole="danger"] {{ 
        background-color: {colors["bg_card"]}; 
        border: 1px solid {colors["border_card"]}; 
        color: {colors["text_primary"]}; 
    }}
    QPushButton[buttonRole="danger"]:hover {{ 
        background-color: {colors["bg_button_hover"]}; 
        border: 1px solid {colors["border_card"]}; 
    }}
    QPushButton[buttonRole="secondary"] {{ 
        background-color: {colors["bg_button"]}; 
        border-top: 1px solid {colors["border_card_top"]}; 
        border-left: 1px solid {colors["border_card"]}; 
        border-right: 1px solid {colors["border_card"]}; 
        border-bottom: 1px solid {colors["border_card_bottom"]}; 
        color: {colors["text_primary"]}; 
        /* IconActionButton parks its icon on a fixed 16px inset with text at
           50px; Qt would otherwise centre the icon+text group, which shifts the
           icon whenever the label changes ("Apply Changes" vs "Restart Windows"). */
        text-align: left;
    }}
    QPushButton[buttonRole="secondary"]:hover {{ 
        background-color: {colors["bg_button_hover"]}; 
        border-top: 1px solid {colors["border_card_top"]}; 
        border-left: 1px solid {colors["border_card"]}; 
        border-right: 1px solid {colors["border_card"]}; 
        border-bottom: 1px solid {colors["border_card_bottom"]}; 
    }}
    QPushButton:disabled,
    QPushButton[buttonRole="primary"]:disabled,
    QPushButton[buttonRole="warning"]:disabled,
    QPushButton[buttonRole="danger"]:disabled,
    QPushButton[buttonRole="secondary"]:disabled {{ 
        color: {colors["text_muted"]}; 
        background-color: {colors["bg_button"]}; 
        border-top: 1px solid {colors["border_card_top"]}; 
        border-left: 1px solid {colors["border_card"]}; 
        border-right: 1px solid {colors["border_card"]}; 
        border-bottom: 1px solid {colors["border_card_bottom"]}; 
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
    
    QScrollBar:vertical {{ border: none; background: transparent; width: 10px; margin: 0; }}
    QScrollBar::handle:vertical {{ 
        background: {"rgba(255, 255, 255, 0.40)" if is_dark else "rgba(0, 0, 0, 0.38)"}; 
        border-radius: 3px; 
        min-height: 36px; 
        margin: 2px 2px; 
    }}
    QScrollBar::handle:vertical:hover {{ 
        background: {"rgba(255, 255, 255, 0.65)" if is_dark else "rgba(0, 0, 0, 0.60)"}; 
    }}
    QScrollBar::handle:vertical:pressed {{ 
        background: {"rgba(255, 255, 255, 0.85)" if is_dark else "rgba(0, 0, 0, 0.80)"}; 
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ border: none; background: none; height: 0px; width: 0px; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

    QScrollBar:horizontal {{ border: none; background: transparent; height: 10px; margin: 0; }}
    QScrollBar::handle:horizontal {{ 
        background: {"rgba(255, 255, 255, 0.40)" if is_dark else "rgba(0, 0, 0, 0.38)"}; 
        border-radius: 3px; 
        min-width: 36px; 
        margin: 2px 2px; 
    }}
    QScrollBar::handle:horizontal:hover {{ 
        background: {"rgba(255, 255, 255, 0.65)" if is_dark else "rgba(0, 0, 0, 0.60)"}; 
    }}
    QScrollBar::handle:horizontal:pressed {{ 
        background: {"rgba(255, 255, 255, 0.85)" if is_dark else "rgba(0, 0, 0, 0.80)"}; 
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ border: none; background: none; height: 0px; width: 0px; }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}
    #CloudPanel {{
        background-color: {colors["bg_card"]};
        border-top: 1px solid {colors["border_card_top"]};
        border-bottom: 1px solid {colors["border_card_bottom"]};
        border-left: 1px solid {colors["border_card"]};
        border-right: 1px solid {colors["border_card"]};
        border-radius: 4px;
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
        border-top: 1px solid {colors["border_card_top"]};
        border-left: 1px solid {colors["border_card"]};
        border-right: 1px solid {colors["border_card"]};
        border-bottom: 1px solid {colors["border_card_bottom"]};
        border-radius: 4px;
        color: {colors["text_primary"]};
        font-family: 'Segoe UI';
        font-size: 13px;
        font-weight: 600;
        padding: 6px 12px;
    }}
    #CloudPanel QPushButton:hover {{
        background-color: {colors["bg_button_hover"]};
        border-top: 1px solid {colors["border_card_top"]};
        border-left: 1px solid {colors["border_card"]};
        border-right: 1px solid {colors["border_card"]};
        border-bottom: 1px solid {colors["border_card_bottom"]};
    }}
    #CloudPanel QPushButton:disabled {{
        color: {colors["text_muted"]};
        background-color: {colors["bg_card"]};
        border: 1px solid {colors["border_card"]};
    }}
    #CloudPanel #IconBtn, #CloudPanel #IconBtnRefresh {{
        background-color: transparent;
        border: none;
        border-radius: 4px;
        padding: 0;
        min-width: 28px;
        max-width: 28px;
        min-height: 28px;
        max-height: 28px;
    }}
    #CloudPanel #IconBtn:hover, #CloudPanel #IconBtnRefresh:hover {{
        background-color: {colors["bg_button_hover"]};
    }}
    #CloudPanel #IconBtn:pressed, #CloudPanel #IconBtnRefresh:pressed {{
        background-color: {colors["bg_button_pressed"]};
    }}
    #CloudPanel #IconBtn:disabled, #CloudPanel #IconBtnRefresh:disabled {{
        background-color: transparent;
        border: none;
    }}
    #CloudFolderRow {{
        background-color: transparent;
        border: 1px solid transparent;
        border-radius: 4px;
        text-align: left;
        padding: 0px;
    }}
    #CloudFolderRow:hover {{
        background-color: {colors["bg_card_hover"]};
        border: 1px solid {"rgba(255, 255, 255, 0.04)" if is_dark else "rgba(0, 0, 0, 0.04)"};
    }}
    #CloudFolderRow:pressed {{
        background-color: {colors["bg_button_pressed"]};
    }}
    #CloudFolderRow:disabled {{
        background-color: transparent;
        border: 1px solid transparent;
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
        font-size: 34px;
        font-weight: 400;
        background: transparent;
    }}
    #CloudFolderRow:disabled #CloudFolderPreview {{
        color: {colors["text_muted"]};
    }}
    QCheckBox {{
        color: {colors["text_secondary"]};
        font-size: 13px;
        font-weight: 500;
        spacing: 8px;
    }}
    QCheckBox:hover {{
        color: {colors["text_primary"]};
    }}
    QPushButton#IconBtnInfo {{
        background: transparent;
        border: none;
        padding: 0px;
        margin: 0px;
        min-width: 20px;
        max-width: 20px;
        min-height: 20px;
        max-height: 20px;
        border-radius: 10px;
        outline: none;
    }}
    QPushButton#IconBtnInfo:hover {{
        background-color: {colors["bg_card_hover"]};
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
        if self.pixmap() and not self.pixmap().isNull():
            super().paintEvent(event)
            return
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


class Win11ProgressRing(QWidget):
    """Rotating accent-tinted action icon shown while an operation runs.

    Replaces the old 5-dot ring but keeps the exact same API (``_timer``,
    ``_angle``, ~60 fps) so ButtonProgressCover and the ghost test harness
    work untouched. The glyph is the same circular-arrow artwork the Restart
    button uses, recoloured to the accent so the busy cue stays on-palette.
    """
    _ICON_ASSET = "action-restart.png"
    _ICON_PX = 18          # logical px, centred inside the 20px box
    _ICON_CACHE = {}       # (r, g, b, a, px, dpr) -> tinted QPixmap

    def __init__(self, size=16, color=None, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._size = size
        self._color = color if color is not None else QColor(255, 255, 255)
        self._angle = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._timer.start(16)  # ~60 fps

    def _rotate(self):
        # Decrementing (not incrementing) makes the glyph spin
        # counter-clockwise: QPainter.rotate() is clockwise for positive
        # angles. Reversing here rather than at draw time keeps the dot
        # fallback path -- which reads _angle directly -- consistent too.
        self._angle = (self._angle - 4.5) % 360.0
        self.update()

    def _tinted_icon(self):
        """The restart glyph recoloured to the accent, cached per colour.

        Built once per colour rather than per frame: paintEvent runs at
        ~60fps and re-tinting there would allocate a pixmap 60 times a
        second for no visual gain.
        """
        try:
            dpr = float(self.devicePixelRatioF())
        except AttributeError:
            dpr = 1.0
        c = self._color
        key = (c.red(), c.green(), c.blue(), c.alpha(),
               self._ICON_PX, round(dpr, 2))
        cached = self._ICON_CACHE.get(key)
        if cached is not None:
            return cached

        try:
            src_path = get_asset_path(self._ICON_ASSET)
        except Exception:
            return None
        if not src_path.exists():
            return None
        src = QPixmap(str(src_path))
        if src.isNull():
            return None

        px = max(1, int(round(self._ICON_PX * dpr)))
        src = src.scaled(px, px, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        tinted = QPixmap(src.size())
        tinted.fill(Qt.transparent)
        painter = QPainter(tinted)
        painter.drawPixmap(0, 0, src)
        # Keep the glyph's own alpha, replace its blue with the accent.
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(tinted.rect(), c)
        painter.end()
        tinted.setDevicePixelRatio(dpr)

        if len(self._ICON_CACHE) > 32:
            self._ICON_CACHE.clear()
        self._ICON_CACHE[key] = tinted
        return tinted

    def paintEvent(self, event):
        icon = self._tinted_icon()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        if icon is not None:
            # Rotate about the widget centre; icon is dpr-aware so it stays
            # crisp on scaled displays and draws at _ICON_PX logical px.
            painter.translate(self._size / 2.0, self._size / 2.0)
            painter.rotate(self._angle)
            half = self._ICON_PX / 2.0
            painter.drawPixmap(-half, -half, icon)
            painter.end()
            return
        # Asset unavailable: fall back to the original 5-dot ring rather than
        # showing an empty box.
        center = self._size / 2.0
        radius = (self._size - 4) / 2.0
        for i in range(5):
            rad = math.radians(self._angle - (i * 22.0))
            x = center + radius * math.cos(rad)
            y = center + radius * math.sin(rad)
            r = 1.3 - (i * 0.15)
            alpha = int(255 * (1.0 - (i * 0.18)))
            c = QColor(self._color)
            c.setAlpha(max(40, alpha))
            painter.setBrush(QBrush(c))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QRectF(x - r, y - r, r * 2, r * 2))
        painter.end()


class ButtonProgressCover(QFrame):
    """Overlay displayed on action buttons during operations.

    The cover is a child of the button and, on neutral faces, paints no
    background or border of its own: the button's own face shows through
    untouched, so it looks exactly as it did before the click. Because the
    cover is see-through, the button's original icon and label are blanked
    while it is up (otherwise they would ghost through next to the cover's
    label) and put back by restore().
    """
    def __init__(self, initial_text, btn, bg_color=None, is_dark=None):
        super().__init__(btn)
        if is_dark is None:
            win = btn.window() if hasattr(btn, "window") else None
            is_dark = getattr(win, "is_dark", is_system_dark_mode())
        self.is_dark = is_dark
        self._btn = btn
        self.setGeometry(0, 0, btn.width(), btn.height())
        colors = get_theme_colors(is_dark)

        is_accent_face = bool(bg_color) and bg_color == colors["accent"]
        if is_accent_face:
            face = bg_color
            borders = (
                f"border-top: 1px solid {bg_color};"
                f"border-left: 1px solid {bg_color};"
                f"border-right: 1px solid {bg_color};"
                f"border-bottom: 1px solid {bg_color};"
            )
        else:
            # Neutral by default: no fill, no border. The button underneath
            # paints its own face (the very face it showed before the click),
            # so there is nothing to match and no seam is possible -- and no
            # accent pill is ever laid over a non-accent button.
            face = "transparent"
            borders = "border: none;"

        # The cover is see-through, so the button's own icon and label must not
        # be under it: blank them for the duration and restore afterwards.
        # The action buttons are fixed-size (160x34), so this cannot shift
        # the layout.
        self._saved_text = btn.text()
        self._saved_icon = btn.icon()
        self._saved_icon_size = btn.iconSize()
        btn.setText("")
        btn.setIcon(QIcon())

        self.setStyleSheet(
            f"QFrame, QFrame:disabled {{"
            f"  background-color: {face};"
            f"  {borders}"
            f"  border-radius: 4px;"
            f"}}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 0)
        # Wider gap pushes the spinner left while the pair stays centred.
        lay.setSpacing(14)
        lay.setAlignment(Qt.AlignCenter)

        text_color = colors["accent_text"] if is_accent_face else colors["text_primary"]
        # Keep the ring on the accent so a neutral cover still reads as busy.
        spinner_color = QColor(text_color if is_accent_face else colors["accent"])

        self.spinner = Win11ProgressRing(size=20, color=spinner_color, parent=self)
        self.label = QLabel(initial_text, self)
        self.label.setStyleSheet(
            f"QLabel, QLabel:disabled {{"
            f"  color: {text_color};"
            f"  font-family: 'Segoe UI Variable Text', 'Segoe UI';"
            f"  font-size: 13.5px;"
            f"  font-weight: 600;"
            f"  border: none;"
            f"  background: transparent;"
            f"}}"
        )
        lay.addWidget(self.spinner)
        lay.addWidget(self.label)
        self.show()
        self.raise_()

    def setText(self, text: str):
        self.setToolTip(text)
        metrics = QFontMetrics(self.label.font())
        # Budget the label can use: cover margins (10+10) + spinner (20) +
        # spinner-to-label gap (14) = 54, so it never runs past the right
        # margin or under the spinner, even for "Restart Windows".
        available_w = max(60, self.width() - 54)
        elided = metrics.elidedText(text, Qt.TextElideMode.ElideRight, available_w)
        self.label.setText(elided)

    set_text = setText

    def restore(self):
        """Put the covered button's original text and icon back.

        Called whenever the cover goes away. Safe to call more than once and
        safe if the widgets are already gone.
        """
        btn = self._btn
        try:
            btn.setText(self._saved_text)
            btn.setIcon(self._saved_icon)
            btn.setIconSize(self._saved_icon_size)
        except RuntimeError:
            pass


class WinUI3ToolTip(QFrame):
    """Modern WinUI 3 / Fluent 2 ToolTip with translucent background,
    elevation drop shadow, 6px corner radius, Segoe UI Variable Caption typography,
    and smooth fade-in animation."""
    _instance = None

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._active_target = None
        self._is_dark = True

        outer_lay = QVBoxLayout(self)
        outer_lay.setContentsMargins(10, 10, 10, 10)

        self.container = QFrame(self)
        self.container_lay = QVBoxLayout(self.container)
        self.container_lay.setContentsMargins(9, 5, 9, 5)

        self.label = QLabel(self.container)
        self.label.setWordWrap(True)
        self.container_lay.addWidget(self.label)
        outer_lay.addWidget(self.container)

        self.shadow = QGraphicsDropShadowEffect(self.container)
        self.shadow.setBlurRadius(16)
        self.shadow.setOffset(0, 4)
        self.container.setGraphicsEffect(self.shadow)

        self.anim = QPropertyAnimation(self, b"windowOpacity")
        self.anim.setDuration(120)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def show_tip(self, text: str, target: QWidget, is_dark: bool = True):
        if not text or not target or not target.isVisible():
            self.hide_tip()
            return

        self._active_target = target
        self._is_dark = is_dark
        colors = get_theme_colors(is_dark)

        bg = colors.get("tip_bg", "#2C2C2C" if is_dark else "#F9F9F9")
        border = colors.get("tip_border", "rgba(255, 255, 255, 0.08)" if is_dark else "rgba(0, 0, 0, 0.05)")
        text_color = colors.get("text_primary", "#FFFFFF" if is_dark else "rgba(0, 0, 0, 0.9)")

        self.container.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 4px;
            }}
        """)
        self.label.setStyleSheet(f"""
            QLabel {{
                color: {text_color};
                font-family: 'Segoe UI Variable Text', 'Segoe UI', sans-serif;
                font-size: 12px;
                font-weight: 400;
                background: transparent;
                border: none;
            }}
        """)
        self.label.setText(text)
        self.shadow.setColor(QColor(0, 0, 0, 95 if is_dark else 30))

        self.container.setMaximumWidth(360)
        self.adjustSize()

        target_rect = target.rect()
        target_top_left = target.mapToGlobal(QPoint(0, 0))
        target_center_x = target_top_left.x() + target_rect.width() // 2

        tip_w = self.width()
        tip_h = self.height()
        pos_x = target_center_x - tip_w // 2
        pos_y = target_top_left.y() + target_rect.height() + 4 - 10

        screen = target.screen() or QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            if pos_y + tip_h > geo.bottom():
                pos_y = target_top_left.y() - tip_h - 4 + 10
            if pos_x < geo.left() + 8:
                pos_x = geo.left() + 8
            elif pos_x + tip_w > geo.right() - 8:
                pos_x = geo.right() - tip_w - 8

        self.move(pos_x, pos_y)
        self.setWindowOpacity(0.0)
        self.show()
        self.anim.stop()
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.start()

    def hide_tip(self):
        self._active_target = None
        if hasattr(self, "anim"):
            self.anim.stop()
        self.hide()


class WinUI3ToolTipFilter(QObject):
    """Global event filter that intercepts legacy Qt tooltips and seamlessly
    presents authentic WinUI 3 tooltips with standard 280ms hover delay."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(280)
        self._timer.timeout.connect(self._on_timer_timeout)
        self._pending_target = None
        self._pending_text = ""
        self._is_dark = True

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if not isinstance(watched, QWidget):
            return super().eventFilter(watched, event)

        etype = event.type()
        if etype == QEvent.ToolTip:
            tip_text = watched.toolTip()
            if tip_text:
                self._pending_target = watched
                self._pending_text = tip_text
                win = watched.window()
                self._is_dark = getattr(win, "is_dark", True)
                self._timer.start()
                return True
            else:
                self._cancel()
                return False

        elif etype in (QEvent.Leave, QEvent.MouseButtonPress, QEvent.MouseButtonRelease,
                       QEvent.Wheel, QEvent.KeyPress, QEvent.WindowDeactivate):
            self._cancel()

        return super().eventFilter(watched, event)

    def _on_timer_timeout(self):
        try:
            if self._pending_target and self._pending_target.isVisible():
                WinUI3ToolTip.instance().show_tip(self._pending_text, self._pending_target, self._is_dark)
        except RuntimeError:
            pass

    def _cancel(self):
        self._timer.stop()
        self._pending_target = None
        self._pending_text = ""
        try:
            WinUI3ToolTip.instance().hide_tip()
        except Exception:
            pass


class WinUI3ToggleSwitch(QAbstractButton):
    """Modern Windows 11 WinUI 3 ToggleSwitch widget with smooth sliding thumb and full UIA accessibility."""
    def __init__(self, checked=False, is_dark=True, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(bool(checked))
        self.is_dark = is_dark
        self.setFixedSize(40, 20)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self.setAccessibleName("Asian & regional system fonts")
        self.setAccessibleDescription("Toggle patching regional Asian system fonts")
        self._thumb_pos = 1.0 if self.isChecked() else 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(120)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim_val)
        self.toggled.connect(self._on_toggled_anim)

    def _on_anim_val(self, val):
        self._thumb_pos = float(val)
        self.update()

    def _on_toggled_anim(self, checked):
        if self.isVisible():
            self._anim.stop()
            self._anim.setStartValue(self._thumb_pos)
            self._anim.setEndValue(1.0 if checked else 0.0)
            self._anim.start()
        else:
            self._thumb_pos = 1.0 if checked else 0.0
            self.update()

    def toggle(self):
        self.setChecked(not self.isChecked())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        radius = h / 2.0
        enabled = self.isEnabled()

        accent_color, _, _, _ = get_windows_accent_color(self.is_dark)
        accent_col = QColor(accent_color)
        off_col = QColor("#333333" if self.is_dark else "#E5E5E5")

        t = self._thumb_pos
        if enabled:
            r = int(off_col.red() * (1.0 - t) + accent_col.red() * t)
            g = int(off_col.green() * (1.0 - t) + accent_col.green() * t)
            b = int(off_col.blue() * (1.0 - t) + accent_col.blue() * t)
            bg_col = QColor(r, g, b)
        else:
            bg_col = QColor("#555555" if self.isChecked() else ("#252525" if self.is_dark else "#EEEEEE"))

        path = QPainterPath()
        path.addRoundedRect(0.5, 0.5, w - 1.0, h - 1.0, radius, radius)
        painter.fillPath(path, bg_col)

        border_alpha = int(25 * (1.0 - t)) if self.is_dark else int(35 * (1.0 - t))
        border_col = QColor(255, 255, 255, border_alpha) if self.is_dark else QColor(0, 0, 0, border_alpha)
        painter.setPen(QPen(border_col, 1))
        painter.drawPath(path)

        # Thumb
        thumb_x = radius + (w - 2 * radius) * t
        thumb_col = QColor("#FFFFFF") if (t > 0.5 or not self.is_dark) else QColor("#D0D0D0")
        painter.setPen(Qt.NoPen)
        painter.setBrush(thumb_col)
        thumb_r = 5.5 + 0.5 * t
        painter.drawEllipse(QPointF(thumb_x, radius), thumb_r, thumb_r)

        # High-visibility focus indicator when focused via Tab
        if self.hasFocus():
            painter.setPen(QPen(accent_col, 2.0, Qt.SolidLine))
            painter.setBrush(Qt.NoBrush)
            focus_path = QPainterPath()
            focus_path.addRoundedRect(0.5, 0.5, w - 1.0, h - 1.0, radius, radius)
            painter.drawPath(focus_path)


class SmokeOverlay(QWidget):
    """Semi-transparent modal scrim (SmokeFillColorDefault) that dims the parent window when a ContentDialog opens."""
    def __init__(self, parent, on_dismiss=None):
        super().__init__(parent)
        self._on_dismiss = on_dismiss
        self.setGeometry(parent.rect())
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        is_dark = getattr(parent, "is_dark", True)
        self.smoke_color = QColor(0, 0, 0, 115 if is_dark else 65)
        if parent:
            parent.installEventFilter(self)
        self.show()

    def eventFilter(self, obj, event):
        if obj is self.parent() and event.type() == QEvent.Resize:
            self.setGeometry(self.parent().rect())
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        if callable(self._on_dismiss):
            self._on_dismiss()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.smoke_color)


class WinUI3ContentDialog(QDialog):
    """
    Authentic Windows 11 WinUI 3 ContentDialog according to generic.xaml specs:
    - 2-tier card: DialogSpace (Title + Body) + CommandSpace (tinted footer band with top divider)
    - OverlayCornerRadius = 8px
    - Segoe UI Variable typography
    - Proper Fluent badge integration
    - Parent window smoke overlay (SmokeFillColorDefault)
    - 140ms smooth entrance animation
    - Dynamic word-wrap bounding rect calculation preventing any vertical text clipping
    """
    def __init__(self, title_text, body_text, primary_btn="OK", secondary_btn=None, parent=None, icon_kind=None, is_accent_btn=False, light_dismiss=False):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self.setFixedWidth(460)

        # Override application QDialog stylesheet to guarantee transparent backdrop for drop shadow
        self.setStyleSheet("QDialog { background: transparent; border: none; }")

        is_dark = getattr(parent, "is_dark", True) if parent is not None else True
        colors = get_theme_colors(is_dark, is_windows_11())

        bg_card = "#2B2B2B" if is_dark else "#FFFFFF"
        bg_footer = "#242424" if is_dark else "#F9F9F9"
        border_col = "rgba(255, 255, 255, 0.09)" if is_dark else "rgba(0, 0, 0, 0.08)"
        border_divider = "rgba(255, 255, 255, 0.08)" if is_dark else "rgba(0, 0, 0, 0.06)"
        text_primary = colors["text_primary"]
        text_secondary = colors["text_secondary"]

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # Outer Card
        self.card = QFrame(self)
        self.card.setObjectName("WinUI3Card")
        self.card.setStyleSheet(f"""
            #WinUI3Card {{
                background-color: {bg_card};
                border: 1px solid {border_col};
                border-radius: 8px;
            }}
        """)

        # Ambient + Directional Shadow
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(32)
        shadow.setColor(QColor(0, 0, 0, 140 if is_dark else 45))
        shadow.setOffset(0, 8)
        self.card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # 1. DialogSpace (Content Area)
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(24, 24, 24, 20)
        content_layout.setSpacing(12)

        # Title row (with optional Fluent icon badge)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(12)

        if icon_kind in ("info", "warning", "error", "restart"):
            status_map = {
                "info": "info",
                "warning": "warning",
                "error": "error",
                "restart": "restart",
            }
            icon_p = get_asset_path(f"status-{status_map.get(icon_kind, 'info')}.png")
            if icon_p.exists():
                badge = QLabel()
                pix = QPixmap(str(icon_p))
                dpr = getattr(self, "devicePixelRatioF", lambda: 1.0)()
                sz = int(28 * dpr)
                scaled = pix.scaled(sz, sz, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                scaled.setDevicePixelRatio(dpr)
                badge.setPixmap(scaled)
                badge.setFixedSize(28, 28)
                badge.setAlignment(Qt.AlignCenter)
                title_row.addWidget(badge, 0, Qt.AlignVCenter)
            elif icon_kind == "info":
                badge = QLabel("ℹ")
                badge.setFixedSize(26, 26)
                badge.setAlignment(Qt.AlignCenter)
                badge.setStyleSheet("""
                    background-color: #0078D4;
                    color: #FFFFFF;
                    border-radius: 13px;
                    font-family: 'Segoe UI', sans-serif;
                    font-size: 15px;
                    font-weight: bold;
                """)
                title_row.addWidget(badge, 0, Qt.AlignVCenter)
            elif icon_kind == "warning":
                badge = QLabel("⚠")
                badge.setFixedSize(28, 28)
                badge.setAlignment(Qt.AlignCenter)
                badge.setStyleSheet("""
                    color: #FFB900;
                    font-size: 24px;
                    background: transparent;
                """)
                title_row.addWidget(badge, 0, Qt.AlignVCenter)

        title_lbl = QLabel(title_text)
        title_lbl.setStyleSheet(f"""
            font-family: 'Segoe UI Variable Display', 'Segoe UI', sans-serif;
            font-size: 20px;
            font-weight: 600;
            color: {text_primary};
            background: transparent;
        """)
        title_row.addWidget(title_lbl, 1, Qt.AlignVCenter)
        content_layout.addLayout(title_row)

        body_lbl = QLabel(body_text)
        body_lbl.setWordWrap(True)
        body_lbl.setStyleSheet(f"""
            font-family: 'Segoe UI Variable Text', 'Segoe UI', sans-serif;
            font-size: 14px;
            color: {text_secondary};
            background: transparent;
        """)

        # Precise dynamic wrapped text height calculation via QTextDocument to prevent clipping
        f = body_lbl.font()
        f.setFamily("Segoe UI Variable Text" if is_windows_11() else "Segoe UI")
        f.setPixelSize(14)
        body_lbl.setFont(f)

        doc = QTextDocument()
        doc.setDefaultFont(f)
        # Content width inside 460px card (460 - 2*16 outer margins - 2*24 content margins = 380px)
        doc.setTextWidth(380.0)
        doc.setPlainText(body_text)
        needed_height = int(math.ceil(doc.size().height())) + 8

        body_lbl.setMinimumHeight(needed_height)
        if needed_height > 260:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
            scroll.setWidget(body_lbl)
            scroll.setFixedHeight(260)
            content_layout.addWidget(scroll)
        else:
            content_layout.addWidget(body_lbl)
        card_layout.addWidget(content_widget)

        # 2. CommandSpace (Dedicated Tinted Footer Band)
        footer_widget = QFrame()
        footer_widget.setObjectName("CommandSpace")
        footer_widget.setStyleSheet(f"""
            #CommandSpace {{
                background-color: {bg_footer};
                border-top: 1px solid {border_divider};
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }}
        """)
        footer_layout = QHBoxLayout(footer_widget)
        footer_layout.setContentsMargins(24, 16, 24, 16)
        footer_layout.setSpacing(8)
        footer_layout.addStretch()

        if secondary_btn:
            s_btn = QPushButton(secondary_btn)
            s_btn.setCursor(Qt.PointingHandCursor)
            s_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {"rgba(255, 255, 255, 0.06)" if is_dark else "#FFFFFF"};
                    color: {text_primary};
                    border: 1px solid {"rgba(0, 0, 0, 0.35)" if is_dark else "rgba(0, 0, 0, 0.08)"};
                    {"border-bottom: 1px solid rgba(0, 0, 0, 0.40);" if is_dark else "border-bottom: 1px solid rgba(0, 0, 0, 0.16);"}
                    border-radius: 4px;
                    padding: 0 20px;
                    min-height: 32px;
                    max-height: 32px;
                    font-family: 'Segoe UI Variable Text', sans-serif;
                    font-size: 13px;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background-color: {"rgba(255, 255, 255, 0.09)" if is_dark else "rgba(0, 0, 0, 0.06)"};
                }}
                QPushButton:pressed {{
                    background-color: {"rgba(255, 255, 255, 0.03)" if is_dark else "rgba(0, 0, 0, 0.12)"};
                }}
            """)
            s_btn.clicked.connect(self.reject)
            footer_layout.addWidget(s_btn)

        p_btn = QPushButton(primary_btn)
        p_btn.setCursor(Qt.PointingHandCursor)
        p_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {"rgba(255, 255, 255, 0.06)" if is_dark else "#FFFFFF"};
                color: {text_primary};
                border: 1px solid {"rgba(0, 0, 0, 0.35)" if is_dark else "rgba(0, 0, 0, 0.08)"};
                {"border-bottom: 1px solid rgba(0, 0, 0, 0.40);" if is_dark else "border-bottom: 1px solid rgba(0, 0, 0, 0.16);"}
                border-radius: 4px;
                padding: 0 28px;
                min-height: 32px;
                max-height: 32px;
                font-family: 'Segoe UI Variable Text', sans-serif;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {"rgba(255, 255, 255, 0.09)" if is_dark else "rgba(0, 0, 0, 0.06)"};
            }}
            QPushButton:pressed {{
                background-color: {"rgba(255, 255, 255, 0.03)" if is_dark else "rgba(0, 0, 0, 0.12)"};
            }}
        """)
        p_btn.clicked.connect(self.accept)
        footer_layout.addWidget(p_btn)

        card_layout.addWidget(footer_widget)
        main_layout.addWidget(self.card)
        content_widget.adjustSize()
        self.card.adjustSize()
        self.adjustSize()

        if parent is not None:
            parent_geom = parent.geometry()
            x = parent_geom.x() + (parent_geom.width() - self.width()) // 2
            y = parent_geom.y() + (parent_geom.height() - self.height()) // 2
            self.move(max(0, x), max(0, y))

    @classmethod
    def show_dialog(cls, parent, title, message, primary_btn="OK", secondary_btn=None, icon_kind=None, is_accent_btn=False, light_dismiss=False):
        dlg_instance = None
        filter_obj = None

        overlay = SmokeOverlay(parent) if parent is not None and hasattr(parent, "rect") and hasattr(parent, "isVisible") and parent.isVisible() else None
        try:
            dlg_instance = cls(title, message, primary_btn=primary_btn, secondary_btn=secondary_btn, parent=parent, icon_kind=icon_kind, is_accent_btn=is_accent_btn, light_dismiss=light_dismiss)
            if light_dismiss:
                from PySide6.QtCore import QObject
                class LightDismissFilter(QObject):
                    def eventFilter(self, obj, event):
                        if event.type() == QEvent.MouseButtonPress and dlg_instance is not None:
                            try:
                                pos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
                                if not dlg_instance.geometry().contains(pos):
                                    dlg_instance.reject()
                                    return True
                            except Exception:
                                pass
                        return False
                filter_obj = LightDismissFilter()
                qApp.installEventFilter(filter_obj)

            return dlg_instance.exec()
        finally:
            if filter_obj is not None:
                try:
                    qApp.removeEventFilter(filter_obj)
                except Exception:
                    pass
            if overlay is not None:
                overlay.hide()
                overlay.deleteLater()

    @classmethod
    def show_cjk_info(cls, parent):
        return cls.show_dialog(
            parent,
            title="Asian & Regional System Fonts",
            message=(
                "99% of Asian apps and websites already work fine.\n\n"
                "Only enable if you use specific apps or websites (like WeChat, LINE, KakaoTalk, etc.) that force regional system fonts instead of normal system fonts."
            ),
            primary_btn="Got it",
            icon_kind="info",
            is_accent_btn=False,
            light_dismiss=True
        )

    @classmethod
    def show_warning(cls, parent, title, message, primary_btn="OK"):
        return cls.show_dialog(
            parent,
            title=title,
            message=message,
            primary_btn=primary_btn,
            icon_kind="warning",
            is_accent_btn=False,
            light_dismiss=False
        )


class StatusBanner(QFrame):
    """Modern Windows 11 WinUI 3 InfoBar control with severity-themed tinting, fluent iconography, and bold headline."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Banner")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(14)
        
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
        name_map = {
            "\uE930": "success",
            "\uEA39": "warning" if str(color).upper() in ("#FFB900", "WARNING") else "error",
            "\uE83D": "admin",
            "\uE895": "restart",
            "success": "success",
            "warning": "warning",
            "error": "error",
            "admin": "admin",
            "restart": "restart",
            "info": "info",
            "\uE946": "info",
        }
        status_key = name_map.get(icon_char)
        if status_key:
            icon_path = get_asset_path(f"status-{status_key}.png")
            if icon_path.exists():
                pix = QPixmap(str(icon_path))
                dpr = getattr(self, "devicePixelRatioF", lambda: 1.0)()
                sz = int(24 * dpr)
                scaled = pix.scaled(sz, sz, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                scaled.setDevicePixelRatio(dpr)
                self.icon_lbl.setText("")
                self.icon_lbl.setPixmap(scaled)
                self.icon_lbl.setFixedSize(24, 24)
                return
        self.icon_lbl.setPixmap(QPixmap())
        self.icon_lbl.setText(icon_char)
        self.icon_lbl.set_ink(QColor(color))

    def set_severity(self, severity: str, is_dark: bool = True):
        themes = {
            "success": {
                "bg": "rgba(16, 124, 65, 0.12)" if is_dark else "rgba(16, 124, 65, 0.08)",
                "border": "rgba(16, 124, 65, 0.35)" if is_dark else "rgba(16, 124, 65, 0.25)",
                "icon": "#107C41",
            },
            "warning": {
                "bg": "rgba(255, 185, 0, 0.12)" if is_dark else "rgba(255, 185, 0, 0.10)",
                "border": "rgba(255, 185, 0, 0.35)" if is_dark else "rgba(255, 185, 0, 0.25)",
                "icon": "#FFB900",
            },
            "info": {
                "bg": "rgba(0, 120, 212, 0.12)" if is_dark else "rgba(0, 120, 212, 0.08)",
                "border": "rgba(0, 120, 212, 0.35)" if is_dark else "rgba(0, 120, 212, 0.25)",
                "icon": "#0078D4",
            },
            "error": {
                "bg": "rgba(209, 52, 56, 0.12)" if is_dark else "rgba(209, 52, 56, 0.08)",
                "border": "rgba(209, 52, 56, 0.35)" if is_dark else "rgba(209, 52, 56, 0.25)",
                "icon": "#D13438",
            },
        }
        theme = themes.get(severity, themes["info"])
        self.setStyleSheet(f"""
            #Banner {{
                background-color: {theme["bg"]};
                border: 1px solid {theme["border"]};
                border-radius: 4px;
            }}
        """)

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
        
        metadata = None
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

        action_btn = QPushButton()
        action_btn.setObjectName("CardChangeBtn")
        action_btn.setProperty("isCustom", "true" if is_manual else "false")
        action_btn.setCursor(Qt.PointingHandCursor)
        action_btn.setFocusPolicy(Qt.NoFocus)

        icon_file = "action-reset.png" if is_manual else "action-edit-file.png"
        icon_p = get_asset_path(icon_file)
        if icon_p.exists():
            action_btn.setIcon(QIcon(str(icon_p)))
            action_btn.setIconSize(QSize(22, 22))
        if is_manual:
            action_btn.setToolTip("Reset to auto-detected font")
            if on_reset:
                action_btn.clicked.connect(lambda: on_reset(self.weight))
        else:
            action_btn.setToolTip("Choose a font file and override the auto-detected font")
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
        if weight == "variable" and is_var_file:
            left_text = "Variable Font"
        else:
            left_text = f"Weight {detected_weight}"

        meta_row = QWidget()
        meta_row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        meta_layout = QHBoxLayout(meta_row)
        meta_layout.setContentsMargins(0, 0, 0, 0)
        meta_layout.setSpacing(8)

        meta_left = QLabel(left_text)
        meta_left.setObjectName("VariantMeta")
        meta_left.setStyleSheet(f"color: {colors['text_muted']}; font-size: 11px;")
        meta_layout.addWidget(meta_left, 0, Qt.AlignVCenter | Qt.AlignLeft)

        meta_layout.addStretch(1)

        meta_right = QLabel(filename_str)
        meta_right.setObjectName("VariantMeta")
        meta_right.setStyleSheet(f"color: {colors['text_muted']}; font-size: 11px;")
        meta_right.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        meta_right.setToolTip(filename_str)
        meta_layout.addWidget(meta_right, 0, Qt.AlignVCenter | Qt.AlignRight)

        layout.addWidget(meta_row)

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

        name_container = QWidget(self)
        name_container.setAttribute(Qt.WA_TransparentForMouseEvents)
        name_container.setFixedWidth(246)
        name_lay = QHBoxLayout(name_container)
        name_lay.setContentsMargins(0, 0, 0, 0)
        name_lay.setSpacing(8)

        self.icon_label = QLabel(name_container)
        self.icon_label.setObjectName("CloudFolderIcon")
        self.icon_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.icon_label.setFixedSize(18, 18)
        font_icon_p = get_asset_path("action-font.png")
        if font_icon_p.exists():
            pm = QPixmap(str(font_icon_p)).scaled(18, 18, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.icon_label.setPixmap(pm)
        name_lay.addWidget(self.icon_label)

        self.name_label = QLabel(folder.name, name_container)
        self.name_label.setObjectName("CloudFolderName")
        self.name_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        name_lay.addWidget(self.name_label, 1)

        lay.addWidget(name_container)

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
            p = self.parent()
            while p is not None:
                if hasattr(p, "is_dark"):
                    is_dark = p.is_dark
                    break
                p = p.parent()
        if is_dark is None:
            is_dark = is_system_dark_mode()
        colors = get_theme_colors(is_dark, is_windows_11())
        text_color = colors["text_primary"] if self.isEnabled() else colors["text_muted"]
        self.name_label.setStyleSheet(
            f"color: {text_color}; font-size: 13px; font-weight: 600; font-family: 'Segoe UI', sans-serif; background: transparent;"
        )
        fam = f"font-family: '{self._family_name}', sans-serif;" if self._family_name else "font-family: 'Segoe UI', sans-serif;"
        self.preview_label.setStyleSheet(
            f"color: {text_color}; {fam} font-size: 34px; background: transparent;"
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

        # Info icon in front of the title; stretches keep the pair centred.
        self._title_icon = QLabel()
        self._title_icon.setObjectName("GuideTitleIcon")
        _about = Path(get_asset_path("test-about.png"))
        if _about.exists():
            # Scale in device pixels, then declare the ratio.
            _pm = QPixmap(str(_about))
            _dpr = getattr(self, "devicePixelRatioF", lambda: 1.0)()
            _sz = int(18 * _dpr)
            _scaled = _pm.scaled(_sz, _sz, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            _scaled.setDevicePixelRatio(_dpr)
            self._title_icon.setPixmap(_scaled)
            self._title_icon.setFixedSize(18, 18)
            self._title_icon.setAlignment(Qt.AlignCenter)
        else:
            self._title_icon.hide()

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(7)
        title_row.addStretch(1)
        title_row.addWidget(self._title_icon, 0, Qt.AlignVCenter)
        title_row.addWidget(self._title_lbl, 0, Qt.AlignVCenter)
        title_row.addStretch(1)
        inner_lay.addLayout(title_row)

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

    def fade_in(self, duration=150):
        """Softly fade in the guide text to prevent abrupt snap/glitch when cloud panel closes."""
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(duration)
        anim.setEasingCurve(QEasingCurve.OutQuad)

        def _on_done():
            try:
                self.setGraphicsEffect(None)
            except Exception:
                pass

        anim.finished.connect(_on_done)
        self._fade_anim = anim
        self.show()
        anim.start()


class IconActionButton(QFrame):
    """Standalone action button with an MDL2 glyph icon and a text label.

    Styling matches the old split-button halves exactly: per-icon glyph
    size at regular weight with accent ink, plus a bold Segoe UI caption.
    Unlike the old split control, the whole button is clickable.
    """

    clicked = Signal()

    _LEFT_PAD = 10
    _ICON_GAP = 8
    _RIGHT_PAD = 14

    def __init__(self, icon_char, icon_px, icon_object_name, text, parent=None, icon_asset=None):
        super().__init__(parent)
        self.setObjectName("ActionButton")
        # 34px height for modern balanced WinUI 3 button feel
        self.setFixedHeight(34)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setCursor(Qt.ArrowCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self.setMouseTracking(True)
        self.setAccessibleName(text)
        self._enabled = True
        self._hover = False
        self._pressed = False
        self.setProperty("pressed", False)
        self._icon_px = icon_px
        self._icon_asset = icon_asset
        self._icon_label = QLabel(self)
        self._icon_label.setObjectName(icon_object_name)
        self._icon_label.setAlignment(Qt.AlignCenter)
        self._icon_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        if icon_asset:
            self._update_icon_pixmap()
        elif icon_char:
            self._icon_label.setText(icon_char)
        self._text_label = QLabel(text, self)
        self._text_label.setObjectName("ActionText")
        self._text_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self._text_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._icon_label.raise_()
        self._text_label.raise_()
        self._sync_width()
        self.refresh_action_style()

    def _update_icon_pixmap(self):
        if not self._icon_asset:
            return
        p = get_asset_path(self._icon_asset)
        if p.exists():
            dpr = self.devicePixelRatioF() if hasattr(self, "devicePixelRatioF") else 1.0
            target = int(self._icon_px * dpr)
            pm = QPixmap(str(p)).scaled(target, target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pm.setDevicePixelRatio(dpr)
            self._icon_label.setPixmap(pm)

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
        offset_y = 2 if self._pressed else 1
        try:
            self._icon_label.setGeometry(self._LEFT_PAD, offset_y, icon_w, max(1, height - 2))
            tx = self._LEFT_PAD + icon_w + self._ICON_GAP
            self._text_label.setGeometry(
                tx, offset_y, max(1, width - tx - self._RIGHT_PAD + 4), max(1, height - 2))
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
            if not self._icon_asset:
                self._icon_label.setStyleSheet(f"color: {icon_ink};")
            else:
                self._icon_label.setGraphicsEffect(None)
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
                self._layout_content()
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

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Space, Qt.Key_Return) and self._enabled:
            self._pressed = True
            self._paint_pressed(True)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() in (Qt.Key_Space, Qt.Key_Return) and self._enabled:
            if self._pressed:
                self._pressed = False
                self._paint_pressed(False)
                self.clicked.emit()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.hasFocus() and self._enabled:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            window = self.window()
            is_dark = getattr(window, "is_dark", True)
            accent, _, _, _ = get_windows_accent_color(is_dark)
            pen = QPen(QColor(accent), 2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            r = QRectF(1.0, 1.0, self.width() - 2.0, self.height() - 2.0)
            path = QPainterPath()
            path.addRoundedRect(r, 6.0, 6.0)
            painter.drawPath(path)


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
        refresh_btn = QPushButton()
        refresh_btn.setObjectName("IconBtnRefresh")
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.setToolTip("Refresh cloud fonts")
        refresh_btn.setAccessibleName("Refresh cloud fonts")
        refresh_p = get_asset_path("action-refresh.png")
        if refresh_p.exists():
            refresh_btn.setIcon(QIcon(str(refresh_p)))
            refresh_btn.setIconSize(QSize(18, 18))
        refresh_btn.clicked.connect(lambda: self.start_fetch(force=True))
        header.addWidget(refresh_btn)
        close_btn = QPushButton()
        close_btn.setObjectName("IconBtn")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setToolTip("Close")
        close_btn.setAccessibleName("Close cloud panel")
        close_p = get_asset_path("action-close.png")
        if close_p.exists():
            close_btn.setIcon(QIcon(str(close_p)))
            close_btn.setIconSize(QSize(18, 18))
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
            row.refresh_theme()
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
        try:
            self.clearMask()
        except RuntimeError:
            pass
        try:
            self.setGraphicsEffect(None)
        except RuntimeError:
            pass

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
        self.setMinimumHeight(0)
        self.setMaximumHeight(0)
        self.show()
        self.raise_()
        anim = QPropertyAnimation(self, b"maximumHeight", self)
        anim.setStartValue(0)
        anim.setEndValue(target)
        anim.setDuration(200)
        anim.setEasingCurve(QEasingCurve.OutCubic)

        def _on_show_step(v):
            h = int(v)
            if h < 90:
                self.setMask(QRegion(0, 0, max(1, self.width()), max(0, h)))
            else:
                self.clearMask()

        anim.valueChanged.connect(_on_show_step)

        def _on_show_done():
            self._height_anim = None
            self.clearMask()
            self.setMaximumHeight(16777215)
            self.setMinimumHeight(0)
            self.sync_height()

        anim.finished.connect(_on_show_done)
        self._height_anim = anim
        anim.start()
        return True

    def animate_hide(self):
        """Collapse the panel smoothly with a slide-up animation matching animate_show."""
        if self._dl_thread and self._dl_thread.isRunning():
            return False
        if not self.isVisible():
            return True
        self._kill_anim()
        self._is_hiding = True
        self.setEnabled(False)
        start = max(1, self.height())
        self.setMinimumHeight(0)
        self.setMaximumHeight(start)

        anim = QPropertyAnimation(self, b"maximumHeight", self)
        anim.setStartValue(start)
        anim.setEndValue(0)
        anim.setDuration(200)
        anim.setEasingCurve(QEasingCurve.OutCubic)

        def _on_hide_step(v):
            h = int(v)
            if h < 90:
                self.setMask(QRegion(0, 0, max(1, self.width()), max(0, h)))
            else:
                self.clearMask()

        anim.valueChanged.connect(_on_hide_step)
        anim.finished.connect(self._on_hide_anim_done)
        self._height_anim = anim
        anim.start()
        return True

    def _on_hide_anim_done(self):
        self._is_hiding = False
        self._height_anim = None
        self.hide()
        self.clearMask()
        self.setMaximumHeight(16777215)
        self.setMinimumHeight(0)
        self.setEnabled(True)
        self._set_status("")
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


_STAR_ASSET = "test-star.png"
_STAR_CANVAS = 128
_STAR_GIF_DELAYS = (40, 40, 50, 40, 40, 40, 40, 40, 50, 40, 40, 40,
                       40, 40, 50, 40, 40, 40, 40, 40, 50, 40, 40, 80, 90, 40)
_STAR_GIF_TOTAL_MS = 1170
_STAR_BREATH_GAP_MS = 1300
_STAR_GIF_CACHE = None


def _star_frames():
    """Load the GIF frames once."""
    global _STAR_GIF_CACHE
    if _STAR_GIF_CACHE is None:
        frames = []
        for i in range(len(_STAR_GIF_DELAYS)):
            p = get_asset_path(f"star-breath/frame_{i:02d}.png")
            if not p.exists():
                break
            frames.append(QPixmap(str(p)))
        _STAR_GIF_CACHE = frames or None
    return _STAR_GIF_CACHE
_STAR_PIX = None
_STAR_LOADED = False


def _star_pixmap():
    """Load the star asset, or None to use the procedural fallback."""
    global _STAR_PIX, _STAR_LOADED
    if not _STAR_LOADED:
        _STAR_LOADED = True
        _STAR_PIX = None
        try:
            p = Path(get_asset_path(_STAR_ASSET))
            if p.exists():
                _STAR_PIX = QPixmap(str(p))
        except Exception:
            _STAR_PIX = None
    return _STAR_PIX


def _render_star3d(angle_deg, px=96, palette=None):
    _flat = _star_pixmap()
    if _flat is not None and not _flat.isNull():
        # Fixed canvas: rotating inside a tight one would change the size.
        src = _flat.toImage().convertToFormat(QImage.Format_ARGB32_Premultiplied)
        canvas = QImage(_STAR_CANVAS, _STAR_CANVAS,
                        QImage.Format_ARGB32_Premultiplied)
        canvas.fill(Qt.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.translate(canvas.width() / 2.0, canvas.height() / 2.0)
        if angle_deg:
            painter.rotate(float(angle_deg))
        painter.drawImage(-src.width() / 2.0, -src.height() / 2.0, src)
        painter.end()
        return QPixmap.fromImage(canvas)
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
            try:
                from settings import APP_USER_MODEL_ID
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
            except Exception:
                pass

        self.setMinimumSize(1250, 600)
        self.resize(1270, 650)
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
        self._star_breath_timer = None
        self._star_breath_t0 = time.monotonic()
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

        self._tooltip_filter = WinUI3ToolTipFilter(self)
        app_inst = QApplication.instance()
        if app_inst:
            app_inst.installEventFilter(self._tooltip_filter)

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

    def _make_button_icon(self, name, icon_size=20, pad_left=0, pad_right=0):
        """Scale an icon and pad it to match IconActionButton's inset."""
        p = get_asset_path(name)
        if not p.exists():
            return QIcon(), QSize(icon_size, icon_size)
        dpr = self.devicePixelRatioF() if hasattr(self, "devicePixelRatioF") else 1.0
        logical_w = icon_size + pad_left + pad_right
        total_w_px = max(1, round(logical_w * dpr))
        total_h_px = max(1, round(icon_size * dpr))
        # Whole-pixel offsets keep the glyph sharp on scaled displays.
        left_px = max(0, min(round(pad_left * dpr),
                             total_w_px - round(icon_size * dpr)))

        pm_src = QPixmap(str(p)).scaled(max(1, round(icon_size * dpr)),
                                        max(1, round(icon_size * dpr)),
                                        Qt.KeepAspectRatio, Qt.SmoothTransformation)
        padded_pm = QPixmap(total_w_px, total_h_px)
        padded_pm.fill(Qt.transparent)
        painter = QPainter(padded_pm)
        painter.drawPixmap(left_px, 0, pm_src)
        painter.end()
        padded_pm.setDevicePixelRatio(dpr)
        return QIcon(padded_pm), QSize(logical_w, icon_size)

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

        # Regional font support is always-on; UI toggle is omitted for a clean interface
        self.cjk_container = None
        self.cjk_toggle = None
        self.cjk_label = None
        self.cjk_info_btn = None
        self.cjk_checkbox = None

        self.actions_widget = QWidget()
        self.actions_layout = QHBoxLayout(self.actions_widget)
        self.actions_layout.setContentsMargins(0, 0, 0, 0)
        self.actions_layout.setSpacing(10)

        self.local_btn = IconActionButton("", 20, "ActionIconLocal", "Local Fonts", icon_asset="action-add-file.png")
        self.fetch_btn = IconActionButton("", 20, "ActionIconFetch", "Fetch Fonts", icon_asset="action-cloud.png")
        self.apply_btn = QPushButton("Apply Changes")
        self.restore_btn = QPushButton("Restore Defaults")

        tick_ico, tick_sz = self._make_button_icon("action-tick.png", 20, 2, 10)
        self.apply_btn.setIcon(tick_ico)
        self.apply_btn.setIconSize(tick_sz)

        restore_ico, restore_sz = self._make_button_icon("action-restore.png", 20, 2, 10)
        self.restore_btn.setIcon(restore_ico)
        self.restore_btn.setIconSize(restore_sz)

        self.local_btn.setToolTip("From this PC")
        self.fetch_btn.setToolTip("From cloud")
        for button in (self.apply_btn, self.restore_btn):
            button.setFixedSize(180, 34)
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
        if hasattr(self, "cjk_toggle") and self.cjk_toggle:
            self.cjk_toggle.is_dark = self.is_dark
            self.cjk_toggle.update()

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

    _STAR_REST_PX = 32                  # matches the 32x32 header button
    _STAR_SHOW_MS = 10000                 # 10s total; ~4 breath cycles at 2.47s each
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
        self._stop_star_breath()
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
            _frames = _star_frames()
            button.setIcon(QIcon(_frames[0] if _frames else
                                 _render_star3d(0.0, palette=self._star_palette())))
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
            # Start breathing once the fade/pop finishes.
            QTimer.singleShot(self._STAR_SPIN_DELAY_MS, self._start_star_breath)

        fade_out.finished.connect(_swap_to_star)
        fade_out.start(QAbstractAnimation.DeleteWhenStopped)

    def _start_star_breath(self):
        """GIF-style breathing until the GitHub logo returns."""
        if not getattr(self, "_star_active", False):
            return
        self._stop_star_breath()
        self._star_breath_t0 = time.monotonic()
        timer = QTimer(self)
        timer.setInterval(16)            # ~60fps, smoother than the GIF's 40ms
        timer.timeout.connect(self._star_breath_frame)
        self._star_breath_timer = timer
        timer.start()
        # The restore timer stops the breathing when the star is replaced.

    def _stop_star_breath(self):
        timer = getattr(self, "_star_breath_timer", None)
        if timer is not None:
            try:
                timer.stop()
            except RuntimeError:
                pass
            try:
                timer.deleteLater()
            except RuntimeError:
                pass
            self._star_breath_timer = None
        # Settle back to the resting star, unless GitHub is coming back.
        if getattr(self, "_star_active", False):
            try:
                _frames = _star_frames()
                self.github_btn.setIcon(
                    QIcon(_frames[0] if _frames else
                          _render_star3d(0.0, palette=self._star_palette())))
            except Exception:
                pass

    def _star_breath_frame(self):
        if not getattr(self, "_star_active", False):
            self._stop_star_breath()
            return
        frames = _star_frames()
        if not frames:
            return
        # Play the GIF frames, then hold the rest frame before repeating.
        elapsed_ms = (time.monotonic() - self._star_breath_t0) * 1000.0
        cycle_ms = _STAR_GIF_TOTAL_MS + _STAR_BREATH_GAP_MS
        phase = elapsed_ms % cycle_ms
        if phase >= _STAR_GIF_TOTAL_MS:
            idx = 0                          # rest (smallest) frame, held still
        else:
            acc = 0.0
            idx = 0
            for i, dur in enumerate(_STAR_GIF_DELAYS):
                if phase < acc + dur:
                    idx = i
                    break
                acc += dur
        try:
            self.github_btn.setIcon(QIcon(frames[idx]))
        except Exception:
            pass

    def _restore_github_logo(self):
        if not getattr(self, "_star_active", False):
            return
        self._star_active = False
        self._stop_star_breath()
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
            if etype == QEvent.Type.Resize:
                self._layout_arm_halves()
            elif etype in (QEvent.Type.Enter, QEvent.Type.MouseMove):
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
                cover.setGeometry(0, 0, cover_btn.width(), cover_btn.height())
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
        self._armed_orig_text = button.text()
        self._armed_orig_icon = button.icon() if hasattr(button, "icon") else None
        try:
            button.setText("")
            if hasattr(button, "setIcon"):
                button.setIcon(QIcon())
        except RuntimeError:
            pass
        self._armed_action = {
            "apply": self.on_apply,
            "restore": self._start_restore_op,
            "restart": self._do_restart,
        }[kind]
        colors = get_theme_colors(self.is_dark)
        face = ("bg_button", "bg_button_hover", "text_primary")
        self._armed_face = {
            "bg": colors[face[0]],
            "hover": colors[face[1]],
            "ink": colors[face[2]],
        }
        yes_label = QLabel(button)
        no_label = QLabel(button)
        self._arm_labels = (yes_label, no_label)
        for label in self._arm_labels:
            label.setAttribute(Qt.WA_TransparentForMouseEvents)
            label.setAttribute(Qt.WA_StyledBackground, True)
            label.setAlignment(Qt.AlignCenter)
        dpr = self.devicePixelRatioF() if hasattr(self, "devicePixelRatioF") else 1.0
        target = int(20 * dpr)
        tick_p = get_asset_path("action-tick.png")
        if tick_p.exists():
            pm_tick = QPixmap(str(tick_p)).scaled(target, target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pm_tick.setDevicePixelRatio(dpr)
            yes_label.setPixmap(pm_tick)
        cross_p = get_asset_path("action-cross.png")
        if cross_p.exists():
            pm_cross = QPixmap(str(cross_p)).scaled(target, target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pm_cross.setDevicePixelRatio(dpr)
            no_label.setPixmap(pm_cross)
        self._armed_hover_half = None
        border_top = colors.get("border_card_top", colors["border_card"])
        border_mid = colors["border_card"]
        border_bottom = colors.get("border_card_bottom", colors["border_card"])
        try:
            button.setMouseTracking(True)
            button.setStyleSheet(f"background-color: {self._armed_face['bg']}; border: none;")
            button.setStyleSheet(
                f"background-color: {self._armed_face['bg']}; "
                f"color: transparent; "
                f"border-top: 1px solid {border_top}; "
                f"border-left: 1px solid {border_mid}; "
                f"border-right: 1px solid {border_mid}; "
                f"border-bottom: 1px solid {border_bottom}; "
                f"border-radius: 4px;"
            )
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
            labels[0].setGeometry(0, 0, mid + 1, height)
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
        colors = get_theme_colors(self.is_dark)
        for index, label in enumerate(labels):
            background = face["hover"] if index == half else "transparent"
            try:
                divider = f"border-right: 1px solid {colors['border_card']};" if index == 0 else "border: none;"
                radius_css = (
                    "border-top-left-radius: 5px; border-bottom-left-radius: 5px; border-top-right-radius: 0px; border-bottom-right-radius: 0px;"
                    if index == 0
                    else "border-top-right-radius: 5px; border-bottom-right-radius: 5px; border-top-left-radius: 0px; border-bottom-left-radius: 0px;"
                )
                label.setStyleSheet(
                    f"background-color: {background}; {divider} {radius_css}"
                )
            except RuntimeError:
                pass
        if half == 1 and len(labels) > 1:
            labels[1].raise_()
        elif len(labels) > 0:
            labels[0].raise_()

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
        orig_text = getattr(self, "_armed_orig_text", None)
        self._armed_orig_text = None
        orig_icon = getattr(self, "_armed_orig_icon", None)
        self._armed_orig_icon = None
        for label in (getattr(self, "_arm_labels", None) or ()):
            try:
                label.hide()
                label.deleteLater()
            except RuntimeError:
                pass
        self._arm_labels = None
        if button is not None:
            if orig_text is not None:
                try:
                    button.setText(orig_text)
                except RuntimeError:
                    pass
            if orig_icon is not None:
                try:
                    button.setIcon(orig_icon)
                except RuntimeError:
                    pass
            try:
                button.setStyleSheet("")
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

    def _on_cjk_toggled(self, checked: bool):
        self.controller.set_include_regional(checked)
        from checks import check_disk_space_only
        state_data = getattr(self.controller, "state", None) or {}
        installed = state_data.get("install", {}).get("fonts", {}) if isinstance(state_data, dict) else {}
        has_reg = any(k.startswith("regional_") for k in installed)
        ok, msg = check_disk_space_only(include_regional=checked, has_regional_installed=has_reg)
        if not ok:
            req_str = "1.2 GB" if checked else ("400 MB" if has_reg else "180 MB")
            target_drive = Path(FONTS_DIR).anchor.rstrip("\\") if hasattr(FONTS_DIR, "anchor") else "C:"
            self.banner.set_icon("\uEA39", "#FFB900")
            self.banner.set_severity("warning", self.is_dark)
            self.banner.set_content(f"Free up at least {req_str} on {target_drive} to continue", msg or "")
            self.apply_btn.setEnabled(False)
            # Restore only requires 400 MB and has its own preflight check; do not disable restore unless space < 400 MB
            can_restore, _ = check_disk_space_only(include_regional=False, is_restore=True, has_regional_installed=has_reg)
            self.restore_btn.setEnabled(can_restore)
        else:
            self.refresh_all()

    def _show_cjk_info_dialog(self):
        WinUI3ContentDialog.show_cjk_info(self)

    def _select_regular(self, font_path):
        try:
            self.controller.set_regular_font(font_path)
        except Exception as exc:
            WinUI3ContentDialog.show_warning(self, "Font not supported", str(exc))
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
        if hasattr(self, "cjk_checkbox") and self.cjk_checkbox:
            self.cjk_checkbox.setEnabled(False)
        colors = get_theme_colors(self.is_dark)
        cover = ButtonProgressCover(text, btn, colors["bg_button"], is_dark=self.is_dark)
        cover.show()
        cover.raise_()
        self._op_cover = cover
        self._op_cover_btn = btn
        self._op_thread = OperationThread(func, self)
        # The label stays on the static phase name ("Applying…"/"Restoring…");
        # step-by-step progress chatter is deliberately not shown on the button.
        self._op_thread.done.connect(lambda r: self._on_operation_done(r, btn))
        self._op_thread.finished.connect(self._op_thread.deleteLater)
        self._op_thread.start()

    def _on_operation_done(self, result, btn):
        cover = getattr(self, "_op_cover", None)
        self._op_cover = None
        self._op_cover_btn = None
        if cover is not None:
            try:
                cover.restore()     # button's own text/icon back first
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
            title = "Low Disk Space" if "disk space" in result.message.lower() else "Operation Failed"
            WinUI3ContentDialog.show_warning(self, title, result.message)
        elif result.warnings:
            notices = [w for w in result.warnings if not w.startswith("Note:")]
            if notices:
                if len(notices) <= 6:
                    notice_lines = "\n".join(f"• {w}" for w in notices)
                else:
                    notice_lines = "\n".join(f"• {w}" for w in notices[:5]) + f"\n• ...and {len(notices) - 5} more notices"
                WinUI3ContentDialog.show_warning(
                    self,
                    "Completed with Notices",
                    result.message + "\n\nNotices:\n" + notice_lines
                )
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
        btn = self.apply_btn if getattr(self, "_apply_action", "apply") == "restart" else self.restore_btn
        colors = get_theme_colors(self.is_dark)
        cover = ButtonProgressCover("Restarting...", btn, colors["bg_button"], is_dark=self.is_dark)
        cover.show()
        cover.raise_()
        # Same contract as _run_operation: while the cover is up, refresh_all()
        # must not put the button's content back underneath it.
        self._op_cover = cover
        self._op_cover_btn = btn
        btn.setEnabled(False)
        QApplication.processEvents()
        try:
            subprocess.run(["shutdown", "/r", "/t", "0"], check=True)
        except Exception:
            self._op_cover = None
            self._op_cover_btn = None
            try:
                cover.restore()
                cover.hide()
                cover.deleteLater()
            except RuntimeError:
                pass
            btn.setEnabled(True)
            WinUI3ContentDialog.show_warning(
                self,
                "Restart Required",
                "Font Wizard couldn't restart Windows automatically.\n\nPlease restart your computer manually to finish the setup."
            )

    def refresh_all(self):
        self._disarm()
        report = self.controller.refresh_preflight()
        colors = get_theme_colors(self.is_dark)

        is_pending = report.install_state in ("pending_reboot_apply", "pending_reboot_recovery")
        if not report.is_supported:
            self.banner.set_icon("\uEA39", "#D13438")
            self.banner.set_severity("error", self.is_dark)
        elif not report.is_admin:
            self.banner.set_icon("\uE83D", "#0078D4")
            self.banner.set_severity("info", self.is_dark)
        elif is_pending:
            self.banner.set_icon("\uE895", "#0078D4")
            self.banner.set_severity("info", self.is_dark)
        elif report.issues or report.install_state == "partial":
            self.banner.set_icon("\uEA39", "#FFB900")
            self.banner.set_severity("warning", self.is_dark)
        elif report.install_state == "managed":
            self.banner.set_icon("\uE930", "#107C41")
            self.banner.set_severity("success", self.is_dark)
        else:
            self.banner.set_icon("\uE930", "#107C41")
            self.banner.set_severity("success", self.is_dark)

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
            restore_text = "Restore Defaults"
            apply_visible = True
            restore_visible = False
            restore_available = False
        else:
            self._browse_action = "select"
            self._apply_action = "apply"
            self._restore_action = "restore"
            apply_text = "Apply Changes"
            apply_available = can_apply
            restore_text = "Restore Defaults"
            apply_visible = has_selected_font
            restore_visible = (not apply_visible) and (report.install_state in ("managed", "partial"))
            apply_available = apply_visible and can_apply
            restore_available = restore_visible and report.can_restore_defaults

        self.local_btn.setEnabled(not is_recovery_pending)
        self.local_btn.setVisible(not is_recovery_pending)
        self.fetch_btn.setEnabled(not is_recovery_pending)
        self.fetch_btn.setVisible(not is_recovery_pending)

        # While an operation cover is up, the covered button's content is
        # deliberately blanked (the cover is transparent so the button's face
        # shows through unchanged -- its icon/label must stay hidden or they
        # ghost through next to the cover's label). refresh_all() can fire
        # mid-operation (card clicks, theme toggle), so it must not put
        # content back underneath an active cover.
        covered_btn = getattr(self, "_op_cover_btn", None)
        apply_covered = covered_btn is self.apply_btn
        restore_covered = covered_btn is self.restore_btn

        if not apply_covered:
            self.apply_btn.setText(apply_text)
            self.apply_btn.setEnabled(apply_available)
            self.apply_btn.setVisible(apply_visible)

        if not restore_covered:
            self.restore_btn.setEnabled(restore_available)
            self.restore_btn.setVisible(restore_visible)
            self.restore_btn.setText(restore_text)

        restart_p = get_asset_path("action-restart.png")
        restart_name = "action-restart.png" if restart_p.exists() else "status-restart.png"
        restart_icon, restart_size = self._make_button_icon(restart_name, 20, 2, 10)

        if not apply_covered:
            if self._apply_action == "restart":
                self.apply_btn.setIcon(restart_icon)
                self.apply_btn.setIconSize(restart_size)
            else:
                tick_ico, tick_sz = self._make_button_icon("action-tick.png", 20, 2, 10)
                self.apply_btn.setIcon(tick_ico)
                self.apply_btn.setIconSize(tick_sz)

        if not restore_covered:
            if self._restore_action == "restart":
                self.restore_btn.setIcon(restart_icon)
                self.restore_btn.setIconSize(restart_size)
            else:
                restore_ico, restore_sz = self._make_button_icon("action-restore.png", 20, 2, 10)
                self.restore_btn.setIcon(restore_ico)
                self.restore_btn.setIconSize(restore_sz)

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
            if not report.is_admin:
                self.restore_btn.setToolTip("Run Font Wizard as Administrator to restore default fonts.")
            elif any("disk space" in issue.lower() for issue in report.issues):
                self.restore_btn.setToolTip("Free up disk space on C: to restore default fonts.")
            else:
                self.restore_btn.setToolTip("Default Windows fonts are already active.")
        else:
            self.restore_btn.setToolTip("")

        if hasattr(self, "cjk_checkbox") and self.cjk_checkbox:
            self.cjk_checkbox.setEnabled(not is_recovery_pending and not (self._op_thread and self._op_thread.isRunning()))

        # Apply/Restore/Restart stay neutral (secondary) — Local/Fetch Fonts
        # are the reference look, so nothing in this row is accent-filled.
        fetch_role = "secondary"
        apply_role = "secondary"
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
                filter_str = "Variable TrueType fonts (*.ttf)"
            else:
                display_name = w.replace("consolas_", "Consolas ").replace("_", " ").title()
                filter_str = "Static TrueType fonts (*.ttf)"
            chosen_file, _ = QFileDialog.getOpenFileName(
                self,
                f"Select Font File for {display_name}",
                start_dir,
                filter_str,
            )
            if chosen_file:
                try:
                    self.controller.set_card_override(w, chosen_file)
                    self._selection_dirty = True
                    self.refresh_all()
                except Exception as exc:
                    WinUI3ContentDialog.show_warning(self, "Invalid Font", str(exc))

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
            show_guide = not has_selected_font and not getattr(self, "_cloud_open", False)
            if not show_guide:
                self.local_fonts_guide.hide()
            else:
                if not self.local_fonts_guide.isVisible():
                    self.local_fonts_guide.fade_in(150)
                else:
                    self.local_fonts_guide.show()
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
        try:
            if hasattr(self, "_tooltip_filter"):
                app_inst = QApplication.instance()
                if app_inst:
                    app_inst.removeEventFilter(self._tooltip_filter)
            WinUI3ToolTip.instance().hide_tip()
        except Exception:
            pass
        event.accept()

    def run(self):
        self.show()
        # Re-assert the default size once native: creating the native
        # window during __init__ (mica/winId) eats ~20px of height.
        self.resize(1270, 650)
        return QApplication.instance().exec()

if __name__ == "__main__":
    from main import main
    sys.exit(main())
