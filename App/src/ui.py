import ctypes
import subprocess
import sys
import winreg
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QSize, QPoint, QRect, QUrl
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

def get_theme_colors(is_dark: bool) -> dict[str, str]:
    if is_dark:
        return {
            "bg_card": "rgba(255, 255, 255, 0.04)",
            "bg_card_hover": "rgba(255, 255, 255, 0.07)",
            "bg_button": "rgba(255, 255, 255, 0.06)",
            "bg_button_hover": "rgba(255, 255, 255, 0.09)",
            "bg_button_pressed": "rgba(255, 255, 255, 0.03)",
            "border_card": "rgba(255, 255, 255, 0.08)",
            "border_button": "rgba(255, 255, 255, 0.08)",
            "text_primary": "#FFFFFF",
            "text_secondary": "rgba(255, 255, 255, 0.78)",
            "text_muted": "rgba(255, 255, 255, 0.55)",
            "accent": "#60CDFF",
            "accent_hover": "#7AD7FF",
            "accent_text": "#000000",
            "success": "#6CCB5F",
            "warning": "#C4B5FD",
            "danger": "#FF99A4",
            "bg_dialog": "#202020",
        }
    return {
        "bg_card": "rgba(255, 255, 255, 0.7)",
        "bg_card_hover": "rgba(255, 255, 255, 0.85)",
        "bg_button": "rgba(255, 255, 255, 0.7)",
        "bg_button_hover": "rgba(255, 255, 255, 0.85)",
        "bg_button_pressed": "rgba(255, 255, 255, 0.5)",
        "border_card": "rgba(0, 0, 0, 0.06)",
        "border_button": "rgba(0, 0, 0, 0.06)",
        "text_primary": "rgba(0, 0, 0, 0.9)",
        "text_secondary": "rgba(0, 0, 0, 0.6)",
        "text_muted": "rgba(0, 0, 0, 0.45)",
        "accent": "#005FB8",
        "accent_hover": "#0052A3",
        "accent_text": "#FFFFFF",
        "success": "#0F7B0F",
        "warning": "#6D28D9",
        "danger": "#C42B1C",
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
        dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark_mode), ctypes.sizeof(dark_mode))
        backdrop_type = ctypes.c_int(2) # 2 for Mica
        dwmapi.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(backdrop_type), ctypes.sizeof(backdrop_type))
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
    colors = get_theme_colors(is_dark)
    return f"""
    QMainWindow, QWidget, QFrame, QScrollArea {{ background: transparent; }}
    QWidget {{ 
        color: {colors["text_primary"]}; 
        font-family: 'Segoe UI Variable Text', 'Segoe UI', sans-serif; 
        font-size: 14px; 
    }}
    QDialog, QMessageBox, QToolTip {{ 
        background-color: {colors["bg_dialog"]}; 
        border: 1px solid {colors["border_card"]}; 
        border-radius: 8px;
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
    
    QPushButton {{ 
        background-color: {colors["bg_button"]}; 
        border: 1px solid {colors["border_button"]}; 
        border-radius: 4px; 
        padding: 6px 16px; 
        min-height: 32px; 
        font-weight: 600; 
    }}
    QPushButton:hover {{ background-color: {colors["bg_button_hover"]}; }}
    QPushButton:pressed {{ background-color: {colors["bg_button_pressed"]}; }}
    QPushButton:disabled {{ color: {colors["text_muted"]}; background-color: {colors["bg_card"]}; border-color: {colors["border_card"]}; }}
    
    QPushButton[buttonRole="primary"] {{ 
        background-color: {colors["accent"]}; 
        border: 1px solid {colors["accent"]}; 
        color: {colors["accent_text"]}; 
    }}
    QPushButton[buttonRole="primary"]:hover {{ background-color: {colors["accent_hover"]}; border-color: {colors["accent_hover"]}; }}
    
    QPushButton[buttonRole="warning"] {{ color: {colors["warning"]}; }}
    QPushButton[buttonRole="danger"] {{ color: {colors["danger"]}; }}
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
    def __init__(self, weight, font_path, parent=None):
        super().__init__(parent)
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
        
        title_str = weight.replace("_", " ").title()
        title = QLabel(title_str)
        title.setObjectName("CardTitle")
        title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(title)
        
        self.preview = QLabel("The quick brown fox jumps over the lazy dog")
        self.preview.setObjectName("VariantPreview")
        self.preview.setWordWrap(True)
        self._font_id = QFontDatabase.addApplicationFont(str(font_path))
        if self._font_id >= 0:
            families = QFontDatabase.applicationFontFamilies(self._font_id)
            if families:
                style_str = "italic" if detected_italic else "normal"
                self.preview.setStyleSheet(f"font-family: '{families[0]}'; font-weight: {detected_weight}; font-style: {style_str};")
        layout.addWidget(self.preview)

        meta = QLabel(f"Weight {detected_weight}" + (" italic" if detected_italic else ""))
        meta.setObjectName("VariantMeta")
        meta.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(meta)

    def cleanup(self):
        if hasattr(self, "preview") and self.preview:
            self.preview.setStyleSheet("")
            from PySide6.QtGui import QFont
            self.preview.setFont(QFont())
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
        self.setAttribute(Qt.WA_TranslucentBackground)

        central = QWidget()
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
        self.setup_layout = QHBoxLayout(self.setup_card)
        self.setup_layout.setContentsMargins(24, 20, 24, 20)
        self.setup_layout.setSpacing(24)

        self.font_summary = QWidget()
        summary_layout = QHBoxLayout(self.font_summary)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(14)

        font_text = QVBoxLayout()
        font_text.setContentsMargins(0, 0, 0, 0)
        font_text.setSpacing(6)

        title = QLabel("Interface Font")
        title.setObjectName("CardTitle")
        font_text.addWidget(title)

        self.cur_font_lbl = QLabel("No font selected")
        self.cur_font_lbl.setObjectName("SelectedFont")
        self.cur_font_lbl.setWordWrap(True)
        self.cur_font_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
        font_text.addWidget(self.cur_font_lbl)
        font_text.addStretch(1)

        summary_layout.addLayout(font_text, 1)
        self.setup_layout.addWidget(self.font_summary, 1)

        self.actions_widget = QWidget()
        self.actions_layout = QVBoxLayout(self.actions_widget)
        self.actions_layout.setContentsMargins(0, 0, 0, 0)
        self.actions_layout.setSpacing(10)

        self.browse_btn = QPushButton("Select Font")
        self.apply_btn = QPushButton("Apply Changes")
        self.restore_btn = QPushButton("Restore Original Fonts")

        for button in (self.browse_btn, self.apply_btn, self.restore_btn):
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumHeight(40)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.actions_layout.addWidget(button)

        self.actions_widget.setMinimumWidth(240)
        self.actions_widget.setMaximumWidth(280)
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

    def _sync_theme(self):
        current_dark = is_system_dark_mode()
        if current_dark != self.is_dark:
            self._apply_theme(current_dark)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_responsive_layout()
        self._sync_variant_layout_height()

    def _sync_responsive_layout(self):
        if not hasattr(self, "setup_layout"):
            return

        is_compact = self.width() < 960
        if self._compact_layout == is_compact:
            return

        self._compact_layout = is_compact
        if is_compact:
            self.main_layout.setContentsMargins(28, 28, 28, 28)
            self.main_layout.setSpacing(20)
            self.setup_layout.setDirection(QBoxLayout.TopToBottom)
            self.setup_layout.setSpacing(18)
            self.setup_layout.setContentsMargins(24, 20, 24, 20)
            self.setup_layout.setAlignment(self.actions_widget, Qt.AlignTop)
            self.actions_widget.setMinimumWidth(0)
            self.actions_widget.setMaximumWidth(16777215)
        else:
            self.main_layout.setContentsMargins(40, 36, 40, 36)
            self.main_layout.setSpacing(24)
            self.setup_layout.setDirection(QBoxLayout.LeftToRight)
            self.setup_layout.setSpacing(24)
            self.setup_layout.setContentsMargins(24, 20, 24, 20)
            self.setup_layout.setAlignment(self.actions_widget, Qt.AlignVCenter)
            self.actions_widget.setMinimumWidth(240)
            self.actions_widget.setMaximumWidth(16777215)

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
            self._hide_applied_variants = True

        if result.success:
            QMessageBox.information(self, "Result", result.message)
        else:
            QMessageBox.warning(self, "Result", result.message)
        self.refresh_all()

    def on_apply(self):
        self._run_operation(self.controller.apply, self.apply_btn, "Applying Changes...")

    def on_restore(self):
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
        if report.install_state == "managed":
            self.banner.set_icon("\uE73E", colors["success"])
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
            self._browse_action = "restart"
            self._apply_action = "restart"
            browse_text = "Restart Windows"
            apply_text = "Apply Changes"
            restore_text = "Restore Original Fonts"
            apply_visible = False
            restore_visible = False
        elif is_apply_pending:
            self._browse_action = "select"
            if has_selected_font and self._selection_dirty:
                self._apply_action = "apply"
                apply_text = "Apply Changes"
            else:
                self._apply_action = "restart"
                apply_text = "Restart Windows"
            browse_text = "Select Font"
            restore_text = "Restore Original Fonts"
            apply_visible = True
            restore_visible = False
        else:
            self._browse_action = "select"
            self._apply_action = "apply"
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
        self.browse_btn.setToolTip("")

        self.apply_btn.setText(apply_text)
        self.apply_btn.setEnabled(apply_available)
        self.apply_btn.setVisible(apply_visible)

        self.restore_btn.setEnabled(restore_available)
        self.restore_btn.setVisible(restore_visible)
        self.restore_btn.setText(restore_text)

        if not can_apply and not action_is_restart:
            if not regular_font:
                self.apply_btn.setToolTip("Select a font to apply.")
            else:
                self.apply_btn.setToolTip(
                    "\n".join(report.issues) if report.issues else "Cannot apply changes right now."
                )
        else:
            self.apply_btn.setToolTip("")

        if not self.restore_btn.isEnabled():
            self.restore_btn.setToolTip("Cannot restore fonts right now.")
        else:
            self.restore_btn.setToolTip("")

        browse_role = "warning" if self._browse_action == "restart" else ("secondary" if has_selected_font else "primary")
        self._set_button_role(self.browse_btn, browse_role)
        self._set_button_role(self.apply_btn, "warning" if action_is_restart else "primary")
        self._set_button_role(self.restore_btn, "warning")

        self.cur_font_lbl.setText(Path(regular_font).name if regular_font else "No font selected")

        while self.weight_layout.count():
            item = self.weight_layout.takeAt(0)
            widget = item.widget()
            if widget:
                if hasattr(widget, "cleanup"):
                    widget.cleanup()
                widget.deleteLater()

        cards_added = 0
        for weight, font_path in self.controller.selection.paths.items():
            if font_path and weight != "variable":
                try:
                    card = WeightCard(weight, font_path)
                    self.weight_layout.addWidget(card)
                    card.show()
                    cards_added += 1
                except (ValueError, OSError):
                    pass

        show_variant_section = (
            has_selected_font
            and not is_recovery_pending
            and (not is_apply_pending or self._selection_dirty or not self._hide_applied_variants)
        )
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
