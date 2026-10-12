"""
Teleprompter V2 - Band/Live Karaoke Teleprompter
"""
from .app import TeleprompterApp, main
from .chordpro import Chord, Line, Section, Song, load_song, parse_chordpro, save_song
from .library import SetlistManager, SongLibrary
from .midi_clock import MidiClockHandler
from .models import AppConfig, AppState, Setlist, SetlistSong, SongStatus

__all__ = [
    "TeleprompterApp",
    "main",
    "Song",
    "Chord", 
    "Line",
    "Section",
    "parse_chordpro",
    "load_song",
    "save_song",
    "SongLibrary",
    "SetlistManager",
    "MidiClockHandler",
    "AppConfig",
    "AppState",
    "Setlist",
    "SetlistSong",
    "SongStatus",
]

__version__ = "0.1.0"