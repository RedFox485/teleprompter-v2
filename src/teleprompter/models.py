"""
Data models for setlist, app state, and configuration.
"""
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class SongStatus(Enum):
    REHEARSED = "rehearsed"
    WINGING_IT = "winging_it"
    REQUEST = "request"


class PlayState(Enum):
    STOPPED = "stopped"    # Show not started or show over
    PLAYING = "playing"    # Actively scrolling
    PAUSED = "paused"      # Paused mid-song


@dataclass
class SetlistSong:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    song_path: str = ""
    title: str = ""
    artist: str = ""
    key: str = ""
    tempo: int = 120
    time_signature: str = "4/4"
    status: SongStatus = SongStatus.REHEARSED
    transpose: int = 0  # semitones
    added_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Setlist:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Untitled Setlist"
    date: str = field(default_factory=lambda: datetime.now().date().isoformat())
    songs: list[SetlistSong] = field(default_factory=list)
    notes: str = ""

    def add_song(
        self,
        song_path: str,
        song_title: str = "",
        song_artist: str = "",
        song_key: str = "",
        song_tempo: int = 120,
        song_time_signature: str = "4/4",
        status: SongStatus = SongStatus.REHEARSED,
    ) -> SetlistSong:
        entry = SetlistSong(
            song_path=song_path,
            title=song_title,
            artist=song_artist,
            key=song_key,
            tempo=song_tempo,
            time_signature=song_time_signature,
            status=status,
        )
        self.songs.append(entry)
        return entry

    def remove_song(self, song_id: str) -> bool:
        for i, s in enumerate(self.songs):
            if s.id == song_id:
                self.songs.pop(i)
                return True
        return False

    def move_song(self, song_id: str, new_index: int) -> bool:
        for i, s in enumerate(self.songs):
            if s.id == song_id:
                song = self.songs.pop(i)
                self.songs.insert(max(0, min(new_index, len(self.songs))), song)
                return True
        return False


@dataclass
class AppConfig:
    # Display
    font_size: int = 28
    line_spacing: float = 1.4
    chord_color: str = "cyan"
    text_color: str = "white"
    bg_color: str = "black"
    highlight_color: str = "yellow"
    section_color: str = "magenta"

    # Auto-scroll
    auto_scroll_enabled: bool = True
    scroll_speed_factor: float = 0.5  # lines per beat
    scroll_smoothing: bool = True

    # BPM / Metronome
    bpm: int = 120
    time_signature: str = "4/4"
    visual_click: bool = True
    click_flash_duration_ms: int = 100

    # MIDI
    midi_input_port: str = ""
    midi_channel: int = 0  # 0 = omni
    midi_sync_enabled: bool = True

    # Paths
    songs_dir: str = "songs"
    setlists_dir: str = "setlists"
    config_file: str = "config.json"

    # Window
    fullscreen: bool = True
    stay_on_top: bool = True

    # Web server
    web_enabled: bool = True
    web_port: int = 8000

    @classmethod
    def load(cls, path: Path) -> "AppConfig":
        if path.exists():
            with open(path) as f:
                data = json.load(f)
            return cls(**data)
        return cls()

    def save(self, path: Path) -> None:
        with open(path, "w") as f:
            json.dump(self.__dict__, f, indent=2)


@dataclass
class AppState:
    config: AppConfig = field(default_factory=AppConfig)
    current_setlist: Setlist | None = None
    current_song_index: int = -1
    current_line_index: int = 0
    current_section_index: int = 0
    play_state: PlayState = PlayState.STOPPED
    is_fullscreen: bool = True
    show_chords: bool = True
    transpose: int = 0
    bpm: int = 120
    midi_connected: bool = False
    last_midi_bpm: float | None = None