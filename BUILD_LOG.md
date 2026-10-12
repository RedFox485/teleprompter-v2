# Teleprompter V2 - Build Log

## Project Overview
Standalone band/live karaoke teleprompter with lyrics, chords, BPM sync, and MIDI clock input. Built as a Textual TUI application in Python 3.11+, designed to run on MacBook for development and Raspberry Pi 3B for deployment alongside lightrig.

---

## Session 2026-10-12: Complete Build & Polish

### Starting Point
Fresh project `~/Documents/projects/teleprompter-v2/` created from scratch, extracting just the teleprompter/lyrics functionality from the larger `live-show-manager` system (which included Reaper integration, full show management, etc.).

### Major Features Implemented

#### Core Functionality
- **ChordPro (.cho/.pro) parser** - Industry standard format with inline chords, sections, directives
- **Large lyrics display** - High contrast dark mode, chord highlighting (cyan), section headers (magenta)
- **BPM-synced auto-scroll** - Configurable lines-per-beat (default 0.5)
- **Tap tempo** - SPACE key calculates BPM from tap intervals
- **Visual click flash** - Screen flashes on downbeat
- **MIDI clock sync** - Receives MIDI Clock (0xF8), Start (0xFA), Stop (0xFC) for BPM + transport sync
- **Section navigation** - Jump between Verse/Chorus/Bridge
- **Transpose** - `[` / `]` shifts chords ± semitones
- **Setlist management** - Add/remove/reorder, song status (Rehearsed/Winging It/Request)

#### Search System (Enhanced)
| Query Type | Examples | Matches |
|------------|----------|---------|
| Key letter | `G`, `g`, `Em`, `em` | Key signature |
| Key name | `G major`, `g ma`, `g majo`, `E minor`, `e min`, `e mi`, `a mi` | Key with major/minor |
| Tempo exact | `98`, `87`, `120` | BPM ±2 |
| Tempo range | `90-110`, `100-140` | BPM range |
| Tempo with unit | `120bpm` | BPM ±5 |
| Artist/title | `lyn`, `skyn`, `sweet`, `wonder`, `free` | Partial match |
| Empty | `` | All songs (max 8) |

**Smart single-letter handling**: Single letters A-G trigger key search only if songs exist in that key; otherwise fall through to title/artist search. Single letters H-Z always do title/artist search.

#### Settings Page (Redesigned)
| Widget | Type | Description |
|--------|------|-------------|
| Font size | Input | Font size in points |
| Chord color | Select | 16 color options (dropdown) |
| Text color | Select | 16 color options |
| Background color | Select | 16 color options |
| Auto-scroll | Switch | Toggle on/off |
| Scroll speed | Input | Lines per beat (e.g., 0.5) |
| MIDI port | Input | Port name + Scan button |
| MIDI channel | Input | 0=omni, 1-16 |
| Songs dir | Input | Path to songs |
| Setlists dir | Input | Path to setlists |

All settings have descriptive labels and are fully editable via Tab navigation.

#### Data & Persistence
- **Song library** - Cached scanning with file hash (mtime+size), JSON cache
- **Setlists** - JSON files with UUIDs, timestamps, song metadata
- **Config** - Auto-saved to `config.json`

#### MIDI Integration
- Virtual port support for inter-app communication
- Receives from Akai Force, lightrig, or any MIDI clock source
- BPM smoothing (0.7/0.3 exponential moving average)
- Auto-scroll starts/stops with MIDI Start/Stop

---

### Technical Stack
- **Language**: Python 3.11+
- **UI Framework**: Textual (TUI) - lightweight, runs on Pi 3B (~50MB RAM)
- **MIDI**: python-rtmidi
- **Data**: pydantic, pathlib, JSON
- **Testing**: pytest + Textual's `run_test()` for virtual UI testing

---

### Test Coverage
| Test Type | Count | Status |
|-----------|-------|--------|
| Unit tests | 19 | ✅ Passing |
| Virtual/UI tests | 8 | ✅ Passing |
| **Total** | **27** | ✅ **All Passing** |
| Ruff linting | - | ✅ Clean |

---

### Git History (This Session)
```
e357640 Add descriptive labels to settings page - all 27 tests passing
cf8f6be Fix search issues (G maj, single letter search), verify setlist order, redesign settings page with Select/Switch widgets - all 27 tests passing
0b6de6e Fix search result height (auto) and verify settings inputs editable - all 27 tests passing
ad422f6 Enhanced search: key search (G, Em, G major, E minor), tempo search (98, 90-110, 120bpm), artist/title partial, max 8 results
17cb7b4 Fix search result height and settings visibility - all 27 tests passing
44c089a All 5 major issues fixed - 27 tests passing
5449928 Current state
```

---

### Files Created
```
teleprompter-v2/
├── run.py                 # Entry point
├── start.sh               # Startup script (activates venv)
├── deploy_pi.sh           # Pi 3B deployment script
├── requirements.txt       # Production deps
├── pyproject.toml         # Package config
├── README.md              # Full documentation
├── BUILD_LOG.md           # This file
├── songs/                 # 3 sample ChordPro files
├── src/teleprompter/
│   ├── __init__.py
│   ├── app.py             # Main Textual TUI app
│   ├── chordpro.py        # ChordPro parser/renderer
│   ├── library.py         # Song library + setlist manager
│   ├── midi_clock.py      # MIDI clock input handler
│   └── models.py          # Data models
└── tests/
    ├── test_teleprompter.py    # 19 unit tests
    └── virtual_test_runner.py  # 8 virtual/UI tests
```

---

### Run Commands
```bash
# Development (MacBook)
cd ~/Documents/projects/teleprompter-v2
./start.sh

# Or directly
source .venv/bin/activate && python run.py

# Pi 3B Deployment
scp -r ~/Documents/projects/teleprompter-v2 pi@pi.local:~/
ssh pi@pi.local "cd ~/teleprompter-v2 && sudo ./deploy_pi.sh"
```

### Controls
| Key | Action |
|-----|--------|
| `F1-F4` | Switch tabs (Setlist/Lyrics/BPM/Settings) |
| `↑/↓` | Scroll lyrics / Navigate setlist / Search results |
| `SPACE` | Tap tempo (BPM tab) / Toggle auto-scroll (Lyrics tab) |
| `t` | Toggle chord display |
| `[` / `]` | Transpose down/up |
| `a` | Add song to setlist |
| `Delete` | Remove song |
| `Enter` | Select song / Add from search |
| `Escape` | Cancel search / Close dialog |
| `Ctrl+S/O` | Save/Load setlist |
| `Ctrl+Q` | Quit |

---

### Next Steps (Future Sessions)
1. Create GitHub repo and push
2. Add fuzzy search for typos
3. Add song duration estimation
4. Add per-song scroll speed override
5. Add lightrig MIDI sync documentation
6. Pi 3B hardware testing
7. Add foot pedal support for page turns

---

*Build log created: 2026-10-12*
*All 27 tests passing (8 virtual + 19 unit)*
*Ruff linting clean*

---

## Session 2026-10-12 (Part 2): Web Server for iPhone Client

### Web Server Architecture
Added a lightweight WebSocket server using `aiohttp` running on port 8000 (lightrig uses 8080) that serves a single-file PWA client for iPhone 14 Safari.

**Server Features:**
- WebSocket at `ws://<pi-ip>:8000/ws` for real-time sync
- Single HTML file served at `/` (~5KB gzipped)
- Broadcasts: current song, lyrics, scroll position, transpose, BPM, auto-scroll state, setlist, MIDI status
- Receives: tap tempo, song select, transpose, scroll, search, setlist operations
- Pre-calculates next 10 beat times for client-side scheduling to minimize WiFi latency

**Client Features (web_client.html):**
- Single-file vanilla JS/CSS, no frameworks
- Works offline after first load (PWA-ready)
- Large lyrics display with chord highlighting, section headers
- Auto-scroll synced to server BPM
- Visual click flash on downbeat (scheduled locally from server beat times)
- Search modal with same query syntax as TUI
- Setlist panel with select/remove
- Footer controls: prev/next song, tap tempo, transpose up/down, search, setlist toggle
- Wake lock API keeps screen on during performance
- QR code on TUI Web tab for instant iPhone connection

**Integration:**
- New Web tab (F5) in TUI shows server status, URL, connected client count, and QR code
- Settings page: Enable/disable web server (Switch), configurable port (Input, default 8000)
- Broadcasts on: song change, setlist add/remove/reorder, load setlist, MIDI BPM change
- Restart required for port/enable changes

### Files Added/Modified
```
src/teleprompter/
├── web_server.py          # WebSocket server with beat scheduling
├── web_client.html        # Single-file PWA client
├── app.py                 # +WebView, +WebServer integration, +settings
├── models.py              # +web_enabled, +web_port config
requirements.txt           # +aiohttp, +qrcode
```

### Git History (This Session)
```
<new commit>  Web server for iPhone client - WebSocket, PWA, QR code, beat scheduling
e357640 Add descriptive labels to settings page - all 27 tests passing
cf8f6be Fix search issues (G maj, single letter search), verify setlist order, redesign settings page with Select/Switch widgets - all 27 tests passing
0b6de6e Fix search result height (auto) and verify settings inputs editable - all 27 tests passing
ad422f6 Enhanced search: key search (G, Em, G major, E minor), tempo search (98, 90-110, 120bpm), artist/title partial, max 8 results
17cb7b4 Fix search result height and settings visibility - all 27 tests passing
44c089a All 5 major issues fixed - 27 tests passing
5449928 Current state
```

### Test Coverage (Updated)
| Test Type | Count | Status |
|-----------|-------|--------|
| Unit tests | 19 | ✅ Passing |
| Virtual/UI tests | 8 | ✅ Passing |
| **Total** | **27** | ✅ **All Passing** |
| Ruff linting | - | ✅ Clean |

### Controls (Updated)
| Key | Action |
|-----|--------|
| `F1-F5` | Switch tabs (Setlist/Lyrics/BPM/Settings/Web) |
| `↑/↓` | Scroll lyrics / Navigate setlist / Search results |
| `SPACE` | Tap tempo (BPM tab) / Toggle auto-scroll (Lyrics tab) |
| `t` | Toggle chord display |
| `[` / `]` | Transpose down/up |
| `a` | Add song to setlist |
| `Delete` | Remove song |
| `Enter` | Select song / Add from search |
| `Escape` | Cancel search / Close dialog |
| `Ctrl+S/O` | Save/Load setlist |
| `Ctrl+Q` | Quit |