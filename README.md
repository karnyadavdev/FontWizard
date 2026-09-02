<p align="center">
  <img src="App/src/assets/font-wizard-icon.png" alt="Font Wizard" width="100"/>
</p>

<h2 align="center">Font Wizard : Complete Windows 11 & 10 System Font Changer</h2>


<p align="center">
  <b>Your font. Every app.
  Truly replace your Windows’ default font everywhere.<br>
 Start, Taskbar, WinUI 3, UWP, Electron, Win32, Office, Chrome and beyond. </b>


</p>

<p align="center">
  <sub>Built with Python · PySide6 · fontTools </sub> <br>
  <sub>License: MIT &nbsp;·&nbsp; Status: Public Release v2.0</sub>
</p>


## Screenshots

<table>
  <tr>
    <img src="App/src/assets/screenshots/app-variants.png" alt="Font Wizard Apply Screen"/>
    <img src="App/src/assets/screenshots/system-wide.png" alt="System-wide font preview"/>
  </tr>
</table>

---

## Download



Download the [latest release](https://github.com/karnyadavdev/fontwizard/releases/latest) and run `FontWizard.exe`.

- Supports **Windows 11** and **Windows 10**.
- Only `.ttf` fonts are supported. Variable and `.otf` fonts are not supported.
> If you have a font that is only available in `.otf`,  you easily convert it to `.ttf` using online font converters.

<br>

### WinGet (Alternative method)
```powershell
winget install -e --id karnyadavdev.FontWizard
```
---

##  Comparison: FontWizard vs. Traditional Tools

| Capability / Surface | Standard Registry Hacks | Winaero Tweaker | FontWizard |
| :--- | :---: | :---: | :---: |
| **Legacy Win32 Apps** (Control Panel, Notepad) | ✅ Yes | ✅ Yes | ✅ **Yes** |
| **Modern WinUI 3 & Settings** | ❌ Broken / Incomplete | ⚠️ Partial | ✅ **100% Coverage** |
| **UWP Apps & System Shell** | ❌ Ignored | ⚠️ Inconsistent | ✅ **Full Support** |
| **Electron & Chromium Apps** (VS Code, Discord) | ❌ No | ❌ No | ✅ **Yes** |
| **System Icon & Glyph Preservation** | ⚠️ Often breaks icons | ⚠️ Requires care | ✅ **Safe Glyph Pass-through** |
| **1-Click Revert to Default (Segoe UI)** | ❌ Manual restore needed | ⚠️ Partial rollback | ✅ **Instant 1-Click Restore** |

---
## Build from source

```bat
.\App\build.bat
```

Build output goes to `App\dist\`.

---

<p align="center"> 
Built with ❤️ by <a href="https://github.com/karnyadavdev">karnyadavdev</a>. If Font Wizard helped you, consider starring the repo ⭐
</p>

