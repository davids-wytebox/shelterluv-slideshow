# Shelter Pet Viewer — Raspberry Pi Kiosk

Fullscreen adoption slideshow for Raspberry Pi 4 running **Raspberry Pi OS** (Bookworm or later). Uses the same cache format as the Windows app, so you can sync on either platform.

## What you get

- Fullscreen slideshow on boot
- Four GPIO buttons: **Forward**, **Back**, **Menu**, **Return**
- On-screen menu for animal set, slide interval, and manual cache update
- Automatic cache sync on startup, then every **2 hours** when internet is available
- Keyboard fallback for testing without wiring (arrow keys, `M`, Esc/Backspace)

## Button wiring (default BCM pins)

Wire each button between a GPIO pin and **GND**. The Pi uses internal pull-ups, so no external resistors are required for short cable runs.

| Button | GPIO (BCM) | Physical pin |
|--------|------------|--------------|
| Forward | 17 | 11 |
| Back | 27 | 13 |
| Menu | 22 | 15 |
| Return | 23 | 16 |
| GND (all buttons) | — | 6, 9, 14, 20, 25, 30, 34, or 39 |

Change pins in `config.json` if needed (copy from `config.example.json`).

## Controls

### Slideshow mode

| Button / Key | Action |
|--------------|--------|
| Forward / → | Next animal (or forward in history) |
| Back / ← | Previous animal |
| Menu / M | Open options menu |
| Return / Esc | — |

### Menu mode

| Button / Key | Action |
|--------------|--------|
| Forward / → | Move down |
| Back / ← | Move up |
| Menu / M | Open submenu or activate setting |
| Return / Esc | Go up one level (close menu from top level) |

Menu options:

- **Animal Set** — Adoption or Foster
- **Slide Interval** — 10–60 seconds
- **Update Cache Now** — sync immediately when online

## One-time Pi setup

### 1. System packages

```bash
sudo apt update
sudo apt install -y git python3-venv python3-pip libsdl2-dev libjpeg-dev \
  libpng-dev python3-dev python3-gpiozero
```

Add your user to the `gpio` group (log out and back in afterward):

```bash
sudo usermod -aG gpio,render,video $USER
```

### 2. Clone the repo

```bash
cd ~
git clone git@github.com:davids-wytebox/shelterluv-slideshow.git
cd shelterluv-slideshow/pi
chmod +x setup.sh
./setup.sh
```

### 3. Configure GPIO pins (optional)

```bash
cp config.example.json config.json
nano config.json
```

### 4. Test manually

Connect the Pi to your display, then:

```bash
cd ~/shelterluv-slideshow/pi
source .venv/bin/activate
python -m shelter_pet_viewer
```

First launch syncs the cache in the background. Press **Menu** to change settings. Ctrl+Q exits.

## Autostart on boot (fullscreen kiosk)

### 1. Auto-login to desktop

```bash
sudo raspi-config
```

Go to **System Options → Boot / Auto Login → Desktop Autologin**.

### 2. Disable screen blanking

```bash
sudo raspi-config
```

**Display Options → Screen Blanking → No**.

Also add to `/etc/xdg/lxsession/LXDE-pi/autostart` (or `~/.config/lxsession/LXDE-pi/autostart`):

```bash
@xset s off
@xset -dpms
@xset s noblank
```

### 3. Install systemd service

Edit the service file if your username or install path differs:

```bash
nano ~/shelterluv-slideshow/pi/systemd/shelter-pet-viewer.service
```

Then install:

```bash
sudo cp ~/shelterluv-slideshow/pi/systemd/shelter-pet-viewer.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable shelter-pet-viewer.service
sudo systemctl start shelter-pet-viewer.service
```

Check status and logs:

```bash
sudo systemctl status shelter-pet-viewer
journalctl -u shelter-pet-viewer -f
tail -f ~/.local/share/ShelterPetViewer/log.txt
```

### 4. Hide mouse cursor (optional)

Install unclutter:

```bash
sudo apt install -y unclutter
```

Add to autostart:

```bash
@unclutter -idle 0.1 -root
```

## Data locations (Pi)

| Item | Path |
|------|------|
| Cache | `~/.local/share/ShelterPetViewer/cache/adoption/` and `foster/` |
| Settings | `~/.local/share/ShelterPetViewer/settings.json` |
| Log | `~/.local/share/ShelterPetViewer/log.txt` |
| Pi config | `~/shelterluv-slideshow/pi/config.json` |

The cache layout matches Windows (`%AppData%\ShelterPetViewer\cache\`), so you can rsync a cache from a PC:

```bash
rsync -av "/mnt/windows/Users/YourName/AppData/Roaming/ShelterPetViewer/cache/" \
  ~/.local/share/ShelterPetViewer/cache/
```

## Sync schedule

- Sync runs immediately on startup
- Then every **2 hours** (configurable via `sync_interval_hours` in `config.json`)
- If offline, it logs quietly and waits for the next interval
- Manual sync: **Menu → Update Cache Now**

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Black screen on boot | Check `journalctl -u shelter-pet-viewer`; ensure desktop autologin is enabled |
| Buttons do nothing | Verify wiring to GND; check `config.json` pins; confirm user is in `gpio` group |
| No animals shown | Wait for first sync or run manual update; check log file |
| pygame won't start | Run from desktop session (needs `DISPLAY=:0`), not SSH without X |
| GPIO "permission denied" | `sudo usermod -aG gpio $USER` and re-login |

## Development on Windows

The Pi app is Python-only and does not affect the Windows WPF build. Test logic with keyboard controls on any machine that has Python 3.10+ and pygame installed.
