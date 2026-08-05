# Font Wizard

Swap the built-in **Segoe UI** and **Consolas** fonts at the Windows level, system-wide.

## Preview
<p align="center">
  <img src="App/src/assets/screenshots/system-wide.png" alt="System-wide font preview" width="900px"/>
  <br/><sub>Font applied across Windows</sub>
</p>

## What it changes

Font Wizard swaps the built-in **Segoe UI** (interface) and **Consolas** (monospace) fonts at the
Windows level. Because it replaces the font sources that Windows hands to apps, your new font shows
up almost everywhere — not just in Font Wizard:

| Area | You'll see your font in |
|---|---|
| **Windows UI** | Start menu, Taskbar, Settings, Explorer, context menus |
| **WinUI 3 / modern apps** | Newer Windows apps, notifications, dialogs (Windows 11) |
| **Classic apps** | Traditional Win32 desktop apps, Office, most toolbars |
| **Electron apps** | VS Code, Discord, Slack, Teams, GitHub Desktop |
| **Browsers** | Chrome/Edge UI itself, not the content of web pages |
| **Terminal & code** | Command Prompt, Notepad, code editors — via the Consolas (Monospaced) slot; optionally set a monospace font card, otherwise the UI font is used |

A few things worth knowing:

- Apps that **bundle their own fonts** (some games, specialist editors) are unaffected by design.
- Apps already open keep the old font until they are restarted; the rest of Windows finishes after the next restart.

## Usage
<table>
  <tr>
    <td><img src="App/src/assets/screenshots/app-ready.png" alt="Font Wizard ready state"/></td>
    <td><img src="App/src/assets/screenshots/app-variants.png" alt="Font style variants preview"/></td>
  </tr>
  <tr>
    <td align="center"><sub>Launch screen</sub></td>
    <td align="center"><sub>Font selected</sub></td>
  </tr>
  <tr>
    <td><img src="App/src/assets/screenshots/app-applying.png" alt="Applying a font change"/></td>
    <td><img src="App/src/assets/screenshots/app-restart.png" alt="Restart required after applying fonts"/></td>
  </tr>
  <tr>
    <td align="center"><sub>Applying process</sub></td>
    <td align="center"><sub>Waiting for restart</sub></td>
  </tr>
</table>

## Download

Download [latest release](../../releases/latest) and run `Font Wizard.exe`.

Supports Windows 10 (build 10240+) and Windows 11.

Only .ttf fonts are supported. Variable fonts and `.otf` files are not supported currently.

## Build

```bat
.\App\build.bat
```

Build output goes to `App\dist\`.

## Developer / testing

You can run Font Wizard against a sandbox instead of the real system fonts by setting
these environment variables (useful for development and the test suite):

- `FONTWIZARD_FONTS_DIR` — folder treated as the Windows Fonts directory (default: `%WINDIR%\Fonts`).
- `FONTWIZARD_DATA_DIR` — app data (state, managed/original fonts, pending operations). Default: `%PROGRAMDATA%\Font Wizard`.
- `FONTWIZARD_LOCAL_DIR` — logs and temporary files. Default: `%LOCALAPPDATA%\Font Wizard`.

## Built With

- PySide6
- fontTools
  
## Project Status

I originally built it to be a commercial product, but decided to open-source it. Future updates will focus strictly on bug fixes, if any.

## License

[MIT](LICENSE)
