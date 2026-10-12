"""Tests for teleprompter-v2."""
import tempfile
from pathlib import Path

import pytest

from teleprompter.chordpro import (
    Chord,
    load_song,
    parse_chordpro,
)
from teleprompter.library import SetlistManager, SongLibrary
from teleprompter.midi_clock import MidiClockHandler
from teleprompter.models import AppConfig, Setlist, SongStatus


class TestChord:
    def test_parse_simple_chord(self):
        chord = Chord.parse("C")
        assert chord.root == "C"
        assert chord.quality == ""
        assert chord.bass is None

    def test_parse_minor_chord(self):
        chord = Chord.parse("Cm")
        assert chord.root == "C"
        assert chord.quality == "m"

    def test_parse_complex_chord(self):
        chord = Chord.parse("Cmaj7")
        assert chord.root == "C"
        assert chord.quality == "maj7"

    def test_parse_slash_chord(self):
        chord = Chord.parse("C/E")
        assert chord.root == "C"
        assert chord.quality == ""
        assert chord.bass == "E"

    def test_transpose(self):
        chord = Chord.parse("C")
        transposed = chord.transpose(2)
        assert transposed.root == "D"

    def test_transpose_flat(self):
        chord = Chord.parse("Bb")
        transposed = chord.transpose(2)
        assert transposed.root == "C"


class TestChordProParser:
    def test_parse_basic(self):
        content = """{title: Test Song}
{artist: Test Artist}
{key: G}
{tempo: 120}

[C]This is a [F]test [G]line"""
        song = parse_chordpro(content, "test.cho")
        assert song.title == "Test Song"
        assert song.artist == "Test Artist"
        assert song.key == "G"
        assert song.tempo == 120

    def test_parse_sections(self):
        content = """{title: Test}
{section: Verse 1}
Line 1
Line 2
{section: Chorus}
Chorus line"""
        song = parse_chordpro(content, "test.cho")
        assert len(song.sections) == 2
        assert song.sections[0].name == "Verse 1"
        assert song.sections[1].name == "Chorus"

    def test_parse_inline_chords(self):
        content = """{title: Test}
[C]Hello [F]world [G]!"""
        song = parse_chordpro(content, "test.cho")
        line = song.all_lines[0]
        # Segments: "", [C], "Hello ", [F], "world ", [G], "!"
        chords = [seg for seg in line.segments if seg[1] is not None]
        assert len(chords) == 3
        assert chords[0][1].root == "C"
        assert chords[1][1].root == "F"
        assert chords[2][1].root == "G"

    def test_load_song_file(self):
        song = load_song("songs/sweet_home_alabama.cho")
        assert song.title == "Sweet Home Alabama"
        assert song.artist == "Lynyrd Skynyrd"
        assert song.key == "G"
        assert song.tempo == 98

    def test_transpose_song(self):
        song = load_song("songs/sweet_home_alabama.cho")
        transposed = song.transpose(2)
        assert transposed.key == "A"
        # Check chords transposed
        for line in transposed.all_lines:
            for _, chord in line.segments:
                if chord:
                    # Original was in G, now should be in A
                    pass


class TestSongLibrary:
    def test_scan_songs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            songs_dir = Path(tmpdir) / "songs"
            songs_dir.mkdir()
            cache_file = Path(tmpdir) / "cache.json"
            
            # Create a test song
            test_song = """{title: Test Song}
{artist: Test Artist}
{key: C}
{tempo: 100}
[C]Test [F]line"""
            (songs_dir / "test.cho").write_text(test_song)
            
            lib = SongLibrary(songs_dir, cache_file)
            entries = lib.scan()
            assert len(entries) == 1
            assert entries[0].title == "Test Song"
            assert entries[0].artist == "Test Artist"
            assert entries[0].key == "C"
            assert entries[0].tempo == 100

    def test_search(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            songs_dir = Path(tmpdir) / "songs"
            songs_dir.mkdir()
            cache_file = Path(tmpdir) / "cache.json"
            
            (songs_dir / "song1.cho").write_text("{title: Hello World}\n{artist: Artist1}\n[C]Test")
            (songs_dir / "song2.cho").write_text("{title: Goodbye}\n{artist: Artist2}\n[G]Test")
            
            lib = SongLibrary(songs_dir, cache_file)
            lib.scan()
            
            results = lib.search("hello")
            assert len(results) == 1
            assert results[0].title == "Hello World"
            
            results = lib.search("artist1")
            assert len(results) == 1
            assert results[0].title == "Hello World"


class TestSetlistManager:
    def test_save_load_setlist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            setlists_dir = Path(tmpdir) / "setlists"
            sm = SetlistManager(setlists_dir)
            
            sl = Setlist(name="My Setlist")
            sl.add_song("song1.cho", "Song 1", "Artist 1", "C", 100, status=SongStatus.REHEARSED)
            sl.add_song("song2.cho", "Song 2", "Artist 2", "G", 120, status=SongStatus.REQUEST)
            
            path = sm.save(sl)
            assert path.exists()
            
            loaded = sm.load(path)
            assert loaded.name == "My Setlist"
            assert len(loaded.songs) == 2
            assert loaded.songs[0].title == "Song 1"
            assert loaded.songs[1].status == SongStatus.REQUEST


class TestModels:
    def test_app_config_defaults(self):
        config = AppConfig()
        assert config.font_size == 28
        assert config.auto_scroll_enabled is True
        assert config.scroll_speed_factor == 0.5

    def test_app_config_save_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.json"
            config = AppConfig(font_size=32, bpm=140)
            config.save(config_file)
            
            loaded = AppConfig.load(config_file)
            assert loaded.font_size == 32
            assert loaded.bpm == 140

    def test_setlist_operations(self):
        sl = Setlist(name="Test")
        s1 = sl.add_song("song1.cho", "Song 1", "Artist 1", "C", 100)
        s2 = sl.add_song("song2.cho", "Song 2", "Artist 2", "G", 120)
        s3 = sl.add_song("song3.cho", "Song 3", "Artist 3", "D", 90)
        
        assert len(sl.songs) == 3
        
        # Remove middle song
        assert sl.remove_song(s2.id)
        assert len(sl.songs) == 2
        assert sl.songs[0].id == s1.id
        assert sl.songs[1].id == s3.id
        
        # Move song
        sl.add_song("song2.cho", "Song 2", "Artist 2", "G", 120)
        s2_new = sl.songs[-1]
        assert sl.move_song(s2_new.id, 0)
        assert sl.songs[0].id == s2_new.id


class TestMidiClockHandler:
    def test_list_ports(self):
        handler = MidiClockHandler()
        ports = handler.list_ports()
        assert isinstance(ports, list)

    def test_virtual_port(self):
        handler = MidiClockHandler()
        success = handler.open_virtual_port("Test Port")
        assert success
        assert handler.port_name == "Test Port"
        handler.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])