# Shelter Pet Viewer

A kiosk slideshow for adoption events — downloads adoptable and foster animals from ShelterLuv and displays them fullscreen from a local cache.

Two platforms share the **same cache format**:

| Platform | Location | Use case |
|----------|----------|----------|
| **Windows** | `ShelterPetViewer/` (.NET 8 WPF) | PC with tray app, multi-monitor, keyboard |
| **Raspberry Pi** | `pi/` (Python + pygame) | Dedicated kiosk with GPIO buttons, autostart |

---

## Windows

### Build

```powershell
cd ShelterPetViewer
dotnet publish -c Release
```

Output: `bin\Release\net8.0-windows\win-x64\publish\ShelterPetViewer.exe`

### First run

1. Run `ShelterPetViewer.exe` — it starts in the system tray.
2. Right-click → **Update Cache** (requires internet).
3. Right-click → **Show Fullscreen**.

### Controls

- **← / →** Previous / next animal
- **Esc** Exit fullscreen

### Tray menu

Animal set, display target, slide interval (10–60s), start with Windows, update cache.

### Data locations

- Cache: `%AppData%\ShelterPetViewer\cache\`
- Settings: `%AppData%\ShelterPetViewer\settings.json`
- Log: `%AppData%\ShelterPetViewer\log.txt`

---

## Raspberry Pi

See **[pi/README.md](pi/README.md)** for full setup: GPIO wiring, autostart, systemd service, and button controls.

Quick start on the Pi:

```bash
cd pi
./setup.sh
source .venv/bin/activate
python -m shelter_pet_viewer
```

**Buttons:** Forward/Back navigate slides (or menu up/down). Menu opens options. Return goes back one level.

Syncs on startup and every 2 hours when online.

---

## Shared cache

Both apps read/write the same structure:

```
cache/
  adoption/{animalId}/info.txt, photos.json, 1.jpg ...
  foster/{animalId}/...
```

You can sync on Windows and copy the cache to the Pi, or let the Pi sync directly.
