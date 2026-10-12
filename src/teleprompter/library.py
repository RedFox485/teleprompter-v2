"""
Song library management - scanning, caching, and loading songs.
"""
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .chordpro import Song, load_song
from .models import Setlist, SetlistSong, SongStatus


@dataclass
class SongCacheEntry:
    filepath: str
    hash: str
    title: str
    artist: str
    key: str
    tempo: int
    time_signature: str
    # Enhanced metadata for future use
    capo: int = 0
    duration_seconds: float = 0.0
    tags: list[str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class SongLibrary:
    """Manages song library with caching for fast startup."""

    def __init__(self, songs_dir: Path, cache_file: Path):
        self.songs_dir = songs_dir
        self.cache_file = cache_file
        self._cache: dict[str, SongCacheEntry] = {}
        self._songs: dict[str, Song] = {}  # filepath -> Song
        self._load_cache()

    def _load_cache(self) -> None:
        if self.cache_file.exists():
            try:
                with open(self.cache_file) as f:
                    data = json.load(f)
                for entry in data:
                    self._cache[entry["filepath"]] = SongCacheEntry(**entry)
            except Exception:
                pass

    def _save_cache(self) -> None:
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, "w") as f:
                json.dump([vars(e) for e in self._cache.values()], f, indent=2)
        except Exception:
            pass

    def _file_hash(self, path: Path) -> str:
        try:
            stat = path.stat()
            return hashlib.md5(f"{stat.st_mtime}:{stat.st_size}".encode()).hexdigest()[:16]
        except Exception:
            return ""

    def scan(self) -> list[SongCacheEntry]:
        """Scan songs directory and update cache."""
        self.songs_dir.mkdir(parents=True, exist_ok=True)
        entries = []

        for ext in (".cho", ".pro", ".chordpro", ".txt"):
            for filepath in self.songs_dir.rglob(f"*{ext}"):
                rel_path = str(filepath.relative_to(self.songs_dir))
                file_hash = self._file_hash(filepath)

                if rel_path in self._cache and self._cache[rel_path].hash == file_hash:
                    # Use cached entry
                    entries.append(self._cache[rel_path])
                else:
                    # Parse and cache
                    try:
                        song = load_song(str(filepath))
                        entry = SongCacheEntry(
                            filepath=rel_path,
                            hash=file_hash,
                            title=song.title or filepath.stem,
                            artist=song.artist or "",
                            key=song.key or "",
                            tempo=song.tempo,
                            time_signature=song.time_signature,
                            capo=song.capo,
                        )
                        self._cache[rel_path] = entry
                        entries.append(entry)
                    except Exception:
                        pass

        self._save_cache()
        return entries

    def get_song(self, rel_path: str) -> Song | None:
        """Get song by relative path, parsing if needed."""
        if rel_path in self._songs:
            return self._songs[rel_path]

        full_path = self.songs_dir / rel_path
        if not full_path.exists():
            return None

        try:
            song = load_song(str(full_path))
            self._songs[rel_path] = song
            return song
        except Exception:
            return None

    def get_all_entries(self) -> list[SongCacheEntry]:
        """Get all cached song entries."""
        return list(self._cache.values())

    def search(self, query: str, max_results: int = 8) -> list[SongCacheEntry]:
        """Search songs by title, artist, key, or tempo.
        
        Supports:
        - Title/artist: "sweet", "lynard"
        - Key search: "G major", "g ma", "A minor", "a min", "a mi", "G", "Em"
        - Tempo: "98", "87", "120bpm", "90-110"
        """
        query = query.strip().lower()
        if not query:
            return list(self._cache.values())[:max_results]
        
        # Check for BPM range query (e.g., "120bpm", "100-140")
        if query.endswith("bpm") or ("-" in query and not query.startswith("-")):
            try:
                if query.endswith("bpm"):
                    target_bpm = int(query[:-3])
                    return [
                        e for e in self._cache.values()
                        if abs(e.tempo - target_bpm) <= 5
                    ][:max_results]
                elif "-" in query:
                    parts = query.split("-")
                    min_bpm = int(parts[0])
                    max_bpm = int(parts[1])
                    return [
                        e for e in self._cache.values()
                        if min_bpm <= e.tempo <= max_bpm
                    ][:max_results]
            except ValueError:
                pass
        
        # Check for key search (e.g., "G major", "g ma", "A minor", "a min", "G", "Em")
        key_query = self._parse_key_query(query)
        if key_query:
            return [
                entry for entry in self._cache.values()
                if self._key_matches(entry.key, key_query)
            ][:max_results]
        
        # Check for single key letter (e.g., "G", "Em", "C#m")
        if self._is_simple_key_query(query):
            key_query = self._normalize_simple_key(query)
            return [
                entry for entry in self._cache.values()
                if self._key_matches(entry.key, key_query)
            ][:max_results]
        
        # Check for tempo number (e.g., "98", "87", "120")
        if query.isdigit():
            target_tempo = int(query)
            return [
                e for e in self._cache.values()
                if abs(e.tempo - target_tempo) <= 2
            ][:max_results]
        
        # Default: search title and artist
        return [
            entry for entry in self._cache.values()
            if query in entry.title.lower() or query in entry.artist.lower()
        ][:max_results]

    def _is_simple_key_query(self, query: str) -> bool:
        """Check if query is a simple key like 'G', 'Em', 'C#m'."""
        import re
        return bool(re.match(r'^[a-gA-G][#b]?m?$', query))

    def _normalize_simple_key(self, query: str) -> str:
        """Normalize simple key query like 'g' -> 'G', 'em' -> 'Em'."""
        query = query.strip()
        import re
        match = re.match(r'^([a-gA-G])([#b]?)(m?)$', query)
        if not match:
            return query
        note, accidental, minor = match.groups()
        return f"{note.upper()}{accidental}{minor}"

    def _parse_key_query(self, query: str) -> str | None:
        """Parse key search query. Returns normalized key or None.
        
        Matches:
        - "G major" -> "G"
        - "g ma" -> "G"
        - "A minor" -> "Am"
        - "a min" -> "Am"
        - "a mi" -> "Am"
        - "c# minor" -> "C#m"
        - "eb major" -> "Eb"
        """
        query = query.strip()
        # Pattern: <note><accidental>? (major|minor|ma|mi|min|majo|mino)
        # Allow partial matches: major/ma/majo, minor/mi/min/mino
        import re
        pattern = r'^([A-Ga-g])([#b]?)\s*(major|minor|ma|mi|min|majo|mino)$'
        match = re.match(pattern, query, re.IGNORECASE)
        if not match:
            return None
        
        note, accidental, quality = match.groups()
        note = note.upper()
        quality = quality.lower()
        
        # Normalize key
        # Handle "mi" as minor explicitly
        if quality in ("mi", "min", "mino", "minor"):
            return f"{note}{accidental}m"
        elif quality in ("ma", "majo", "major"):
            return f"{note}{accidental}"
        elif quality.startswith("min"):
            return f"{note}{accidental}m"
        else:
            return f"{note}{accidental}"

    def _key_matches(self, song_key: str, query_key: str) -> bool:
        """Check if song key matches query key (handles enharmonic equivalents)."""
        if not song_key:
            return False
        
        # Normalize both keys for comparison
        song_norm = self._normalize_key(song_key)
        query_norm = self._normalize_key(query_key)
        
        return song_norm == query_norm

    def _normalize_key(self, key: str) -> str:
        """Normalize key for comparison (handles enharmonic equivalents)."""
        # Remove any quality suffix, normalize accidentals
        import re
        match = re.match(r'^([A-G])([#b]?)(m)?', key)
        if not match:
            return key
        note, accidental, minor = match.groups()
        accidental = accidental or ""
        minor = minor or ""
        
        # Enharmonic equivalents
        enharmonic = {
            ("C#", ""): ("Db", ""),
            ("Db", ""): ("C#", ""),
            ("D#", ""): ("Eb", ""),
            ("Eb", ""): ("D#", ""),
            ("F#", ""): ("Gb", ""),
            ("Gb", ""): ("F#", ""),
            ("G#", ""): ("Ab", ""),
            ("Ab", ""): ("G#", ""),
            ("A#", ""): ("Bb", ""),
            ("Bb", ""): ("A#", ""),
        }
        
        key_base = f"{note}{accidental}{minor}"
        equiv = enharmonic.get((note, accidental))
        if equiv:
            return f"{equiv[0]}{equiv[1]}{minor}"
        return key_base


class SetlistManager:
    """Manages setlists persistence."""

    def __init__(self, setlists_dir: Path):
        self.setlists_dir = setlists_dir
        self.setlists_dir.mkdir(parents=True, exist_ok=True)

    def save(self, setlist: Setlist) -> Path:
        """Save setlist to JSON file."""
        filepath = self.setlists_dir / f"{setlist.name.replace(' ', '_')}.json"
        data = {
            "id": setlist.id,
            "name": setlist.name,
            "date": setlist.date,
            "notes": setlist.notes,
            "songs": [
                {
                    "id": s.id,
                    "song_path": s.song_path,
                    "title": s.title,
                    "artist": s.artist,
                    "key": s.key,
                    "tempo": s.tempo,
                    "time_signature": s.time_signature,
                    "status": s.status.value,
                    "transpose": s.transpose,
                    "added_at": s.added_at,
                }
                for s in setlist.songs
            ],
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        return filepath

    def load(self, filepath: Path) -> Setlist:
        """Load setlist from JSON file."""
        with open(filepath) as f:
            data = json.load(f)
        setlist = Setlist(
            id=data["id"],
            name=data["name"],
            date=data["date"],
            notes=data.get("notes", ""),
        )
        for s in data["songs"]:
            song = SetlistSong(
                id=s["id"],
                song_path=s["song_path"],
                title=s["title"],
                artist=s["artist"],
                key=s["key"],
                tempo=s["tempo"],
                time_signature=s.get("time_signature", "4/4"),
                status=SongStatus(s["status"]),
                transpose=s.get("transpose", 0),
                added_at=s.get("added_at", ""),
            )
            setlist.songs.append(song)
        return setlist

    def list_setlists(self) -> list[Path]:
        return sorted(self.setlists_dir.glob("*.json"))

    def delete(self, name: str) -> bool:
        filepath = self.setlists_dir / f"{name.replace(' ', '_')}.json"
        if filepath.exists():
            filepath.unlink()
            return True
        return False