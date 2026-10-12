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

    def search(self, query: str) -> list[SongCacheEntry]:
        """Search songs by title/artist."""
        query = query.lower()
        return [
            entry for entry in self._cache.values()
            if query in entry.title.lower() or query in entry.artist.lower()
        ]


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