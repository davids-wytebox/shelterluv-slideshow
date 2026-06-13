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
2. Right-click the tray icon → **Update Cache** (requires internet).
3. Right-click → **Show Fullscreen** to start the slideshow.

## Controls

- **←** Previous animal (20-item history)
- **→** Random next animal
- **Esc** Exit fullscreen
- Auto-advances every 45 seconds
