# Screenpipe Manager

A lightweight macOS menu bar app + web dashboard for controlling [Screenpipe](https://github.com/mediar-ai/screenpipe) locally.

## What it does

- **Menu bar icon** (eye) - shows recording status, start/stop from the menu bar
- **Web dashboard** - timeline, search, and stats at `http://localhost:7654`
- **Screenshot thumbnails** - actual frame previews in search results
- **No cloud** - everything runs locally, no external services

## Requirements

- macOS (Apple Silicon or Intel)
- Python 3.12+ (for the web server)
- Xcode Command Line Tools (for Swift compilation)

## Setup

### Step 1: Install Screenpipe

Screenpipe is the recording engine. The official desktop app is paid ($25/mo), but the CLI is free and source-available.

#### Option A: Build from source (recommended - full control, free)

```bash
git clone https://github.com/mediar-ai/screenpipe.git
cd screenpipe
cargo build --release
```

The binary will be at `target/release/screenpipe`.

#### Option B: Install via npm

```bash
npx screenpipe record --port 3030
```

This runs the CLI without building from source.

#### Grant macOS permissions

On first launch, macOS will prompt for:

1. **Screen Recording** - System Settings > Privacy & Security > Screen Recording - enable for your terminal app (e.g. Ghostty, Terminal, iTerm)
2. **Microphone** - System Settings > Privacy & Security > Microphone - enable for your terminal app

If permissions are missing or stale, reset and re-grant:

```bash
# Find your terminal bundle ID (e.g. com.cmuxterm.app for cmux/Ghostty)
tccutil reset Microphone com.cmuxterm.app
tccutil reset ScreenCapture com.cmuxterm.app
```

Then restart screenpipe - macOS will re-trigger the permission dialogs.

#### Get your API key

Screenpipe requires API auth for all endpoints. Get your key:

```bash
screenpipe auth token
# Output: sp-xxxxxxxx
```

Store it - the manager server needs it to proxy API calls.

#### Verify it works

```bash
# Start recording
screenpipe record --port 3030 --language english

# Check health (no auth needed)
curl http://localhost:3030/health

# Search (auth required)
curl -H "Authorization: Bearer sp-xxxx" http://localhost:3030/search?limit=5
```

### Step 2: Build Screenpipe Manager

```bash
git clone https://github.com/acyclic-eu/screenpipe-manager.git
cd screenpipe-manager

# Compile the Swift menu bar app
swiftc MenubarApp.swift -o "Screenpipe Manager" -framework Cocoa
```

### Step 3: Install the app bundle

```bash
APP="/Applications/Screenpipe Manager.app"
mkdir -p "$APP/Contents/MacOS"
mkdir -p "$APP/Contents/Resources"
cp "Screenpipe Manager" "$APP/Contents/MacOS/"
cp Info.plist "$APP/Contents/"
cp index.html "$APP/Contents/Resources/"
```

### Step 4: Configure paths

Edit `MenubarApp.swift` and `server.py` to match your setup:

**MenubarApp.swift:**
```swift
let screenpipeBin = "/path/to/screenpipe"    // path to your screenpipe binary
let screenpipePort = "3030"                    // screenpipe API port
let dashboardURL = "http://localhost:7654"     // web dashboard URL
```

**server.py:**
```python
SCREENPIPE_BIN = "/path/to/screenpipe"         # path to your screenpipe binary
SCREENPIPE_PORT = 3030                          # screenpipe API port
SERVER_PORT = 7654                              # web dashboard port
```

The server auto-discovers the API key by running `screenpipe auth token`, so no need to hardcode it.

### Step 5: Launch

```bash
open "/Applications/Screenpipe Manager.app"
```

Or find it via Spotlight (Cmd+Space, type "Screenpipe Manager").

You should see an **eye icon** in your menu bar. Click it to:

- **Start Recording** - launches screenpipe
- **Stop Recording** - kills screenpipe
- **Open Dashboard** - opens the web UI in your browser
- **Status** - shows current recording state and meeting detection

The web dashboard is at `http://localhost:7654`.

## Files

| File | Purpose |
|---|---|
| `MenubarApp.swift` | Swift menu bar app (compiles to native binary) |
| `server.py` | Python stdlib web server - serves dashboard, proxies screenpipe API, controls process |
| `index.html` | Single-page web dashboard (timeline, search, stats) |
| `Info.plist` | macOS app bundle metadata |

## How it works

```
Menu bar app (Swift)
  ├── starts/stops screenpipe CLI
  └── launches server.py in background

server.py (Python)
  ├── serves index.html at localhost:7654
  ├── /api/status - screenpipe health + process status
  ├── /api/start, /api/stop - control recording
  ├── /api/proxy/* - proxies to screenpipe API (port 3030) with auth
  └── /api/frame/* - serves screenshot JPEGs

index.html (browser)
  ├── fetches status every 5s
  ├── search with tabs (All / OCR / Audio)
  └── shows frame thumbnails + transcription text
```

## Architecture

Screenpipe itself has two pipelines:

| Pipeline | What it does | Tech |
|---|---|---|
| Vision | Captures screenshots on all monitors, extracts text | ScreenCaptureKit + Accessibility tree (fallback: Apple Vision OCR) |
| Audio | Captures mic + system audio, transcribes to text | CoreAudio + Whisper (local STT) |

Screenpipe Manager is a thin control layer on top:

- It does **not** record anything itself
- It starts/stops the screenpipe process
- It proxies the screenpipe API (adding auth headers)
- It serves a web UI for browsing/searching recordings

## Troubleshooting

### No audio transcriptions

1. Check microphone permission: `System Settings > Privacy & Security > Microphone`
2. Check audio level in health endpoint:
   ```bash
   curl http://localhost:3030/health | python3 -m json.tool | grep audio_level
   ```
   RMS below 0.01 means near-silence. Try increasing mic input volume:
   ```bash
   osascript -e 'set volume input volume 100'
   ```
3. Screenpipe uses **batch mode** by default - transcriptions may take 1-2 minutes to appear after speaking

### Menu bar icon not showing

The Swift app needs to be launched as a proper `.app` bundle (not run directly as a binary). Use `open` to launch it:

```bash
open "/Applications/Screenpipe Manager.app"
```

If it still doesn't show, check that `LSUIElement` is `true` in `Info.plist` and that no menu bar manager app (like Ice, Bartender, Hidden Bar) is hiding it.

### API unauthorized error

The screenpipe fork requires auth for all endpoints (even localhost). The manager server auto-discovers the key via `screenpipe auth token`. If that fails:

```bash
# Find the key manually
screenpipe auth token

# Or check the secrets database
sqlite3 ~/.screenpipe/secrets.sqlite "SELECT key FROM secrets WHERE key LIKE 'sp-%' LIMIT 1;"
```

Then hardcode it in `server.py`:
```python
API_KEY = "sp-xxxxxxxx"
```

### Web dashboard not loading

Check that the Python server is running:

```bash
curl http://localhost:7654/api/status
```

If port 7654 is in use, kill the old process:

```bash
lsof -ti:7654 | xargs kill -9
```

## License

MIT
