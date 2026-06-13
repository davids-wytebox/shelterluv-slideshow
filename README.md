# Shelter Pet Viewer

A small Windows tray app that downloads adoptable and foster animals from ShelterLuv and displays them fullscreen for adoption events — works fully offline from a local cache.

## Build

```powershell
cd ShelterPetViewer
dotnet publish -c Release
```

The single-file executable is at `bin\Release\net8.0-windows\win-x64\publish\ShelterPetViewer.exe`

## First run

1. Run `ShelterPetViewer.exe` — it starts in the system tray.
2. Right-click the tray icon → **Update Cache** (requires internet). This downloads both adoption and foster animals.
3. Right-click → **Show Fullscreen** to start the slideshow.

## Tray menu

- **Animal Set** — Adoption or Foster slideshow
- **Display On** — Primary, secondary, or all monitors
- **Slide Interval** — 10, 15, 20, 30, 45 (default), or 60 seconds
- **Start with Windows** — launch at login

## Controls

- **←** Previous animal (20-item history)
- **→** Forward in history when available, otherwise random next
- **Esc** Exit fullscreen
- Keyboard works from any monitor while fullscreen is open

## Data locations

- Cache: `%AppData%\ShelterPetViewer\cache\adoption\` and `\foster\`
- Settings: `%AppData%\ShelterPetViewer\settings.json`
- Log: `%AppData%\ShelterPetViewer\log.txt`

## Notes

- An open slideshow reloads automatically after **Update Cache** completes.
- Close the app from the tray before publishing a new build (the exe cannot be overwritten while running).
