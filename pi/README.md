# Shelter Pet Viewer — Raspberry Pi Kiosk

Fullscreen adoption slideshow for **Raspberry Pi 4** or **Pi Zero 2 W**, running **Raspberry Pi OS** (Bookworm or later). Uses the same cache format as the Windows app, so you can sync on either platform.

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
  libpng-dev python3-dev python3-lgpio python3-libgpiod
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

## Raspberry Pi Zero 2 W

The same `pi/` app runs on a **Pi Zero 2 W** with no code changes — same clone, wiring, GPIO pins, and systemd steps as above. The Zero 2 is a viable low-cost kiosk option if you plan around its limits.

### What is the same

| Item | Notes |
|------|-------|
| Software | Identical setup (`./setup.sh`, systemd service, `config.json`) |
| GPIO buttons | Same BCM pin numbers on the 40-pin header |
| Cache format | Same as Windows and Pi 4 |
| WiFi sync | **Zero 2 W** only — the non-W Zero has no WiFi |
| Display | Mini HDMI → full-size HDMI adapter → monitor or TV |

### What is different

| Item | Pi 4 | Pi Zero 2 W |
|------|------|-------------|
| CPU | ~1.5 GHz quad-core | ~1 GHz quad-core (Pi 3 class) |
| RAM | 1–8 GB | **512 MB** |
| Photo transitions | Fast | Slower (1–3 s is normal) |
| First cache sync | Fine | Can take longer; pre-sync from PC helps |

### Hardware tips

- **Power:** Use a reliable **2.5 A** supply. Undervoltage causes freezes that look like software bugs.
- **Storage:** 32 GB+ microSD recommended; cache grows over time.
- **GPIO header:** Many Zero 2 boards ship without pins soldered — you may need to add a header for buttons.
- **Resolution:** 1080p is a safe default; 4K works but is heavier on the Zero 2.

### Recommended Zero 2 workflow

1. Follow the **One-time Pi setup** and **Autostart** sections above (desktop autologin is the easiest path).
2. **Pre-seed the cache** from Windows before the event, if possible — sync on the PC, then copy:

   ```bash
   rsync -av "/path/to/ShelterPetViewer/cache/" \
     ~/.local/share/ShelterPetViewer/cache/
   ```

   On Windows the cache is at `%AppData%\ShelterPetViewer\cache\`.
3. On first boot without a pre-seeded cache, the slideshow may show “No cached animals” until the background sync finishes. Give it time or use **Menu → Update Cache Now** once online.
4. Use a slide interval of **30–45 seconds** or longer so slower photo loading is less noticeable.

### Optional: lighter boot (save RAM)

The default setup runs under the desktop (X11, `DISPLAY=:0`), which uses a meaningful chunk of the Zero 2’s 512 MB. If the slideshow feels sluggish or the Pi runs out of memory, you can run fullscreen **without the desktop** using pygame’s KMS driver.

An alternate systemd unit is included:

```bash
sudo cp ~/shelterluv-slideshow/pi/systemd/shelter-pet-viewer-kms.service /etc/systemd/system/
sudo systemctl disable shelter-pet-viewer.service   # if the desktop unit was enabled
sudo systemctl daemon-reload
sudo systemctl enable shelter-pet-viewer-kms.service
sudo systemctl start shelter-pet-viewer-kms.service
```

This unit sets `SDL_VIDEODRIVER=kmsdrm` and does not require X11. It is optional and slightly more fiddly than desktop autologin — try the standard path first, and switch to KMS only if you need the extra headroom.

> **Note:** KMS mode boots directly to the slideshow on the framebuffer. You lose the desktop environment while the service is running.

### Zero 2 expectations

| Scenario | Zero 2 W |
|----------|----------|
| Slideshow with cached photos | Good |
| GPIO menu and buttons | Good |
| Background sync every 2 hours | Good (WiFi) |
| Fast photo transitions | Acceptable, not instant |
| Large first-time sync (100+ animals) | Slow — pre-sync from PC recommended |

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
| `lgpio` / `RPi.GPIO` / `pigpio` missing | Run `./setup.sh` again, or `sudo apt install python3-lgpio` then recreate venv: `rm -rf .venv && ./setup.sh` |
| No animals shown | Wait for first sync or run manual update; check log file |
| pygame won't start | Run from desktop session (needs `DISPLAY=:0`), not SSH without X |
| GPIO "permission denied" | `sudo usermod -aG gpio $USER` and re-login |
| Zero 2 sluggish or OOM | Pre-sync cache from PC; try `shelter-pet-viewer-kms.service`; use 1080p display |
| Zero 2 freezes or lightning bolt icon | Weak power supply — use 2.5 A adapter and a short cable |
| Zero 2 black screen with KMS service | Check `journalctl -u shelter-pet-viewer-kms`; confirm user is in `video` and `render` groups |

## Development on Windows

The Pi app is Python-only and does not affect the Windows WPF build. Test logic with keyboard controls on any machine that has Python 3.10+ and pygame installed.
