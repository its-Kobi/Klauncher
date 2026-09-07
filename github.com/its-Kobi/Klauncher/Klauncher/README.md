# KLauncher — Modern Minecraft Launcher

> A clean, fast and original Minecraft launcher for Windows — Vanilla, Fabric, Forge, Quilt, OptiFine & Custom clients. Inspired by PrismLauncher's power and NoRiskClient's minimal dark aesthetic, built from scratch in Python + PySide6.

![KLauncher](Assets/Icons/Klauncher_logo.svg)

**Version:** 1.0.0 · **By KOBI · 2026** · **License:** Open Source · **Platform:** Windows 10/11 (x64)

---

### ✨ Features

**Instances — Fully Isolated**
* Each instance is a self-contained folder (`instances/<name>/minecraft/` with its own `mods/`, `saves/`, `resourcepacks/`, `logs/`, `config/`)
* Create Vanilla, Fabric (auto best loader), Quilt, Forge, OptiFine or Custom in one click
* Groups/folders, copy/export/import (zip), drag & drop `.jar`/`.zip` onto instance tiles
* `Load default .minecraft versions` — import all `%APPDATA%/.minecraft/versions` as instances

**Mods & Content — Modrinth Built-In**
* Browse Modrinth without leaving the launcher: **Mods**, **Resource Packs**, **Shader Packs**, **Datapacks**
* Top trending on open + search any Modrinth project (not just top 20), small 24px icons, version/loader filtered to your instance (`1.21.1` + `Fabric` → only `1.21.1` Fabric builds)
* Install via double-click or drag result onto any instance tile — lands in correct `mods/`/`resourcepacks/`/`shaderpacks/`/`datapacks/`
* Vanilla gating: Mods/Shaders blocked on Vanilla with clear message
* Get A Modpack — top + search any Modrinth modpack, installs with its Modrinth icon to instances list (`.mrpack` `overrides/` extracted)

**Java — Automatic**
* Auto-detects all system Javas (`JAVA_HOME`, `PATH`, registry, vendors) via `launcher/java_detector.py`
* Auto-matches: `≤1.16 → Java 8`, `1.17 → 16`, `1.18-1.20.4 → 17`, `1.20.5+ → 21`, `1.21+ → 21/25`
* Missing → auto-downloads Temurin JRE (`api.adoptium.net`) to `%APPDATA%/KLauncher/java/temurin-*`, then auto relaunches (e.g. `1.8.9` auto gets Java 8)

**Accounts — Secure**
* Offline (3-16 chars) + **Microsoft OAuth2 Device Code** (`launcher/auth/manager.py`) — no password ever stored, `QDesktopServices.openUrl` to `microsoft.com/link`
* Ownership verified via `api.minecraftservices.com` — `This account does not own Java Edition` blocked before launch
* Left → Offline list + create at bottom, Right → Microsoft auto sign-in panel

**Polish**
* Dark minimal NoRisk-style shell: 56px left rail, top bar (instance/account selectors), centered head-only launch (96px skin head, not full body), smooth fade/scale animations (`QPropertyAnimation`), black title bar (`DwmSetWindowAttribute` immersive dark), gradient veil under everything with low opacity
* Minecraft fonts: `MinecraftTen-VGORe` for titles, `Minecraft` (`Monocraft`) for body — default, no toggle
* Themes: `themes/dark.json` / `Light (Beta)` (warning shown — Light is buggy this version), accent/gradient saved to `%APPDATA%/KLauncher/config.json`
* Play → `STOP` live when running, tray minimize option, logs on main tab toggle, Health Check / Diff Preview / History per instance
* Servers tab: add `name + IP` → writes `servers.dat` (gzipped NBT)

### 📦 Installation (User)

1. Download `KLauncher-Setup.exe` (InstallForge)
2. Install → launch → create Offline or Sign in with Microsoft → Create Instance → Launch

No `Java` pre-install needed — KLauncher will fetch it.

### ▶️ Usage

* **Launch:** Select instance + account → `LAUNCH` (shows `Fabric Loader 1.21.1` clean names)
* **Instances:** Grid/list toggle, search, group filter
* **Edit instance:** `Right-click → Edit` → 10 tabs (Version, Mods, Resource/Shaders/Datapacks with Modrinth, Worlds, Screenshots, Servers, Notes, Settings overrides, Log, History)
* **Drag & Drop:** `.jar`/`.zip` or Modrinth result onto instance tile

### 🛠️ Building from Source (Windows)

```powershell
git clone https://github.com/yourname/KLauncher
cd KLauncher
python -m venv venv; venv\Scripts\activate
pip install -r requirements.txt  # PySide6, requests
python main.py

# OneDir exe (ready for InstallForge)
pip install pyinstaller
pyinstaller KLauncher.spec  # → dist/KLauncher/KLauncher.exe
```

`KLauncher.spec` includes `Assets/`, `themes/`, `launcher/`, `ui/` and is `sys._MEIPASS` aware (`launcher/paths.py:get_base_dir`) for frozen exe. Minecraft data stays in `%APPDATA%/KLauncher` vs `%APPDATA%/.minecraft` — never deletes `.minecraft`.

### ⚙️ Requirements

* Windows 10/11 x64, 2GB RAM default (configurable), internet for first version/mod download.

### 💙 Supporting KLauncher

> ### 💙 Supporting KLauncher
>
> I currently don't have a donation option because I'm not old enough to legally set up my own bank account or PayPal account.
>
> If you'd still like to support the project, something simple like a **Minecraft gift card** or another small gift would mean a lot! You can contact me through my **email or Discord** if you'd like to send something.
> Discord : kobix1
> Email : itsmek0bi21@gmail.com
>
> Thank you for supporting KLauncher! 🚀

### 📄 License

Open Source — inspired by PrismLauncher (GPL-3.0) and NoRiskClient layout, **no code/assets copied**. KLauncher is not affiliated with Mojang, Microsoft, PrismLauncher or NoRiskClient.

---

**KLauncher — Launch clean. Stay original.**
