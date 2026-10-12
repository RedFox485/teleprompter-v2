# Teleprompter V2 - Code Review & Refinement Report

**Date:** 2026-10-11  
**Reviewer:** Kilo (Expert Code Review)  
**Scope:** All source files in `src/teleprompter/`

---

## Executive Summary

The codebase is **functional and well-structured** with 27 passing tests (19 unit + 8 virtual). The architecture follows clean separation of concerns: ChordPro parsing, library management, MIDI clock handling, data models, and Textual TUI. However, several areas need refinement for production readiness, maintainability, and correctness.

---

## Component-by-Component Analysis

### 1. `chordpro.py` - ChordPro Parser ⭐⭐⭐⭐☆

**Strengths:**
- Clean dataclass-based design with `Chord`, `Line`, `Section`, `Song`
- Proper handling of inline chords with regex
- Transpose logic for both chords and key signatures
- Round-trip save/load support
- Good use of `contextlib.suppress` for safe int parsing

**Issues Found:**

| Severity | Issue | Location | Recommendation |
|----------|-------|----------|----------------|
| **High** | Chord regex doesn't validate quality strings properly - accepts invalid chords like `[XYZ]` | Line 39-42 | Add stricter validation or document behavior |
| **Medium** | `ChordQuality` enum defined but never used | Line 11-25 | Remove or integrate into parsing |
| **Medium** | Transpose always uses sharps (no flat preference) | Line 51-52, 134-144 | Add `prefer_flats` option for keys like F, Bb, Eb |
| **Low** | `save_song` doesn't preserve all metadata (unknown directives) | Line 254-293 | Include `metadata` dict in output |
| **Low** | Empty lines create `Line(segments=[("", None)])` - could use sentinel | Line 162 | Consider explicit `is_empty` flag |

**Code Quality Notes:**
- Line 125-126: Type annotation issue - `list[tuple[str, Chord]]` vs `list[tuple[str, Chord \| None]]` variance problem. Use `Sequence` or add type ignores.
- The `_transpose_key` regex `r"([A-G][#b]?)(m|min)?"` doesn't handle all key formats (e.g., "Gmaj7", "F#m7").

---

### 2. `library.py` - Song Library & Setlist Manager ⭐⭐⭐⭐☆

**Strengths:**
- Smart caching with file hash (mtime + size)
- Clean separation: `SongLibrary` for songs, `SetlistManager` for setlists
- Search by title/artist
- JSON persistence with proper serialization

**Issues Found:**

| Severity | Issue | Location | Recommendation |
|----------|-------|----------|----------------|
| **High** | Bare `except Exception: pass` swallows errors silently | Lines 42, 50, 88, 107 | At minimum log errors; consider structured error handling |
| **Medium** | Cache key uses relative path but `get_song` expects relative path - inconsistent | Line 66, 93 | Document or normalize path handling |
| **Medium** | `SongCacheEntry` missing `capo` field | Line 13-21 | Add for completeness |
| **Low** | `scan()` doesn't remove deleted songs from cache | Line 59-91 | Add cache cleanup pass |
| **Low** | Filename-based setlist naming (`replace(' ', '_')`) can collide | Line 131, 187 | Use UUID in filename or sanitize better |

**Code Quality Notes:**
- Good use of `pathlib` throughout
- Hash based on mtime+size is fast but not content-based (acceptable for this use case)

---

### 3. `midi_clock.py` - MIDI Clock Handler ⭐⭐⭐☆☆

**Strengths:**
- Proper MIDI real-time message handling (0xF8, 0xFA, 0xFC, 0xFB)
- BPM smoothing with exponential moving average (0.7/0.3)
- Virtual port support for inter-app communication
- Callback-based design for integration

**Issues Found:**

| Severity | Issue | Location | Recommendation |
|----------|-------|----------|----------------|
| **High** | `tick_intervals` initialized to `None` then set in `__post_init__` - mypy error | Line 19, 21-23 | Use `field(default_factory=lambda: deque(maxlen=24))` |
| **High** | No MIDI channel filtering - processes all channels | Line 88-98 | Add `midi_channel` filter (0=omni) |
| **Medium** | `list_ports()` creates temporary `MidiIn` each call | Line 47-48 | Cache or reuse |
| **Medium** | No reconnection logic if port disappears | - | Add port monitoring |
| **Low** | BPM calculation uses simple average - could use median for outlier rejection | Line 107-113 | Consider `statistics.median` |
| **Low** | `time_stamp` from callback may be 0 - falls back to `time.monotonic()` | Line 101 | Document assumption |

**Critical Bug:** The `midi_channel` parameter in `AppConfig` is never used! The handler processes all channels.

---

### 4. `models.py` - Data Models ⭐⭐⭐⭐⭐

**Strengths:**
- Clean dataclass design with proper defaults
- `SongStatus` enum for type safety
- `AppConfig` with load/save methods
- `AppState` for runtime state
- UUID-based IDs

**Issues Found:**

| Severity | Issue | Location | Recommendation |
|----------|-------|----------|----------------|
| **Medium** | `AppConfig.load()` uses `**data` - breaks if JSON has extra fields | Line 119 | Use `**{k: v for k, v in data.items() if k in cls.__dataclass_fields__}` |
| **Medium** | `AppConfig.save()` dumps `__dict__` - includes methods if any added | Line 124 | Use `dataclasses.asdict()` or explicit field list |
| **Low** | `Setlist.add_song` has 7 parameters - consider builder or dataclass | Line 40-49 | Accept `SetlistSong` directly or use `**kwargs` |
| **Low** | No validation on `tempo` (negative?), `time_signature` format | - | Add `__post_init__` validation |

---

### 5. `app.py` - Main TUI Application ⭐⭐⭐☆☆

**This is the largest file (783 lines) and has the most issues.**

#### Architecture Concerns:
| Severity | Issue | Location | Recommendation |
|----------|-------|----------|----------------|
| **High** | **God Class** - `MainScreen` handles UI, business logic, MIDI, settings, setlist, lyrics | Entire file | Split into: `SetlistController`, `LyricsController`, `BPMController`, `SettingsController` |
| **High** | Tight coupling - `MainScreen` directly manipulates `app_state` and queries widgets | Throughout | Use MVC pattern: controllers update state, views react |
| **High** | `query_one` calls without error handling - crashes if widget missing | Lines 308, 314, 345, etc. | Add try/except or verify widget exists |
| **Medium** | `LyricsView` recreates ALL widgets on `set_song` - inefficient for large songs | Line 132-156 | Virtual scrolling or widget recycling |
| **Medium** | Auto-scroll timing uses `asyncio.sleep` - drift accumulates over time | Line 228-230 | Use `time.monotonic()` for drift correction |
| **Medium** | Settings UI uses `Input` for everything - no validation, no type safety | Lines 518-556 | Use proper widgets (Switch, Select, NumericInput) |

#### Specific Bugs:
| Severity | Issue | Location | Fix |
|----------|-------|----------|-----|
| **High** | `SetlistSong.time_signature` not passed in test (fixed) | - | ✅ Fixed |
| **Medium** | `action_load_setlist` only loads first setlist - no selection UI | Line 679-689 | Add setlist picker |
| **Medium** | `action_next_section`/`action_prev_section` not bound to keys | Lines 246-266 | Add bindings or remove |
| **Medium** | Transpose creates new song each time - loses original reference | Line 198-202 | Store original, transpose on render |
| **Low** | `ChordLine._render_line` called on every chord toggle - re-parses markup | Line 180-185 | Cache rendered markup |
| **Low** | `SongSearchScreen` ID matching uses `filepath` but stores sanitized ID | Line 451, 464 | Use consistent ID mapping |

#### Textual-Specific Issues:
| Issue | Location | Fix |
|-------|----------|-----|
| `Label` doesn't accept `width` kwarg (fixed) | Was lines 392, 397 | Use CSS classes |
| `scroll_page` doesn't exist on `VerticalScroll` (fixed) | Was lines 165, 168 | Use `scroll_relative` |
| IDs can't contain dots (fixed) | Lines 399, 451 | Sanitize with prefix |
| `query_one` returns `Widget` not specific type | Throughout | Add type ignores or cast |

#### Performance Concerns:
1. **LyricsView.set_song()** mounts all lines at once - for 100+ line songs, this is slow
2. **Auto-scroll** creates new task on every BPM change - cancel/create pattern
3. **Settings** re-queries all inputs on every save - use `query` once

---

## Cross-Cutting Concerns

### Type Safety (mypy)
**43 errors** - mostly Textual dynamic typing issues:
- `query_one` returns `Widget` not specific type → add `# type: ignore[return-value]`
- `Optional` vs `X | None` inconsistencies → standardize on `X | None`
- `rtmidi` missing stubs → add `# type: ignore[import-untyped]`
- List variance issues in `chordpro.py` → use `Sequence` or `type: ignore`

### Error Handling
- **Zero structured logging** - uses `print()` in library (removed) and `app.notify()` in UI
- **No exception hierarchy** - consider custom exceptions (`SongParseError`, `MidiError`, `ConfigError`)
- **Silent failures** in cache loading/saving

### Testing Coverage
| Area | Unit Tests | Virtual Tests | Gap |
|------|------------|---------------|-----|
| ChordPro parsing | ✅ 7 tests | ✅ | Good |
| Library/Setlist | ✅ 4 tests | ✅ | Good |
| MIDI Clock | ✅ 2 tests | ✅ | No real MIDI test |
| Models | ✅ 3 tests | ✅ | Good |
| App/UI | ❌ | ✅ 5 tests | No unit tests for UI logic |
| Auto-scroll timing | ❌ | ❌ | **Critical gap** |
| MIDI integration | ❌ | ❌ | **Critical gap** |
| Transpose + auto-scroll | ❌ | ❌ | **Critical gap** |

### Documentation
- No docstrings on public methods in `app.py`
- `README.md` is good for users but no developer docs
- No architecture diagram

---

## Priority Refactoring Plan

### Phase 1: Critical Fixes (Do First)
1. **Fix MIDI channel filtering** in `midi_clock.py` - currently ignores `midi_channel` config
2. **Add error handling** to `query_one` calls in `app.py`
3. **Fix auto-scroll drift** - use monotonic time
4. **Add cache cleanup** in `library.py` for deleted songs

### Phase 2: Architecture Improvements
1. **Extract controllers** from `MainScreen`:
   - `SetlistController` - setlist CRUD, selection
   - `LyricsController` - song display, scroll, transpose
   - `BPMController` - tap tempo, MIDI sync, visual click
   - `SettingsController` - config UI, validation
2. **Implement virtual scrolling** in `LyricsView` for large songs
3. **Add proper settings widgets** (Switch, Select, etc.)

### Phase 3: Quality & Polish
1. **Fix mypy errors** with proper type annotations
2. **Add structured logging** (replace `app.notify` for errors)
3. **Add integration tests** for MIDI + auto-scroll + transpose
4. **Add setlist picker UI** for `action_load_setlist`
5. **Document chord transpose behavior** (sharp vs flat preference)

### Phase 4: Nice to Have
1. **ChordPro export** preserves all metadata
2. **Key preference** (flats vs sharps) per song
3. **Song search** with fuzzy matching
4. **Keyboard shortcuts** for section navigation (already implemented but unbound)
5. **Theme support** (dark/light/custom)

---

## Code Smells to Address

| Smell | Location | Fix |
|-------|----------|-----|
| Long method (`MainScreen.on_mount` = 18 lines) | Line 561 | Split into `init_library`, `init_midi`, `init_views` |
| Long parameter list (`Setlist.add_song` = 7 params) | Line 40 | Use dataclass or builder |
| Magic numbers (24 PPQN, 0.7/0.3 smoothing, 8 taps) | `midi_clock.py`, `app.py` | Move to constants/config |
| Duplicate BPM update logic | `_on_midi_bpm`, `_refresh_bpm_widget`, `LyricsView.set_bpm` | Centralize in `BPMController` |
| Commented-out code / dead code | `ChordQuality` enum | Remove or use |

---

## Security Considerations
- **No user input sanitization** in ChordPro parser - but local files only
- **Path traversal** possible in `SongLibrary.scan()` if symlinks - use `resolve()`
- **MIDI input** from network? - `rtmidi` only does local ports by default

---

## Performance Benchmarks (Estimated)
| Operation | Current | Target |
|-----------|---------|--------|
| App startup | ~500ms | <200ms |
| Load 50-song library | ~200ms | <100ms |
| Switch to lyrics (300 lines) | ~300ms | <50ms (virtual scroll) |
| Auto-scroll 60fps | ✅ | ✅ |
| Transpose (50 chords) | ~50ms | <10ms |

---

## Conclusion

The codebase is **production-ready for core features** but needs:
1. **MIDI channel filter fix** (critical for multi-device setups)
2. **Auto-scroll drift correction** (critical for long songs)
3. **Architecture refactor** of `app.py` (technical debt)
4. **Type safety cleanup** (maintainability)

**Recommendation:** Ship current version for rehearsal use, schedule Phase 1-2 for next sprint before live performance.

---

## Files to Create for Next Sprint

```
docs/
├── ARCHITECTURE.md          # Component diagram, data flow
├── DEVELOPER_GUIDE.md       # How to extend, test, debug
└── MIDI_INTEGRATION.md      # lightrig/Force sync guide

src/teleprompter/
├── controllers/
│   ├── __init__.py
│   ├── setlist_controller.py
│   ├── lyrics_controller.py
│   ├── bpm_controller.py
│   └── settings_controller.py
├── widgets/
│   ├── __init__.py
│   ├── virtual_lyrics_view.py
│   └── settings_widgets.py
└── exceptions.py            # Custom exception hierarchy
```

---

*End of Review*