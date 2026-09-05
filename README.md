<p align="center">
  <img src="App/src/assets/font-wizard-icon.png" alt="Font Wizard" width="100"/>
</p>

<h1 align="center">Font Wizard</h1>


<p align="center">
  <b>Your font. Every app.
  Truly replace your Windows’ default font everywhere.<br>
 Start, Taskbar, WinUI 3, UWP, Electron, Win32, Office, Chrome and beyond. 

</b>
</p>

<p align="center">
  <sub>Built with Python · PySide6 · fontTools </sub> <br>
  <sub>License: MIT &nbsp;·&nbsp; Status: Public Release v3.0</sub>
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

Font Wizard is the only complete windows 11 & 10 Font changer unlike all other tools which fails at modern system components and third party apps, also font wizard is extemely safe to apply and revert fonts , as easy as one click 
|  | Registry Hacks | Winaero Tweaker | Font Wizard |
| :--- | :---: | :---: | :---: |
| **Legacy Win32 Apps** (Control Panel, Notepad, etc) | ✅  | ✅  | ✅  |
| **Modern WinUI 3 apps** | ❌  | ❌ | ✅  |
| **UWP Apps & System Shell** | ❌ | ❌  | ✅  |
| **Electron & Chromium Apps** (VS Code, Discord, chrome) | ❌ | ❌ | ✅ |
| **System Icons & Glyph Preservation** | ⚠️  | ⚠️  | ✅ |
| **1-Click Revert to Default (Segoe UI)** | ❌  | ⚠️  | ✅  |

---


## Build from source

```bat
.\App\build.bat
```

Build output goes to `App\dist\`.

---

<p align="center"> 
Built with ❤️ by <a href="https://github.com/karnyadavdev">karnyadavdev</a>, consider starring the repo ⭐ if it helped u.
</p>

