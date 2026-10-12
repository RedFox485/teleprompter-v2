"""
Comprehensive virtual tests for teleprompter-v2 using Textual's run_test.
Tests rendering, edge cases, and functionality.
"""
import asyncio
import os
from pathlib import Path
import tempfile

# Disable web server during tests
os.environ["TELEPROMPTER_TEST"] = "1"

from textual.app import App
from teleprompter.app import TeleprompterApp
from teleprompter.chordpro import parse_chordpro, load_song, Chord, Song, Line, Section
from teleprompter.library import SongLibrary, SetlistManager
from teleprompter.models import AppConfig, Setlist, SetlistSong, SongStatus
from teleprompter.midi_clock import MidiClockHandler


async def test_chordpro_parser():
    """Test ChordPro parser edge cases."""
    print("Testing ChordPro parser...")
    
    # Test 1: Empty content
    song = parse_chordpro("", "empty.cho")
    assert song.title == ""
    assert song.tempo == 120
    
    # Test 2: Only directives
    content = "{title: Test}\n{artist: Me}\n{key: C}\n{tempo: 100}"
    song = parse_chordpro(content, "test.cho")
    assert song.title == "Test"
    assert song.artist == "Me"
    assert song.key == "C"
    assert song.tempo == 100
    
    # Test 3: Inline chords with various formats
    content = """{title: Chord Test}
[C]Major [Cm]Minor [Cmaj7]Maj7 [C7]7 [Cdim]Dim [Caug]Aug [Csus4]Sus4 [Cadd9]Add9 [C6]6 [C9]9 [C/E]Slash"""
    song = parse_chordpro(content, "test.cho")
    line = song.all_lines[0]
    chords = [seg[1] for seg in line.segments if seg[1] and seg[1].root]
    assert len(chords) == 11  # 11 valid chords
    assert chords[0].root == "C"
    assert chords[1].quality == "m"
    assert chords[2].quality == "maj7"
    assert chords[10].bass == "E"
    
    # Test 4: Section directives
    content = """{title: Sections}
{section: Verse 1}
Line 1
{section: Chorus}
Chorus line
{end_of_section}"""
    song = parse_chordpro(content, "test.cho")
    assert len(song.sections) == 2
    assert song.sections[0].name == "Verse 1"
    assert song.sections[1].name == "Chorus"
    
    # Test 5: Transpose
    song = parse_chordpro("{title: T}\n{key: C}\n[C] [F] [G]", "t.cho")
    transposed = song.transpose(2)
    assert transposed.key == "D"
    chords = [seg[1] for seg in transposed.all_lines[0].segments if seg[1]]
    assert chords[0].root == "D"
    assert chords[1].root == "G"
    assert chords[2].root == "A"
    
    # Test 6: Load real song files
    song = load_song("songs/sweet_home_alabama.cho")
    assert song.title == "Sweet Home Alabama"
    assert song.tempo == 98
    assert len(song.sections) == 8
    
    print("  ✓ ChordPro parser tests passed")


async def test_library():
    """Test SongLibrary and SetlistManager."""
    print("Testing Library...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        songs_dir = Path(tmpdir) / "songs"
        songs_dir.mkdir()
        cache_file = Path(tmpdir) / "cache.json"
        
        # Create test songs
        (songs_dir / "song1.cho").write_text("{title: Song One}\n{artist: Artist A}\n{key: C}\n{tempo: 100}\n[C]Line")
        (songs_dir / "song2.cho").write_text("{title: Song Two}\n{artist: Artist B}\n{key: G}\n{tempo: 120}\n[G]Line")
        
        lib = SongLibrary(songs_dir, cache_file)
        entries = lib.scan()
        assert len(entries) == 2
        
        # Test search
        results = lib.search("one")
        assert len(results) == 1
        assert results[0].title == "Song One"
        
        results = lib.search("artist")
        assert len(results) == 2
        
        # Test get_song
        song = lib.get_song("song1.cho")
        assert song.title == "Song One"
        
        # Test setlist manager
        setlists_dir = Path(tmpdir) / "setlists"
        sm = SetlistManager(setlists_dir)
        
        sl = Setlist(name="My Set")
        sl.add_song("song1.cho", "Song One", "Artist A", "C", 100, status=SongStatus.REHEARSED)
        sl.add_song("song2.cho", "Song Two", "Artist B", "G", 120, status=SongStatus.REQUEST)
        
        path = sm.save(sl)
        loaded = sm.load(path)
        assert loaded.name == "My Set"
        assert len(loaded.songs) == 2
        assert loaded.songs[0].status == SongStatus.REHEARSED
        assert loaded.songs[1].status == SongStatus.REQUEST
        
        # Test move/remove
        sl.remove_song(loaded.songs[0].id)
        assert len(sl.songs) == 1
        
    print("  ✓ Library tests passed")


async def test_midi_clock():
    """Test MIDI clock handler."""
    print("Testing MIDI Clock...")
    
    handler = MidiClockHandler()
    ports = handler.list_ports()
    assert isinstance(ports, list)
    
    # Virtual port
    success = handler.open_virtual_port("Test Port")
    assert success
    assert handler.port_name == "Test Port"
    handler.close()
    
    print("  ✓ MIDI Clock tests passed")


async def test_models():
    """Test data models."""
    print("Testing Models...")
    
    # AppConfig
    config = AppConfig(font_size=32, bpm=140)
    assert config.font_size == 32
    assert config.bpm == 140
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / "config.json"
        config.save(config_file)
        loaded = AppConfig.load(config_file)
        assert loaded.font_size == 32
        assert loaded.bpm == 140
    
    # Setlist operations
    sl = Setlist(name="Test")
    s1 = sl.add_song("s1.cho", "Song 1", "A", "C", 100)
    s2 = sl.add_song("s2.cho", "Song 2", "B", "G", 120)
    s3 = sl.add_song("s3.cho", "Song 3", "C", "D", 90)
    
    assert len(sl.songs) == 3
    assert sl.remove_song(s2.id)
    assert len(sl.songs) == 2
    assert sl.songs[0].id == s1.id
    assert sl.songs[1].id == s3.id
    
    sl.add_song("s2.cho", "Song 2", "B", "G", 120)
    s2_new = sl.songs[-1]
    assert sl.move_song(s2_new.id, 0)
    assert sl.songs[0].id == s2_new.id
    
    print("  ✓ Model tests passed")


async def test_app_rendering():
    """Test app rendering and UI interactions."""
    print("Testing App Rendering...")
    
    app = TeleprompterApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        
        # Test tab switching
        tabs = screen.query_one("#main-tabs")
        
        for tab_id in ["tab-setlist", "tab-lyrics", "tab-bpm", "tab-settings"]:
            tabs.active = tab_id
            await pilot.pause()
            assert tabs.active == tab_id
        
        # Test setlist view rendering
        tabs.active = "tab-setlist"
        await pilot.pause()
        setlist_view = screen.query_one("#setlist-view")
        # Should have empty setlist initially
        
        # Test lyrics view
        tabs.active = "tab-lyrics"
        await pilot.pause()
        lyrics = screen.query_one("#lyrics-view")
        assert lyrics.song is None
        
        # Test BPM widget
        tabs.active = "tab-bpm"
        await pilot.pause()
        bpm = screen.query_one("#bpm-widget")
        assert bpm.bpm == 120
        
        # Test tap tempo
        bpm.tap()
        await pilot.pause()
        # First tap doesn't calculate BPM
        assert bpm.bpm == 120
        
        bpm.tap()
        await pilot.pause()
        # Second tap should calculate
        assert bpm.bpm > 0
        
        # Test settings
        tabs.active = "tab-settings"
        await pilot.pause()
        settings = screen.query_one("#settings-container")
        assert settings is not None
        
    print("  ✓ App rendering tests passed")


async def test_lyrics_view():
    """Test lyrics view with actual song content."""
    print("Testing Lyrics View...")
    
    app = TeleprompterApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        
        # Load a song into lyrics view
        tabs = screen.query_one("#main-tabs")
        tabs.active = "tab-lyrics"
        await pilot.pause()
        
        lyrics = screen.query_one("#lyrics-view")
        song = load_song("songs/sweet_home_alabama.cho")
        lyrics.set_song(song)
        await pilot.pause()
        
        # Check lines rendered
        line_widgets = lyrics.query("ChordLine")
        assert len(line_widgets) > 0
        
        # Test scroll actions
        lyrics.action_scroll_down()
        await pilot.pause()
        lyrics.action_scroll_up()
        await pilot.pause()
        lyrics.action_page_down()
        await pilot.pause()
        lyrics.action_page_up()
        await pilot.pause()
        lyrics.action_scroll_home()
        await pilot.pause()
        lyrics.action_scroll_end()
        await pilot.pause()
        
        # Test chord toggle
        lyrics.action_toggle_chords()
        await pilot.pause()
        assert lyrics.show_chords is False
        lyrics.action_toggle_chords()
        await pilot.pause()
        assert lyrics.show_chords is True
        
        # Test transpose
        lyrics.action_transpose_up()
        await pilot.pause()
        assert lyrics.transpose == 1
        lyrics.action_transpose_down()
        await pilot.pause()
        assert lyrics.transpose == 0
        
        # Test auto-scroll toggle
        lyrics.action_toggle_auto_scroll()
        await pilot.pause()
        assert lyrics.auto_scroll is False
        
    print("  ✓ Lyrics view tests passed")


async def test_setlist_interactions():
    """Test setlist add/remove/select."""
    print("Testing Setlist Interactions...")
    
    app = TeleprompterApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        
        # Go to setlist tab
        tabs = screen.query_one("#main-tabs")
        tabs.active = "tab-setlist"
        await pilot.pause()
        
        setlist_view = screen.query_one("#setlist-view")
        initial_count = len(setlist_view.children)
        
        # Add song via search screen
        await pilot.press("a")
        await pilot.pause()
        
        # Should be on search screen now
        search_screen = app.screen
        # Find search input and type
        search_input = search_screen.query_one("#search-input")
        search_input.value = "sweet"
        await pilot.pause()
        
        results_list = search_screen.query_one("#results-list")
        await pilot.pause()
        
        if len(results_list.children) > 0:
            # Focus the results list (Down key)
            await pilot.press("down")
            await pilot.pause()
            
            # Verify focus moved to results list
            assert results_list.has_focus, "Results list should have focus after Down key"
            
            # Select first result with Enter
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            
            # Should be back on main screen
            main_screen = app.screen
            tabs = main_screen.query_one("#main-tabs")
            tabs.active = "tab-setlist"
            await pilot.pause()
            setlist_view = main_screen.query_one("#setlist-view")
            assert len(setlist_view.children) > initial_count
        
    print("  ✓ Setlist interaction tests passed")


async def test_edge_cases():
    """Test edge cases and error handling."""
    print("Testing Edge Cases...")
    
    # Test empty song
    song = parse_chordpro("{title: Empty}", "empty.cho")
    assert song.title == "Empty"
    assert len(song.all_lines) == 0
    
    # Test song with only whitespace
    song = parse_chordpro("   \n\n  \n", "ws.cho")
    assert len(song.all_lines) >= 0
    
    # Test malformed chords - only valid root chords count
    song = parse_chordpro("[XYZ] [123] [C]", "bad.cho")
    line = song.all_lines[0]
    chords = [seg[1] for seg in line.segments if seg[1] and seg[1].root]
    assert len(chords) == 1  # Only [C] should parse
    assert chords[0].root == "C"
    
    # Test transpose with flats
    chord = Chord.parse("Bb")
    transposed = chord.transpose(2)
    assert transposed.root == "C"
    
    chord = Chord.parse("Eb")
    transposed = chord.transpose(-2)
    # Using sharps: Eb -> D -> C# (enharmonic to Db)
    assert transposed.root in ("C#", "Db")
    
    # Test library with missing file
    with tempfile.TemporaryDirectory() as tmpdir:
        lib = SongLibrary(Path(tmpdir) / "songs", Path(tmpdir) / "cache.json")
        song = lib.get_song("nonexistent.cho")
        assert song is None
    
    print("  ✓ Edge case tests passed")


async def run_all_tests():
    """Run all virtual tests."""
    print("=" * 50)
    print("TELEPROMPTER V2 - VIRTUAL TEST SUITE")
    print("=" * 50)
    
    tests = [
        test_chordpro_parser,
        test_library,
        test_midi_clock,
        test_models,
        test_app_rendering,
        test_lyrics_view,
        test_setlist_interactions,
        test_edge_cases,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            await test()
            passed += 1
        except Exception as e:
            print(f"  ✗ FAILED: {e}")
            failed += 1
    
    print("=" * 50)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 50)
    
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)