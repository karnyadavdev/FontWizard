<p align="center">
    <a href="https://github.com/karnyadavdev/fontwizard/releases"><img src="https://img.shields.io/badge/Download installer-blue" alt="Downloads"/></a>
  
</p>
<p align="center">
  <img src="App/src/assets/font-wizard-icon.png" alt="Font Wizard" width="110"/>
</p>

<h1 align="center"> Font Wizard </h1>

<p align="center">
  <b>Customize Windows' system font completely<br> Start, Taskbar, WinUI 3, UWP, Electron, Win32, Every app & beyond</b>.
</p>






<p align="center">
 <b> ⭐ Star the repo </b>, it helps others discover it
</p>

---

## 📸 Screenshots

<table>
  <tr>
    <td align="center">
      <img src="App/src/assets/screenshots/app-variants.png" alt="Font Wizard Apply Screen"/>
      <br> App UI
    </td>
    <td align="center">
      <img src="App/src/assets/screenshots/system-wide.png" alt="System-wide font preview"/>
      <br> System-wide look after applying
    </td>
  </tr>
</table>

---

## 📥 Download


Download the [**latest release**](https://github.com/karnyadavdev/fontwizard/releases/latest) and run `FontWizard.exe`

- Supports **Windows 11** and **Windows 10**
- Only `.ttf` fonts are supported (`.otf` not supported)
>  **Tip:** Have only `.otf`? Convert it to `.ttf`

<br>

### 📦 Alternative method, Run this in Terminal 


```powershell
winget install -e --id karnyadavdev.FontWizard
```

---

## Why Font Wizard was made?

|  |  Registry Hacks |  Winaero Tweaker |  Font Wizard |
| :--- | :---: | :---: | :---: |
| **Legacy Win32 Apps** (Control Panel, Notepad, etc) | ✅ | ✅ | ✅ |
| **Modern WinUI 3 apps** | ❌ | ❌ | ✅ |
| **UWP Apps & System Shell** | ❌ | ❌ | ✅ |
| **Electron & Chromium Apps** (VS Code, Discord, Chrome) | ❌ | ❌ | ✅ |
| **System Icons & Glyph Preservation** | ⚠️ | ⚠️ | ✅ |
| **1-Click Revert to Default (Segoe UI)** | ❌ | ⚠️ | ✅ |


---

## Build from Source


```bat
.\App\build.bat
```

Build output goes to `App\dist\`.




<p align="center">
  Built with ❤️ by <a href="https://github.com/karnyadavdev">karnyadavdev</a>
</p>
