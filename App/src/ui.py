import ctypes
import subprocess
import sys
import winreg
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QSize, QPoint, QRect, QUrl, QTimer, QEvent
from PySide6.QtGui import QDesktopServices, QFontDatabase, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QBoxLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
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

def is_windows_11() -> bool:
    try:
        winver = sys.getwindowsversion()
        return winver.major == 10 and winver.build >= 22000
    except Exception:
        return False

def get_theme_colors(is_dark: bool, is_win11: bool = True) -> dict[str, str]:
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
            "accent": "#38BDF8",
            "accent_hover": "#60CDFF",
            "accent_text": "#000000",
            "success": "#22C55E",
            "success_hover": "#4ADE80",
            "warning": "#F59E0B",
            "warning_hover": "#FBBF24",
            "warning_text": "#000000",
            "danger": "#EF4444",
            "danger_hover": "#F87171",
            "danger_text": "#FFFFFF",
            "bg_dialog": "#202020",
        }
    return {
        "bg_window": "transparent" if is_win11 else "#F3F3F3",
        "bg_card": "rgba(255, 255, 255, 0.7)" if is_win11 else "#FFFFFF",
        "bg_card_hover": "rgba(255, 255, 255, 0.85)" if is_win11 else "#F9F9F9",
        "bg_button": "rgba(255, 255, 255, 0.7)" if is_win11 else "#E5E5E5",
        "bg_button_hover": "rgba(255, 255, 255, 0.85)" if is_win11 else "#DEDEDE",
        "bg_button_pressed": "rgba(255, 255, 255, 0.5)" if is_win11 else "#CCCCCC",
        "border_card": "rgba(0, 0, 0, 0.06)" if is_win11 else "#E0E0E0",
        "border_button": "rgba(0, 0, 0, 0.06)" if is_win11 else "#D0D0D0",
        "text_primary": "rgba(0, 0, 0, 0.9)" if is_win11 else "#1A1A1A",
        "text_secondary": "rgba(0, 0, 0, 0.6)" if is_win11 else "#555555",
        "text_muted": "rgba(0, 0, 0, 0.45)" if is_win11 else "#777777",
        "accent": "#0066CC",
        "accent_hover": "#0052A3",
        "accent_text": "#FFFFFF",
        "success": "#16A34A",
        "success_hover": "#15803D",
        "warning": "#D97706",
        "warning_hover": "#B45309",
        "warning_text": "#FFFFFF",
        "danger": "#DC2626",
        "danger_hover": "#B91C1C",
        "danger_text": "#FFFFFF",
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

def get_wizard_stylesheet(is_dark: bool) -> str:
    is_win11 = is_windows_11()
    colors = get_theme_colors(is_dark, is_win11)
    win_bg = colors["bg_window"]
    font_stack = "'Segoe UI Variable Text', 'Segoe UI', sans-serif" if is_win11 else "'Segoe UI', sans-serif"
    title_font_stack = "'Segoe UI Variable Display', 'Segoe UI', sans-serif" if is_win11 else "'Segoe UI', sans-serif"

    return f"""
    QMainWindow {{ background-color: {win_bg}; }}
    QWidget#CentralWidget {{ background-color: {win_bg}; }}
    QFrame, QScrollArea {{ background: transparent; }}
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
        border: 1px solid {colors["border_button"]};
        border-radius: 4px;
        padding: 0 8px;
        min-height: 24px;
        max-height: 24px;
        font-size: 11px;
        font-weight: 500;
        color: {colors["text_secondary"]};
        outline: none;
    }}
    #CardChangeBtn:hover {{
        background-color: {colors["bg_button_hover"]};
        color: {colors["text_primary"]};
    }}
    #CardChangeBtn:pressed {{
        background-color: {colors["bg_button_pressed"]};
    }}
    #CustomBadge {{
        background-color: {colors["accent"]};
        color: {colors["accent_text"]};
        border-radius: 3px;
        padding: 1px 6px;
        font-size: 10px;
        font-weight: 600;
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
        background-color: {colors["warning"]}; 
        border: 1px solid {colors["warning"]}; 
        color: {colors["warning_text"]}; 
        outline: none;
    }}
    QPushButton[buttonRole="warning"]:hover {{ 
        background-color: {colors["warning_hover"]}; 
        border-color: {colors["warning_hover"]}; 
    }}
    
    QPushButton[buttonRole="danger"] {{ 
        background-color: {colors["bg_card"]}; 
        border: 1px solid {colors["danger"]}; 
        color: {colors["danger"]}; 
    }}
    QPushButton[buttonRole="danger"]:hover {{ 
        background-color: {colors["danger"]}; 
        border-color: {colors["danger"]}; 
        color: {colors["danger_text"]}; 
    }}
    QPushButton[buttonRole="secondary"] {{ 
        background-color: {colors["bg_card"]}; 
        color: {colors["text_primary"]}; 
    }}
    QPushButton[buttonRole="secondary"]:hover {{ background-color: {colors["bg_button_hover"]}; }}
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

        if weight.startswith("consolas_"):
            title_str = "Monospaced " + weight.replace("consolas_", "").replace("_", " ").title()
        else:
            title_str = weight.replace("_", " ").title()

        title = QLabel(title_str)
        title.setObjectName("CardTitle")
        title.setStyleSheet(f"color: {colors['text_primary']}; font-weight: 600; font-size: 14px;")
        header_layout.addWidget(title, 0, Qt.AlignVCenter)

        if is_manual:
            badge = QLabel("Custom")
            badge.setObjectName("CustomBadge")
            header_layout.addWidget(badge, 0, Qt.AlignVCenter)

        header_layout.addStretch(1)

        action_btn = QPushButton("Reset to Auto" if is_manual else "Select File")
        action_btn.setObjectName("CardChangeBtn")
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

        self.setMinimumSize(600, 500)
        self.resize(920, 720)
        self._selection_dirty = False
        self._hide_applied_variants = True
        self._apply_action = "apply"
        self._browse_action = "select"
        self._op_thread = None
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
        self._action_buttons = (self.browse_btn, self.apply_btn, self.restore_btn)

        self.browse_btn.clicked.connect(self.on_browse)
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

        self.browse_btn = QPushButton("Select Font")
        self.apply_btn = QPushButton("Apply Changes")
        self.restore_btn = QPushButton("Restore Original Fonts")

        for button in (self.browse_btn, self.apply_btn, self.restore_btn):
            button.setCursor(Qt.PointingHandCursor)
            button.setFixedHeight(34)
            button.setMinimumWidth(150)
            button.setFocusPolicy(Qt.NoFocus)
            button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            self.actions_layout.addWidget(button)

        self.setup_layout.addWidget(self.actions_widget, 0, Qt.AlignVCenter)
        self.main_layout.addWidget(self.setup_card)

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

    def _apply_widget_theme(self):
        for button in self._action_buttons:
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()

    def _apply_theme(self, is_dark: bool):
        self.is_dark = is_dark
        self.setStyleSheet(get_wizard_stylesheet(is_dark))
        apply_native_mica(int(self.winId()), is_dark)
        self._apply_widget_theme()
        self.refresh_all()

    def _sync_theme(self):
        current_dark = is_system_dark_mode()
        if current_dark != self.is_dark:
            self._apply_theme(current_dark)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.PaletteChange, QEvent.ThemeChange, QEvent.ActivationChange, QEvent.ApplicationPaletteChange):
            self._sync_theme()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_responsive_layout()
        self._sync_variant_layout_height()

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
            return

        viewport_width = self.weight_scroll.viewport().width()
        if viewport_width <= 0:
            viewport_width = self.weight_scroll.width()
        content_height = self.weight_layout.heightForWidth(viewport_width) + 16
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

        if msg.message in {
            WM_SETTINGCHANGE,
            WM_THEMECHANGED,
            WM_DWMCOLORIZATIONCOLORCHANGED,
        }:
            self._sync_theme()

        return super().nativeEvent(event_type, message)

    def _confirm(self, title, message):
        return QMessageBox.question(
            self,
            title,
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) == QMessageBox.Yes

    def on_browse(self):
        if self._browse_action == "restart":
            self.on_restart()
            return
        font_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Static TrueType Font",
            "",
            "Static TrueType fonts (*.ttf)",
        )
        if font_path:
            try:
                self.controller.set_regular_font(font_path)
            except (ValueError, OSError) as exc:
                QMessageBox.warning(self, "Font not supported", str(exc))
                return
            self._selection_dirty = True
            self._hide_applied_variants = False
            self.refresh_all()

    def on_apply_action(self):
        if self._apply_action == "restart":
            self.on_restart()
            return
        if self._confirm(
            "Apply font change?",
            "Apply this font change now? Windows may need a restart before every app uses it.",
        ):
            self.on_apply()

    def _run_operation(self, func, btn, text):
        if self._op_thread and self._op_thread.isRunning():
            return

        for button in self._action_buttons:
            button.setEnabled(False)
        btn.setText(text)
        self._set_button_role(btn, "warning")
        self._op_thread = OperationThread(func, self)
        self._op_thread.progress.connect(lambda v, m: self._update_progress_text(btn, v, m))
        self._op_thread.done.connect(lambda r: self._on_operation_done(r, btn))
        self._op_thread.finished.connect(self._op_thread.deleteLater)
        self._op_thread.start()

    def _update_progress_text(self, btn, value, message):
        btn.setText(f"{value}%")
        btn.setToolTip(message)

    def _on_operation_done(self, result, btn):
        self._op_thread = None

        if not isinstance(result, OperationResult):
            result = OperationResult(
                False,
                "The operation finished with an unexpected result.",
                [repr(result)],
            )

        if btn == self.apply_btn and result.success:
            self._selection_dirty = False

        if result.success:
            QMessageBox.information(self, "Result", result.message)
        else:
            QMessageBox.warning(self, "Result", result.message)
        self.refresh_all()

    def on_apply(self):
        self._run_operation(self.controller.apply, self.apply_btn, "Applying Changes...")

    def on_restore(self):
        if getattr(self, "_restore_action", "restore") == "restart":
            self.on_restart()
            return
        if self._confirm(
            "Restore original fonts?",
            "Restore the original Windows interface fonts?",
        ):
            self._run_operation(self.controller.restore, self.restore_btn, "Restoring Fonts...")

    def on_restart(self):
        if self._confirm(
            "Restart Windows?",
            "Restart Windows now to finish the font change?",
        ):
            try:
                subprocess.run(["shutdown", "/r", "/t", "0"], check=True)
            except Exception as exc:
                QMessageBox.warning(self, "Restart Failed", f"Could not initiate Windows restart: {exc}\n\nPlease restart your computer manually to finish the setup.")

    def refresh_all(self):
        report = self.controller.refresh_preflight()
        colors = get_theme_colors(self.is_dark)

        is_pending = report.install_state in ("pending_reboot_apply", "pending_reboot_recovery")
        if not report.is_supported:
            self.banner.set_icon("\uEA39", colors["danger"])
        elif not report.is_admin:
            self.banner.set_icon("\uE7BA", colors["warning"])
        elif is_pending:
            self.banner.set_icon("\uE777", colors["warning"])
        elif report.install_state == "managed":
            self.banner.set_icon("\uE73E", colors["accent"])
        elif report.issues:
            self.banner.set_icon("\uEA39", colors["danger"])
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
            self._apply_action = "restart"
            self._restore_action = "restart"
            browse_text = "Select Font"
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
            browse_text = "Change Font" if has_selected_font else "Select Font"
            restore_text = "Restore Original Fonts"
            apply_visible = True
            restore_visible = False
            restore_available = False
        else:
            self._browse_action = "select"
            self._apply_action = "apply"
            self._restore_action = "restore"
            browse_text = "Change Font" if has_selected_font else "Select Font"
            apply_text = "Apply Changes"
            restore_text = "Restore Original Fonts"
            apply_visible = has_selected_font
            restore_visible = not has_selected_font and report.install_state == "managed"
            apply_available = apply_visible and can_apply
            restore_available = restore_visible and report.can_restore_defaults

        self.browse_btn.setText(browse_text)
        self.browse_btn.setEnabled(True)
        self.browse_btn.setVisible(True)
        self.browse_btn.setToolTip("")

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

        browse_role = "secondary" if (has_selected_font or is_pending) else "primary"
        apply_role = "warning" if self._apply_action == "restart" else "primary"
        restore_role = "warning" if self._restore_action == "restart" else "danger"

        self._set_button_role(self.browse_btn, browse_role)
        self._set_button_role(self.apply_btn, apply_role)
        self._set_button_role(self.restore_btn, restore_role)

        self.cur_font_lbl.setText(Path(regular_font).name if regular_font else "No font selected")

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
                except ValueError as exc:
                    QMessageBox.warning(self, "Invalid Font", str(exc))

        def _handle_card_reset(w):
            self.controller.reset_card_override(w)
            self._selection_dirty = True
            self.refresh_all()

        cards_added = 0
        for weight, font_path in self.controller.selection.paths.items():
            if font_path and weight != "variable":
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

    def run(self):
        self.show()
        return QApplication.instance().exec()

if __name__ == "__main__":
    from main import main
    sys.exit(main())
