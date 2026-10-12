"""
ChordPro (.cho/.pro) parser for teleprompter.
Format: {directive: value} + plain text with [inline chords]
"""
import contextlib
import re
from dataclasses import dataclass, field
from enum import Enum


class ChordQuality(Enum):
    MAJOR = ""
    MINOR = "m"
    DIM = "dim"
    AUG = "aug"
    SUS2 = "sus2"
    SUS4 = "sus4"
    SEVEN = "7"
    MAJ7 = "maj7"
    MIN7 = "m7"
    MIN7B5 = "m7b5"
    DIM7 = "dim7"
    ADD9 = "add9"
    SIX = "6"
    NINE = "9"


@dataclass
class Chord:
    root: str
    quality: str = ""
    bass: str | None = None
    raw: str = ""

    @classmethod
    def parse(cls, text: str) -> "Chord":
        text = text.strip()
        # Match: [C], [Cm], [Cmaj7], [C/G], [C/E], etc.
        pattern = (
            r"^([A-G][#b]?)"
            r"(m|maj7|min7|m7b5|dim7|dim|aug|sus2|sus4|7|add9|6|9)?"
            r"(?:/([A-G][#b]?))?$"
        )
        match = re.match(pattern, text)
        if not match:
            return cls(root="", raw=text)
        root, quality, bass = match.groups()
        return cls(root=root, quality=quality or "", bass=bass, raw=text)

    def transpose(self, semitones: int) -> "Chord":
        notes = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        flats = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
        try:
            idx = notes.index(self.root)
        except ValueError:
            try:
                idx = flats.index(self.root)
            except ValueError:
                return self
        new_root = notes[(idx + semitones) % 12]
        return Chord(root=new_root, quality=self.quality, bass=self.bass)

    def __str__(self) -> str:
        bass = f"/{self.bass}" if self.bass else ""
        return f"[{self.root}{self.quality}{bass}]"


@dataclass
class Section:
    name: str
    lines: list["Line"] = field(default_factory=list)
    start_line_idx: int = 0


@dataclass
class Line:
    segments: list[tuple[str, Chord | None]]  # (text, chord or None)
    is_directive: bool = False
    directive: str | None = None
    value: str | None = None

    @property
    def plain_text(self) -> str:
        return "".join(chord.raw if chord else text for text, chord in self.segments)


@dataclass
class Song:
    title: str = ""
    artist: str = ""
    key: str = ""
    time_signature: str = "4/4"
    tempo: int = 120
    capo: int = 0
    sections: list[Section] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    filepath: str = ""

    @property
    def all_lines(self) -> list[Line]:
        return [line for section in self.sections for line in section.lines]

    def transpose(self, semitones: int) -> "Song":
        new_song = Song(
            title=self.title,
            artist=self.artist,
            key=self._transpose_key(self.key, semitones),
            time_signature=self.time_signature,
            tempo=self.tempo,
            capo=self.capo,
            metadata=self.metadata.copy(),
            filepath=self.filepath,
        )
        for section in self.sections:
            new_section = Section(name=section.name, start_line_idx=section.start_line_idx)
            for line in section.lines:
                if line.is_directive:
                    new_section.lines.append(line)
                    continue
                new_segments = []
                for text, chord in line.segments:
                    if chord:
                        new_segments.append((text, chord.transpose(semitones)))
                    else:
                        new_segments.append((text, None))
                new_section.lines.append(Line(segments=new_segments))
            new_song.sections.append(new_section)
        return new_song

    def _transpose_key(self, key: str, semitones: int) -> str:
        if not key:
            return ""
        # Simple key transposition
        notes = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        match = re.match(r"([A-G][#b]?)(m|min)?", key)
        if not match:
            return key
        root, quality = match.groups()
        try:
            idx = notes.index(root)
        except ValueError:
            flats = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
            idx = flats.index(root)
        new_root = notes[(idx + semitones) % 12]
        return f"{new_root}{quality or ''}"


def parse_chordpro(content: str, filepath: str = "") -> Song:
    """Parse ChordPro format into Song object."""
    lines = content.splitlines()
    song = Song(filepath=filepath)
    current_section = Section(name="")
    section_counter = 0
    line_counter = 0

    directive_pattern = re.compile(r"^\{([^:}]+)(?::([^}]*))?\}$")
    chord_pattern = re.compile(r"\[([^\]]+)\]")

    for raw_line in lines:
        line = raw_line.rstrip()
        if not line:
            current_section.lines.append(Line(segments=[("", None)]))
            line_counter += 1
            continue

        # Check for directive
        directive_match = directive_pattern.match(line)
        if directive_match:
            directive, value = directive_match.groups()
            directive = directive.lower().strip()
            value = value.strip() if value else ""

            if directive in ("title", "t"):
                song.title = value
            elif directive in ("artist", "a"):
                song.artist = value
            elif directive in ("key", "k"):
                song.key = value
            elif directive in ("time", "time_signature"):
                song.time_signature = value
            elif directive in ("tempo", "bpm"):
                with contextlib.suppress(ValueError):
                    song.tempo = int(value)
            elif directive in ("capo",):
                with contextlib.suppress(ValueError):
                    song.capo = int(value)
            elif directive in ("section", "soc", "start_of_chorus", "chorus"):
                if current_section.lines:
                    song.sections.append(current_section)
                section_name = value or f"Section {section_counter}"
                current_section = Section(name=section_name, start_line_idx=line_counter)
                section_counter += 1
            elif directive in ("end_of_chorus", "eoc", "eos", "end_of_section"):
                if current_section.lines:
                    song.sections.append(current_section)
                current_section = Section(name="", start_line_idx=line_counter)
            elif directive in ("comment", "c"):
                current_section.lines.append(Line(
                    segments=[(value, None)],
                    is_directive=True,
                    directive="comment",
                    value=value,
                ))
                line_counter += 1
            else:
                # Store unknown directives as metadata
                song.metadata[directive] = value
                current_section.lines.append(Line(
                    segments=[(line, None)],
                    is_directive=True,
                    directive=directive,
                    value=value,
                ))
                line_counter += 1
            continue

        # Parse line with inline chords: "This is a [C]line with [G]chords"
        segments = []
        last_end = 0
        for match in chord_pattern.finditer(line):
            chord_text = match.group(1)
            start, end = match.span()
            if start > last_end:
                segments.append((line[last_end:start], None))
            chord = Chord.parse(chord_text)
            segments.append(("", chord))
            last_end = end
        if last_end < len(line):
            segments.append((line[last_end:], None))

        if not segments:
            segments = [(line, None)]

        current_section.lines.append(Line(segments=segments))
        line_counter += 1

    if current_section.lines:
        song.sections.append(current_section)

    # If no sections defined, create one
    if not song.sections:
        song.sections = [Section(name="", lines=current_section.lines, start_line_idx=0)]

    return song


def load_song(filepath: str) -> Song:
    """Load song from .cho/.pro file."""
    with open(filepath, encoding="utf-8") as f:
        content = f.read()
    return parse_chordpro(content, filepath)


def save_song(song: Song, filepath: str) -> None:
    """Save song to ChordPro format."""
    lines = []
    if song.title:
        lines.append(f"{{title: {song.title}}}")
    if song.artist:
        lines.append(f"{{artist: {song.artist}}}")
    if song.key:
        lines.append(f"{{key: {song.key}}}")
    if song.time_signature:
        lines.append(f"{{time: {song.time_signature}}}")
    if song.tempo:
        lines.append(f"{{tempo: {song.tempo}}}")
    if song.capo:
        lines.append(f"{{capo: {song.capo}}}")
    for key, value in song.metadata.items():
        lines.append(f"{{{key}: {value}}}")
    lines.append("")

    for section in song.sections:
        if section.name:
            lines.append(f"{{section: {section.name}}}")
        for line in section.lines:
            if line.is_directive:
                if line.directive == "comment":
                    lines.append(f"{{comment: {line.value}}}")
                else:
                    lines.append(f"{{{line.directive}: {line.value}}}")
            else:
                text_parts = []
                for text, chord in line.segments:
                    text_parts.append(text)
                    if chord:
                        text_parts.append(str(chord))
                lines.append("".join(text_parts))
        if section.name:
            lines.append("{end_of_section}")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))