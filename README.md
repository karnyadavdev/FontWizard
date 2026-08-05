# Font Wizard

Swap the built-in **Segoe UI** and **Consolas** fonts at the Windows level, system-wide.

## Preview
<p align="center">
  <img src="App/src/assets/screenshots/system-wide.png" alt="System-wide font preview" width="900px"/>
  <br/><sub>Font applied across Windows</sub>
</p>


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


## Built With

- PySide6
- fontTools
  
## Project Status

I originally built it to be a commercial product, but decided to open-source it. Future updates will focus strictly on bug fixes, if any.

## License

[MIT](LICENSE)
