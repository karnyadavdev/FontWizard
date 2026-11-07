>Note: Version 6 is ready for release on November 9, bringing support for Chinese, Korean, Japanese, and other languages.<br><br>
It also fixes an issue where English text continued to use Segoe UI in non-English apps, affecting users who have set their device language to English but live in countries where apps are primarily designed for other languages.<br><br>
Additionally, excessive empty spacing above and below text in fonts not designed primarily for UI use has now been fixed. Previously, some fonts like Google Sans (designed for the web use only) could introduce extra vertical space, making UI elements and containers unnecessarily tall. You can now use these fonts without affecting the UI layout.
<p align="center">
  <img src="App/src/assets/font-wizard-icon.png" alt="Font Wizard" width="110"/>
</p>

<h1 align="center"> Font Wizard 5</h1>

<p align="center">
  <b>Change Windows 11 & 10 system font Everywhere</b>. <br>  Start, Taskbar, Lockscreen, Old Apps, New UWP & WinUI apps, everywhere <br>
  


  

---




 <h1 align="center">📸 Screenshots</h1>
</p>

<p align="center">
  <img src="App/src/assets/screenshots/system-wide2.png" alt="System-wide font preview" width="100%"/>
</p>

<p align="center">
  <img src="App/src/assets/screenshots/app-variants.png" alt="Font Wizard Apply Screen" width="100%"/>
</p>
<p align="center">
  <img src="App/src/assets/screenshots/app-variants2.png" alt="Font Wizard Apply Screen" width="100%"/>
</p>


<p align="center">
  <img src="App/src/assets/screenshots/screenshot (2).png" alt="Font Wizard screenshot 2" width="100%"/>
</p>







---

### If you wish to install via terminal

```powershell
winget install -e --id karnyadavdev.FontWizard
```


## Build from Source


```bat
.\App\build.bat
```

Build output goes to `App\dist\`.
