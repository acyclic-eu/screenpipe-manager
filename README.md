# Screenpipe Manager

A lightweight macOS menu bar app + web dashboard for controlling [Screenpipe](https://github.com/mediar-ai/screenpipe) locally.

## What it does

- **Menu bar icon** (eye) - shows recording status, start/stop from the menu bar
- **Web dashboard** - timeline, search, and stats at `http://localhost:7654`
- **Screenshot thumbnails** - actual frame previews in search results
- **No cloud** - everything runs locally, no external services

## Requirements

- macOS (Apple Silicon or Intel)
- [Screenpipe](https://github.com/mediar-ai/screenpipe) CLI installed and working
- Python 3.12+ (for the web server)
- Xcode Command Line Tools (for Swift compilation)

## Installation

### 1. Build the Swift menu bar app

```bash
cd screenpipe-manager
swiftc MenubarApp.swift -o "Screenpipe Manager" -framework Cocoa
```

### 2. Install the app bundle

```bash
mkdir -p "/Applications/Screenpipe Manager.app/Contents/MacOS"
mkdir -p "/Applications/Screenpipe Manager.app/Contents/Resources"
cp "Screenpipe Manager" "/Applications/Screenpipe Manager.app/Contents/MacOS/"
cp Info.plist "/Applications/Screenpipe Manager.app/Contents/"
cp index.html "/Applications/Screenpipe Manager.app/Contents/Resources/"
```

### 3. Launch

```bash
open "/Applications/Screenpipe Manager.app"
```

Or find it via Spotlight (Cmd+Space, type "Screenpipe Manager").

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

## Configuration

Edit `server.py` and `MenubarApp.swift` to change:

- `SCREENPIPE_BIN` - path to your screenpipe binary
- `SCREENPIPE_PORT` - screenpipe API port (default: 3030)
- `SERVER_PORT` - web dashboard port (default: 7654)

## License

MIT
