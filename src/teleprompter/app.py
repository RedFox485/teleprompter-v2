"""
Main Teleprompter Textual TUI Application.
"""
import asyncio
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.events import Key
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Select,
    Static,
    Switch,
    TabbedContent,
    TabPane,
)

from .chordpro import Line, Song
from .library import SetlistManager, SongCacheEntry, SongLibrary
from .midi_clock import MidiClockHandler
from .models import (
    AppConfig,
    AppState,
    Setlist,
)


class ChordLine(Static):
    """A single line of lyrics with highlighted chords."""
    
    DEFAULT_CSS = """
    ChordLine {
        height: auto;
        min-height: 1;
        padding: 0 2;
    }
    ChordLine .chord {
        color: $primary;
        background: $surface;
        padding: 0 1;
        text-style: bold;
    }
    ChordLine .section {
        color: $accent;
        text-style: bold underline;
    }
    ChordLine .comment {
        color: $text-muted;
        text-style: italic;
    }
    ChordLine.active {
        background: $primary 20%;
    }
    """

    def __init__(self, line: Line, show_chords: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.line = line
        self.show_chords = show_chords
        self._render_line()

    def _render_line(self) -> None:
        if self.line.is_directive:
            if self.line.directive == "comment":
                self.update(f"[comment]{self.line.value}[/comment]")
                self.add_class("comment")
            elif self.line.directive in ("section", "soc", "start_of_chorus", "chorus"):
                self.update(f"[section]── {self.line.value} ──[/section]")
                self.add_class("section")
            else:
                self.update(f"[dim]{{{self.line.directive}: {self.line.value}}}[/dim]")
            return

        parts = []
        for text, chord in self.line.segments:
            if text:
                parts.append(text)
            if chord and self.show_chords:
                parts.append(f"[chord]{chord}[/chord]")
        self.update("".join(parts))


class LyricsView(VerticalScroll):
    """Scrollable lyrics display with auto-scroll support."""
    
    DEFAULT_CSS = """
    LyricsView {
        width: 1fr;
        height: 1fr;
        background: $surface;
        border: solid $primary;
    }
    LyricsView:focus {
        border: double $accent;
    }
    LyricsView ChordLine.active {
        background: $warning 30%;
    }
    """

    BINDINGS = [
        Binding("up", "scroll_up", "Scroll up"),
        Binding("down", "scroll_down", "Scroll down"),
        Binding("pageup", "page_up", "Page up"),
        Binding("pagedown", "page_down", "Page down"),
        Binding("home", "scroll_home", "Top"),
        Binding("end", "scroll_end", "Bottom"),
        Binding("space", "toggle_auto_scroll", "Auto-scroll"),
        Binding("t", "toggle_chords", "Chords"),
        Binding("]", "transpose_up", "Transpose +"),
        Binding("[", "transpose_down", "Transpose -"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.song: Song | None = None
        self.auto_scroll = True
        self.show_chords = True
        self.transpose = 0
        self.current_line = 0
        self.scroll_task: asyncio.Task | None = None
        self.lines_per_beat = 0.5
        self.bpm = 120
        self._line_widgets: list[ChordLine] = []

    def set_song(self, song: Song) -> None:
        self.song = song
        self.current_line = 0
        self._line_widgets.clear()
        self.query("ChordLine").remove()
        
        # Group lines by section for rendering
        for section in song.sections:
            if section.name:
                section_line = Line(
                    segments=[("", None)],
                    is_directive=True,
                    directive="section",
                    value=section.name
                )
                widget = ChordLine(section_line, self.show_chords, classes="section-header")
                self.mount(widget)
                self._line_widgets.append(widget)
            
            for line in section.lines:
                widget = ChordLine(line, self.show_chords)
                self.mount(widget)
                self._line_widgets.append(widget)
        
        self.scroll_home()

    def action_scroll_up(self) -> None:
        self.scroll_relative(y=-1, animate=True)

    def action_scroll_down(self) -> None:
        self.scroll_relative(y=1, animate=True)

    def action_page_up(self) -> None:
        self.scroll_relative(y=-20, animate=True)

    def action_page_down(self) -> None:
        self.scroll_relative(y=20, animate=True)

    def action_scroll_home(self) -> None:
        self.scroll_home(animate=True)

    def action_scroll_end(self) -> None:
        self.scroll_end(animate=True)

    def action_toggle_auto_scroll(self) -> None:
        self.auto_scroll = not self.auto_scroll
        self.app.notify(f"Auto-scroll: {'ON' if self.auto_scroll else 'OFF'}")

    def action_toggle_chords(self) -> None:
        self.show_chords = not self.show_chords
        for widget in self._line_widgets:
            if not widget.line.is_directive:
                widget.show_chords = self.show_chords
                widget._render_line()
        self.app.notify(f"Chords: {'ON' if self.show_chords else 'OFF'}")

    def action_transpose_up(self) -> None:
        self.transpose += 1
        self._apply_transpose()
        self.app.notify(f"Transpose: +{self.transpose}")

    def action_transpose_down(self) -> None:
        self.transpose -= 1
        self._apply_transpose()
        self.app.notify(f"Transpose: {self.transpose}")

    def _apply_transpose(self) -> None:
        if not self.song:
            return
        transposed = self.song.transpose(self.transpose)
        self.set_song(transposed)

    def set_bpm(self, bpm: int) -> None:
        self.bpm = bpm
        if self.auto_scroll and self.scroll_task:
            self.scroll_task.cancel()
            self.scroll_task = asyncio.create_task(self._auto_scroll_loop())

    def start_auto_scroll(self) -> None:
        if self.auto_scroll and not self.scroll_task:
            self.scroll_task = asyncio.create_task(self._auto_scroll_loop())

    def stop_auto_scroll(self) -> None:
        if self.scroll_task:
            self.scroll_task.cancel()
            self.scroll_task = None

    async def _auto_scroll_loop(self) -> None:
        """Auto-scroll based on BPM."""
        try:
            while self.auto_scroll and self.song:
                # Calculate delay: lines per beat = scroll_speed_factor
                # beats per second = bpm / 60
                # lines per second = (bpm / 60) * lines_per_beat
                # seconds per line = 1 / lines_per_second
                lines_per_second = (self.bpm / 60.0) * self.lines_per_beat
                delay = 1.0 / lines_per_second if lines_per_second > 0 else 1.0

                await asyncio.sleep(delay)
                if self.auto_scroll:
                    self.current_line = min(self.current_line + 1, len(self._line_widgets) - 1)
                    self._highlight_current_line()
                    # Smooth scroll to keep current line visible
                    self.scroll_to_widget(self._line_widgets[self.current_line], animate=True)
        except asyncio.CancelledError:
            pass

    def _highlight_current_line(self) -> None:
        for i, widget in enumerate(self._line_widgets):
            if i == self.current_line:
                widget.add_class("active")
            else:
                widget.remove_class("active")

    def action_next_section(self) -> None:
        """Jump to next section."""
        if not self.song:
            return
        for _i, section in enumerate(self.song.sections):
            if section.start_line_idx > self.current_line:
                self.current_line = section.start_line_idx
                self._highlight_current_line()
                self.scroll_to_widget(self._line_widgets[self.current_line], animate=True)
                break

    def action_prev_section(self) -> None:
        """Jump to previous section."""
        if not self.song:
            return
        for i in range(len(self.song.sections) - 1, -1, -1):
            if self.song.sections[i].start_line_idx < self.current_line:
                self.current_line = self.song.sections[i].start_line_idx
                self._highlight_current_line()
                self.scroll_to_widget(self._line_widgets[self.current_line], animate=True)
                break


class BPMWidget(Static):
    """Large BPM display with tap tempo."""
    
    DEFAULT_CSS = """
    BPMWidget {
        width: 100%;
        height: 12;
        content-align: center middle;
        background: $surface;
        border: solid $primary;
    }
    BPMWidget .bpm-value {
        text-style: bold;
        color: $accent;
    }
    BPMWidget .tap-hint {
        color: $text-muted;
        text-style: italic;
    }
    BPMWidget.flash {
        background: $warning;
    }
    """
    
    BINDINGS = [
        Binding("space", "tap", "Tap tempo"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bpm = 120
        self.time_sig = "4/4"
        self.tap_times = []
        self.flash_task = None
        self.visual_click = True

    def action_tap(self) -> None:
        """Handle Space key for tap tempo."""
        self.tap()

    def compose(self) -> ComposeResult:
        yield Label(str(self.bpm), classes="bpm-value", id="bpm-value")
        hint = f"{self.time_sig}  •  Tap: SPACE  •  Auto: MIDI"
        yield Label(hint, classes="tap-hint", id="tap-hint")

    def set_bpm(self, bpm: float) -> None:
        self.bpm = int(round(bpm))
        self.query_one("#bpm-value").update(str(self.bpm))
        if self.visual_click:
            self._flash()

    def set_time_signature(self, sig: str) -> None:
        self.time_sig = sig
        self.query_one("#tap-hint").update(f"{self.time_sig}  •  Tap: SPACE  •  Auto: MIDI")

    def tap(self) -> None:
        import time
        now = time.monotonic()
        self.tap_times.append(now)
        # Keep last 8 taps
        if len(self.tap_times) > 8:
            self.tap_times = self.tap_times[-8:]
        if len(self.tap_times) >= 2:
            times = self.tap_times
            intervals = [times[i] - times[i - 1] for i in range(1, len(times))]
            avg_interval = sum(intervals) / len(intervals)
            bpm = 60.0 / avg_interval
            self.set_bpm(bpm)

    def _flash(self) -> None:
        if self.flash_task:
            self.flash_task.cancel()
        self.add_class("flash")
        
        async def unflash():
            await asyncio.sleep(0.1)
            self.remove_class("flash")
        
        self.flash_task = asyncio.create_task(unflash())

    def set_midi_connected(self, connected: bool, bpm: float = None) -> None:
        if connected:
            display_bpm = int(bpm or self.bpm)
            msg = f"{self.time_sig}  •  MIDI SYNC @ {display_bpm} BPM"
            self.query_one("#tap-hint").update(msg)
        else:
            msg = f"{self.time_sig}  •  Tap: SPACE  •  Auto: MIDI"
            self.query_one("#tap-hint").update(msg)


class SetlistView(ListView):
    """Setlist management view."""
    
    DEFAULT_CSS = """
    SetlistView {
        width: 1fr;
        height: 1fr;
        background: $surface;
        border: solid $primary;
    }
    SetlistView ListItem {
        height: 3;
        padding: 0 2;
    }
    SetlistView ListItem:hover {
        background: $primary 20%;
    }
    SetlistView ListItem.-highlight {
        background: $accent 30%;
    }
    SetlistView .song-title {
        text-style: bold;
    }
    SetlistView .song-meta {
        color: $text-muted;
    }
    SetlistView .song-number {
        width: 4;
        color: $text-muted;
    }
    SetlistView .song-status {
        width: 16;
        text-align: right;
    }
    SetlistView .status-rehearsed { color: $success; }
    SetlistView .status-winging_it { color: $warning; }
    SetlistView .status-request { color: $error; }
    """

    def __init__(self, setlist: Setlist, **kwargs):
        super().__init__(**kwargs)
        self.setlist = setlist
        self._populate_generation = 0
        self._populate()

    def _populate(self) -> None:
        # Use clear() to properly remove all children
        self.clear()
        # Increment generation counter to ensure unique IDs across re-populates
        self._populate_generation += 1
        
        for i, song in enumerate(self.setlist.songs):
            status_class = f"status-{song.status.value}"
            meta = f"{song.artist}  •  {song.key}  •  {song.tempo} BPM"
            status_text = song.status.value.replace("_", " ").title()
            # Include generation and index to ensure unique IDs in test context
            safe_id = f"s{self._populate_generation}_{i}_{song.id}"
            item = ListItem(
                Horizontal(
                    Label(f"{i+1}. ", classes="song-number"),
                    Vertical(
                        Label(song.title or "Unknown", classes="song-title"),
                        Label(meta, classes="song-meta"),
                    ),
                    Label(status_text, classes=f"{status_class} song-status"),
                ),
                id=safe_id,
            )
            self.append(item)


DEFAULT_CSS = """
    #search-container ListView ListItem {
        height: 3;
        padding: 0 2;
    }
    #search-container ListView ListItem.-highlight {
        background: $accent 30%;
    }
    #search-container .song-title {
        text-style: bold;
    }
    #search-container .song-meta {
        color: $text-muted;
    }
    """


class SongSearchScreen(Screen):
    """Search and add songs to setlist."""
    
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "select", "Add to setlist"),
        Binding("down", "focus_results", "Results"),
        Binding("up", "focus_search", "Search"),
    ]

    def __init__(self, library: SongLibrary, on_select, **kwargs):
        super().__init__(**kwargs)
        self.library = library
        self.on_select = on_select
        self.search_results: list[SongCacheEntry] = []
        self._search_counter = 0

    def compose(self) -> ComposeResult:
        yield Container(
            Label("Search Songs", classes="screen-title"),
            Input(placeholder="Search by title or artist...", id="search-input"),
            ListView(id="results-list"),
            id="search-container",
        )

    def on_mount(self) -> None:
        self.query_one("#search-input").focus()
        # Populate initial search results (up to 8 songs)
        self.search_results = self.library.get_all_entries()[:8]
        self._update_results_list()
        # Auto-select first item when results list gets focus
        # Use a timer to wait for composition to complete
        def set_initial_focus():
            results_list = self.query_one("#results-list", ListView)
            if results_list.index is None and len(results_list.children) > 0:
                results_list.index = 0
        self.set_timer(0.01, set_initial_focus)

    def _update_results_list(self) -> None:
        """Update the results list with current search_results."""
        results_list = self.query_one("#results-list", ListView)
        # Clear existing items
        for child in list(results_list.children):
            child.remove()
        for _idx, entry in enumerate(self.search_results):
            self._search_counter += 1
            base_id = entry.filepath.replace(".", "_").replace("/", "_")
            safe_id = f"{base_id}_{self._search_counter}"
            meta = f"{entry.artist}  •  {entry.key}  •  {entry.tempo} BPM"
            item = ListItem(
                Horizontal(
                    Label(entry.title, classes="song-title"),
                    Label(meta, classes="song-meta"),
                ),
                id=safe_id,
            )
            item.original_filepath = entry.filepath
            results_list.append(item)

    def on_key(self, event: Key) -> None:
        """Handle key events at screen level for focus management."""
        # Allow up arrow to escape from results list
        if event.key == "up":
            results_list = self.query_one("#results-list", ListView)
            if results_list.has_focus and results_list.index == 0:
                # Move focus back to search input
                event.prevent_default()
                event.stop()
                self.action_focus_search()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search-input":
            query = event.value.strip()
            if query:
                self.search_results = self.library.search(query, max_results=8)
            else:
                self.search_results = self.library.get_all_entries()[:8]
            self._update_results_list()

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        if self.on_select:
            # Use stored original filepath
            filepath = event.item.original_filepath
            entry = next((e for e in self.search_results if e.filepath == filepath), None)
            if entry:
                await self.on_select(entry)
                # Use call_later to pop screen after event handler completes
                self.app.call_later(self.app.pop_screen)

    def action_select(self) -> None:
        """Handle Enter key to select highlighted item."""
        results_list = self.query_one("#results-list", ListView)
        if results_list.highlighted_child:
            # Simulate selection event with proper index
            selected = ListView.Selected(
                results_list, results_list.highlighted_child, results_list.index
            )
            self.on_list_view_selected(selected)

    def action_focus_results(self) -> None:
        """Move focus from search input to results list."""
        results_list = self.query_one("#results-list", ListView)
        results_list.focus()
        # Auto-select first item if none selected
        if results_list.index is None and len(results_list.children) > 0:
            results_list.index = 0

    def action_focus_search(self) -> None:
        """Move focus from results list back to search input."""
        search_input = self.query_one("#search-input", Input)
        search_input.focus()
        # Move cursor to end
        search_input.cursor_position = len(search_input.value)

    def action_cancel(self) -> None:
        """Handle Escape key to cancel and return to main screen."""
        self.app.pop_screen()


class MainScreen(Screen):
    """Main application screen with tabs."""
    
    BINDINGS = [
        Binding("f1", "tab('tab-setlist')", "Setlist"),
        Binding("f2", "tab('tab-lyrics')", "Lyrics"),
        Binding("f3", "tab('tab-bpm')", "BPM"),
        Binding("f4", "tab('tab-settings')", "Settings"),
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+s", "save_setlist", "Save"),
        Binding("ctrl+o", "load_setlist", "Load"),
        Binding("a", "add_song", "Add Song"),
        Binding("delete", "remove_song", "Remove"),
        Binding("space", "tap_tempo", "Tap Tempo"),
    ]

    def action_tap_tempo(self) -> None:
        """Handle Space key for tap tempo on BPM tab."""
        tabs = self.query_one("#main-tabs", TabbedContent)
        if tabs.active == "tab-bpm":
            bpm = self.query_one("#bpm-widget", BPMWidget)
            bpm.tap()

    def __init__(self, app_state: AppState, **kwargs):
        super().__init__(**kwargs)
        self.app_state = app_state
        self.library = SongLibrary(
            Path(app_state.config.songs_dir),
            Path(app_state.config.config_file).parent / "song_cache.json"
        )
        self.setlist_manager = SetlistManager(Path(app_state.config.setlists_dir))
        self.midi_handler = MidiClockHandler(
            on_bpm_change=self._on_midi_bpm,
            on_start=self._on_midi_start,
            on_stop=self._on_midi_stop,
            midi_channel=self.app_state.config.midi_channel,
        )

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(id="main-tabs"):
            with TabPane("Setlist (F1)", id="tab-setlist"):
                yield SetlistView(self.app_state.current_setlist or Setlist(), id="setlist-view")
            with TabPane("Lyrics (F2)", id="tab-lyrics"):
                yield LyricsView(id="lyrics-view")
            with TabPane("BPM (F3)", id="tab-bpm"):
                yield BPMWidget(id="bpm-widget")
            with TabPane("Settings (F4)", id="tab-settings"):
                yield self._build_settings()
        yield Footer()

    def _build_settings(self) -> Container:
        config = self.app_state.config
        
        # Color options for Select widgets
        color_options = [
            ("White", "White"),
            ("Black", "Black"),
            ("Red", "Red"),
            ("Green", "Green"),
            ("Blue", "Blue"),
            ("Yellow", "Yellow"),
            ("Cyan", "Cyan"),
            ("Magenta", "Magenta"),
            ("Gray", "Gray"),
            ("Bright White", "Bright White"),
            ("Bright Red", "Bright Red"),
            ("Bright Green", "Bright Green"),
            ("Bright Blue", "Bright Blue"),
            ("Bright Yellow", "Bright Yellow"),
            ("Bright Cyan", "Bright Cyan"),
            ("Bright Magenta", "Bright Magenta"),
        ]
        
        # Map config color names to Select values (capitalized)
        color_map = {
            "white": "White", "black": "Black", "red": "Red", "green": "Green",
            "blue": "Blue", "yellow": "Yellow", "cyan": "Cyan", "magenta": "Magenta",
            "gray": "Gray", "bright_white": "Bright White", "bright_red": "Bright Red",
            "bright_green": "Bright Green", "bright_blue": "Bright Blue",
            "bright_yellow": "Bright Yellow", "bright_cyan": "Bright Cyan",
            "bright_magenta": "Bright Magenta",
        }
        chord_color_val = color_map.get(config.chord_color, config.chord_color)
        text_color_val = color_map.get(config.text_color, config.text_color)
        bg_color_val = color_map.get(config.bg_color, config.bg_color)
        
        return Container(
            Label("Settings", classes="screen-title"),
            Vertical(
                Label("Display"),
                Input(value=str(config.font_size), placeholder="Font size (pt)", id="font-size"),
                Label("Colors"),
                Select(
                    options=color_options,
                    value=chord_color_val,
                    id="chord-color",
                    allow_blank=False,
                    prompt="Chord color",
                ),
                Select(
                    options=color_options,
                    value=text_color_val,
                    id="text-color",
                    allow_blank=False,
                    prompt="Text color",
                ),
                Select(
                    options=color_options,
                    value=bg_color_val,
                    id="bg-color",
                    allow_blank=False,
                    prompt="Background color",
                ),
                Label("Auto-scroll"),
                Switch(
                    value=config.auto_scroll_enabled,
                    id="auto-scroll",
                ),
                Input(
                    value=str(config.scroll_speed_factor),
                    placeholder="Scroll speed factor (e.g. 0.5)",
                    id="scroll-speed",
                ),
                Label("MIDI"),
                Input(
                    value=config.midi_input_port,
                    placeholder="MIDI input port name",
                    id="midi-port",
                ),
                Input(
                    value=str(config.midi_channel),
                    placeholder="MIDI channel (0=omni, 1-16)",
                    id="midi-channel",
                ),
                Button("Scan MIDI Ports", id="scan-midi", variant="primary"),
                Label("Paths"),
                Input(
                    value=config.songs_dir,
                    placeholder="Songs directory",
                    id="songs-dir",
                ),
                Input(
                    value=config.setlists_dir,
                    placeholder="Setlists directory",
                    id="setlists-dir",
                ),
                Button("Save Settings", id="save-settings", variant="success"),
            ),
            id="settings-container",
        )

    async def on_mount(self) -> None:
        # Load songs library
        self.library.scan()
        
        # Load or create default setlist
        if not self.app_state.current_setlist:
            self.app_state.current_setlist = Setlist(name="Default")
        
        # Connect MIDI if configured
        if self.app_state.config.midi_input_port:
            self.midi_handler.open_port(self.app_state.config.midi_input_port)
            self.app_state.midi_connected = True
        
        # Update views
        await self._refresh_setlist_view()
        self._refresh_lyrics_view()
        self._refresh_bpm_widget()

    async def _refresh_setlist_view(self) -> None:
        view = self.query_one("#setlist-view", SetlistView)
        view.setlist = self.app_state.current_setlist
        view._populate()

    def _refresh_lyrics_view(self) -> None:
        view = self.query_one("#lyrics-view", LyricsView)
        if self.app_state.current_setlist and self.app_state.current_song_index >= 0:
            song_entry = self.app_state.current_setlist.songs[self.app_state.current_song_index]
            song = self.library.get_song(song_entry.song_path)
            if song:
                if song_entry.transpose:
                    song = song.transpose(song_entry.transpose)
                view.set_song(song)
                view.set_bpm(song_entry.tempo)
                view.auto_scroll = self.app_state.config.auto_scroll_enabled
                view.lines_per_beat = self.app_state.config.scroll_speed_factor
                view.start_auto_scroll()

    def _refresh_bpm_widget(self) -> None:
        widget = self.query_one("#bpm-widget", BPMWidget)
        if self.app_state.current_setlist and self.app_state.current_song_index >= 0:
            song_entry = self.app_state.current_setlist.songs[self.app_state.current_song_index]
            widget.set_bpm(song_entry.tempo)
            widget.set_time_signature(song_entry.time_signature or "4/4")
        widget.set_midi_connected(self.app_state.midi_connected, self.app_state.last_midi_bpm)

    def _on_midi_bpm(self, bpm: float) -> None:
        self.app_state.last_midi_bpm = bpm
        widget = self.query_one("#bpm-widget", BPMWidget)
        widget.set_midi_connected(True, bpm)
        # Also update lyrics view BPM
        lyrics = self.query_one("#lyrics-view", LyricsView)
        lyrics.set_bpm(int(bpm))

    def _on_midi_start(self) -> None:
        lyrics = self.query_one("#lyrics-view", LyricsView)
        lyrics.auto_scroll = True
        lyrics.start_auto_scroll()

    def _on_midi_stop(self) -> None:
        lyrics = self.query_one("#lyrics-view", LyricsView)
        lyrics.stop_auto_scroll()

    def action_tab(self, tab_id: str) -> None:
        tabs = self.query_one("#main-tabs", TabbedContent)
        tabs.active = tab_id

    def action_add_song(self) -> None:
        self.app.push_screen(SongSearchScreen(self.library, self._on_song_selected))

    async def _on_song_selected(self, entry: SongCacheEntry) -> None:
        if not self.app_state.current_setlist:
            self.app_state.current_setlist = Setlist(name="Default")
        song = self.library.get_song(entry.filepath)
        if song:
            self.app_state.current_setlist.add_song(
                song_path=entry.filepath,
                song_title=song.title,
                song_artist=song.artist,
                song_key=song.key,
                song_tempo=song.tempo,
                song_time_signature=song.time_signature,
            )
            # Select the newly added song
            self.app_state.current_song_index = len(self.app_state.current_setlist.songs) - 1
            await self._refresh_setlist_view()
            self._refresh_lyrics_view()
            self._refresh_bpm_widget()
            self.app.notify(f"Added: {song.title}")

    async def action_remove_song(self) -> None:
        setlist_view = self.query_one("#setlist-view", SetlistView)
        highlighted = setlist_view.highlighted_child
        if highlighted and highlighted.id:
            song_id = highlighted.id
            # ID format: s{generation}_{index}_{uuid}
            if song_id.startswith("s"):
                # Split by underscore and get the last part (the UUID)
                parts = song_id.split("_")
                if len(parts) >= 3:
                    song_id = parts[2]
            current_setlist = self.app_state.current_setlist
            if current_setlist and current_setlist.remove_song(song_id):
                await self._refresh_setlist_view()
                self.app.notify("Song removed")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id == "setlist-view" and event.item.id:
            song_id = event.item.id
            # ID format: s{generation}_{index}_{uuid}
            if song_id.startswith("s"):
                parts = song_id.split("_")
                if len(parts) >= 3:
                    song_id = parts[2]
            current_setlist = self.app_state.current_setlist
            if current_setlist:
                for i, song in enumerate(current_setlist.songs):
                    if song.id == song_id:
                        self.app_state.current_song_index = i
                        self._refresh_lyrics_view()
                        self._refresh_bpm_widget()
                        # Switch to lyrics tab
                        self.action_tab("tab-lyrics")
                        break

    def action_save_setlist(self) -> None:
        if self.app_state.current_setlist:
            path = self.setlist_manager.save(self.app_state.current_setlist)
            self.app.notify(f"Saved: {path.name}")

    async def action_load_setlist(self) -> None:
        # Simple: load first available
        setlists = self.setlist_manager.list_setlists()
        if setlists:
            loaded = self.setlist_manager.load(setlists[0])
            self.app_state.current_setlist = loaded
            self.app_state.current_song_index = 0
            await self._refresh_setlist_view()
            self._refresh_lyrics_view()
            self._refresh_bpm_widget()
            self.app.notify(f"Loaded: {loaded.name}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-settings":
            self._save_settings()
        elif event.button.id == "scan-midi":
            self._scan_midi_ports()

    def _save_settings(self) -> None:
        config = self.app_state.config
        config.font_size = int(self.query_one("#font-size", Input).value or config.font_size)
        
        # Convert capitalized color names back to lowercase for config
        color_reverse_map = {
            "White": "white", "Black": "black", "Red": "red", "Green": "green",
            "Blue": "blue", "Yellow": "yellow", "Cyan": "cyan", "Magenta": "magenta",
            "Gray": "gray", "Bright White": "bright_white", "Bright Red": "bright_red",
            "Bright Green": "bright_green", "Bright Blue": "bright_blue",
            "Bright Yellow": "bright_yellow", "Bright Cyan": "bright_cyan",
            "Bright Magenta": "bright_magenta",
        }
        
        chord_sel = self.query_one("#chord-color", Select)
        text_sel = self.query_one("#text-color", Select)
        bg_sel = self.query_one("#bg-color", Select)
        
        config.chord_color = color_reverse_map.get(chord_sel.value, config.chord_color)
        config.text_color = color_reverse_map.get(text_sel.value, config.text_color)
        config.bg_color = color_reverse_map.get(bg_sel.value, config.bg_color)
        config.auto_scroll_enabled = self.query_one("#auto-scroll", Switch).value
        speed_val = self.query_one("#scroll-speed", Input).value
        config.scroll_speed_factor = float(speed_val or config.scroll_speed_factor)
        config.midi_input_port = (self.query_one("#midi-port", Input).value
                                   or config.midi_input_port)
        config.midi_channel = int(
            self.query_one("#midi-channel", Input).value or config.midi_channel)
        config.songs_dir = (self.query_one("#songs-dir", Input).value
                             or config.songs_dir)
        config.setlists_dir = (self.query_one("#setlists-dir", Input).value
                                or config.setlists_dir)
        
        config.save(Path(config.config_file))
        self.app.notify("Settings saved")

    def _scan_midi_ports(self) -> None:
        ports = self.midi_handler.list_ports()
        if ports:
            self.query_one("#midi-port").placeholder = ", ".join(ports[:3])
            self.app.notify(f"Found {len(ports)} MIDI ports")
        else:
            self.app.notify("No MIDI ports found")


class TeleprompterApp(App):
    """Main Teleprompter Application."""
    
    CSS = """
    Screen {
        background: $surface;
    }
    .screen-title {
        text-style: bold;
        padding: 1 2;
        color: $accent;
    }
    #search-container {
        width: 80%;
        max-height: 80%;
        border: solid $primary;
        padding: 1;
    }
    #search-container ListView {
        max-height: 70%;
        overflow-y: auto;
    }
    #search-container ListView ListItem {
        height: auto;
        min-height: 3;
    }
    #search-container ListView ListItem > Horizontal {
        height: auto;
    }
    #settings-container {
        width: 80%;
        max-height: 80%;
        padding: 1;
        overflow-y: auto;
        background: $surface;
        border: solid $primary;
    }
    #settings-container > Vertical {
        height: auto;
        min-height: 100%;
    }
    #settings-container Label {
        padding-top: 1;
    }
    #settings-container Input {
        width: 100%;
    }
    TabbedContent {
        height: 1fr;
    }
    TabPane {
        height: 1fr;
        overflow-y: auto;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        config_path = Path("config.json")
        self.app_state = AppState(config=AppConfig.load(config_path))
        self.config_path = config_path

    def on_mount(self) -> None:
        self.push_screen(MainScreen(self.app_state))

    def on_unmount(self) -> None:
        self.app_state.config.save(self.config_path)


def main():
    app = TeleprompterApp()
    app.run()


if __name__ == "__main__":
    main()