import winreg

from settings import FONT_REGISTRY_SUBKEY, default_registry_targets

FONT_SUBSTITUTES_SUBKEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\FontSubstitutes"


class WindowsFontRegistry:
    def __init__(self, subkey: str = FONT_REGISTRY_SUBKEY):
        self.subkey = subkey

    def _open(self, access: int):
        return winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            self.subkey,
            0,
            access | winreg.KEY_WOW64_64KEY,
        )

    def read_value(self, name: str) -> str | None:
        with self._open(winreg.KEY_READ) as key:
            try:
                value, _ = winreg.QueryValueEx(key, name)
            except FileNotFoundError:
                return None
            return value

    def read_targets(self, names=None):
        keys = names or list(default_registry_targets().keys())
        return {name: self.read_value(name) for name in keys}

    def write_targets(self, targets):
        with self._open(winreg.KEY_SET_VALUE) as key:
            for name, value in targets.items():
                if value is None:
                    try:
                        winreg.DeleteValue(key, name)
                    except FileNotFoundError:
                        pass
                    continue
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)

    def ensure_font_substitutes(self):
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            FONT_SUBSTITUTES_SUBKEY,
            0,
            winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY,
        ) as key:
            winreg.SetValueEx(key, "MS Shell Dlg", 0, winreg.REG_SZ, "Segoe UI")
            winreg.SetValueEx(key, "MS Shell Dlg 2", 0, winreg.REG_SZ, "Segoe UI")

    def read_substitutes(self) -> dict[str, str | None]:
        names = ["MS Shell Dlg", "MS Shell Dlg 2"]
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                FONT_SUBSTITUTES_SUBKEY,
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
            ) as key:
                values = {}
                for name in names:
                    try:
                        value, _ = winreg.QueryValueEx(key, name)
                    except FileNotFoundError:
                        value = None
                    values[name] = value
                return values
        except OSError:
            return {}

    def write_substitutes(self, values: dict[str, str | None]):
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            FONT_SUBSTITUTES_SUBKEY,
            0,
            winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY,
        ) as key:
            for name, value in values.items():
                if value is None:
                    try:
                        winreg.DeleteValue(key, name)
                    except FileNotFoundError:
                        pass
                    continue
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)

