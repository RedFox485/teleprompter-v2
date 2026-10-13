"""
Live Section Manager - Hybrid Live/Programmed Section Control.

Allows dynamic section extension during performance:
- Pre-programmed song structure with beat-accurate sections
- Live "Add Chorus", "Add Verse", "Add Bridge" buttons
- Drives both teleprompter (lyrics) and lighting rig (MIDI)
"""
import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum


class SectionType(Enum):
    INTRO = "intro"
    VERSE = "verse"
    PRE_CHORUS = "pre_chorus"
    CHORUS = "chorus"
    BRIDGE = "bridge"
    SOLO = "solo"
    OUTRO = "outro"
    CUSTOM = "custom"


class LiveAction(Enum):
    """Actions that can be triggered live."""
    ADD_CHORUS = "add_chorus"
    ADD_VERSE = "add_verse"
    ADD_BRIDGE = "add_bridge"
    ADD_SOLO = "add_solo"
    EXTEND_CURRENT = "extend_current"
    SKIP_TO_NEXT = "skip_to_next"
    JUMP_TO_SECTION = "jump_to_section"
    END_SONG = "end_song"


@dataclass
class SectionTemplate:
    """Template for a section type."""
    type: SectionType
    name: str
    default_measures: int = 8
    chord_progression: str = ""  # ChordPro format for this section
    lyrics: str = ""
    midi_cue: int = 0  # MIDI program change or note for lighting
    color: str = ""


@dataclass
class LiveSection:
    """A section instance during live performance."""
    template: SectionTemplate
    start_beat: int
    end_beat: int
    start_time: float
    end_time: float
    repeats: int = 1
    max_repeats: int = 3
    is_active: bool = False
    is_extended: bool = False


@dataclass
class SongStructure:
    """Complete song structure with live extension capability."""
    title: str
    artist: str
    tempo: float
    time_signature: str = "4/4"
    sections: list[LiveSection] = field(default_factory=list)
    current_section_index: int = 0
    current_beat: int = 0
    current_measure: int = 1
    playback_state: str = "stopped"  # stopped, playing, paused
    
    # Callbacks for external systems
    on_section_change: Callable[[LiveSection], None] | None = None
    on_beat: Callable[[int, int], None] | None = None  # beat, measure
    on_midi_cue: Callable[[int], None] | None = None  # MIDI cue number
    
    def get_current_section(self) -> LiveSection | None:
        if 0 <= self.current_section_index < len(self.sections):
            return self.sections[self.current_section_index]
        return None
    
    def get_next_section(self) -> LiveSection | None:
        if self.current_section_index + 1 < len(self.sections):
            return self.sections[self.current_section_index + 1]
        return None
    
    def advance_beat(self) -> None:
        """Call on each beat during playback."""
        self.current_beat += 1
        
        # Check measure boundary
        beats_per_measure = 4  # Default 4/4
        if self.current_beat % beats_per_measure == 1:
            self.current_measure = self.current_beat // beats_per_measure + 1
        
        # Check section boundary
        current = self.get_current_section()
        if current and self.current_beat > current.end_beat:
            self._advance_section()
        
        # Notify beat callback
        if self.on_beat:
            self.on_beat(self.current_beat, self.current_measure)
    
    def _advance_section(self) -> None:
        """Move to next section."""
        if self.current_section_index + 1 < len(self.sections):
            self.current_section_index += 1
            new_section = self.get_current_section()
            if new_section:
                new_section.is_active = True
                if self.on_section_change:
                    self.on_section_change(new_section)
                if new_section.template.midi_cue and self.on_midi_cue:
                    self.on_midi_cue(new_section.template.midi_cue)
    
    def trigger_action(self, action: LiveAction) -> bool:
        """Trigger a live action. Returns True if action was executed."""
        if action == LiveAction.ADD_CHORUS:
            return self._insert_section(SectionType.CHORUS)
        elif action == LiveAction.ADD_VERSE:
            return self._insert_section(SectionType.VERSE)
        elif action == LiveAction.ADD_BRIDGE:
            return self._insert_section(SectionType.BRIDGE)
        elif action == LiveAction.ADD_SOLO:
            return self._insert_section(SectionType.SOLO)
        elif action == LiveAction.EXTEND_CURRENT:
            return self._extend_current_section()
        elif action == LiveAction.SKIP_TO_NEXT:
            return self._skip_to_next()
        elif action == LiveAction.END_SONG:
            self.playback_state = "stopped"
            return True
        return False
    
    def _insert_section(self, section_type: SectionType) -> bool:
        """Insert a section after current section."""
        current = self.get_current_section()
        if not current:
            return False
        
        # Find template
        template = self._get_template(section_type)
        if not template:
            return False
        
        # Calculate timing
        insert_beat = current.end_beat + 1
        beats_per_measure = 4
        measures = template.default_measures
        beat_duration = 60.0 / self.tempo
        
        new_section = LiveSection(
            template=template,
            start_beat=insert_beat,
            end_beat=insert_beat + (measures * beats_per_measure) - 1,
            start_time=insert_beat * beat_duration,
            end_time=(insert_beat + measures * beats_per_measure) * beat_duration,
            repeats=1
        )
        
        # Insert after current
        insert_idx = self.current_section_index + 1
        self.sections.insert(insert_idx, new_section)
        
        # Shift subsequent sections
        self._shift_sections_after(insert_idx, new_section.beat_count)
        
        return True
    
    def _extend_current_section(self) -> bool:
        """Add a repeat to current section."""
        current = self.get_current_section()
        if not current or current.repeats >= current.max_repeats:
            return False
        
        current.repeats += 1
        beats_per_repeat = current.template.default_measures * 4
        current.end_beat += beats_per_repeat
        current.end_time += beats_per_repeat * (60.0 / self.tempo)
        current.is_extended = True
        
        # Shift subsequent sections
        self._shift_sections_after(self.current_section_index + 1, beats_per_repeat)
        
        return True
    
    def _skip_to_next(self) -> bool:
        """Skip to next section immediately."""
        if self.current_section_index + 1 < len(self.sections):
            self.current_section_index += 1
            new_section = self.get_current_section()
            if new_section:
                new_section.is_active = True
                if self.on_section_change:
                    self.on_section_change(new_section)
                if new_section.template.midi_cue and self.on_midi_cue:
                    self.on_midi_cue(new_section.template.midi_cue)
            return True
        return False
    
    def _shift_sections_after(self, start_idx: int, beat_shift: int) -> None:
        """Shift all sections after start_idx by beat_shift."""
        beat_duration = 60.0 / self.tempo
        time_shift = beat_shift * beat_duration
        
        for i in range(start_idx, len(self.sections)):
            self.sections[i].start_beat += beat_shift
            self.sections[i].end_beat += beat_shift
            self.sections[i].start_time += time_shift
            self.sections[i].end_time += time_shift
    
    def _get_template(self, section_type: SectionType) -> SectionTemplate | None:
        """Get template for section type."""
        templates = {
            SectionType.CHORUS: SectionTemplate(
                type=SectionType.CHORUS, name="Chorus", default_measures=8,
                midi_cue=1, color="#d62728"
            ),
            SectionType.VERSE: SectionTemplate(
                type=SectionType.VERSE, name="Verse", default_measures=8,
                midi_cue=2, color="#1f77b4"
            ),
            SectionType.BRIDGE: SectionTemplate(
                type=SectionType.BRIDGE, name="Bridge", default_measures=8,
                midi_cue=3, color="#9467bd"
            ),
            SectionType.SOLO: SectionTemplate(
                type=SectionType.SOLO, name="Guitar Solo", default_measures=16,
                midi_cue=4, color="#ff7f0e"
            ),
        }
        return templates.get(section_type)


def create_default_structure(title: str, artist: str, tempo: float) -> SongStructure:
    """Create a standard song structure."""
    structure = SongStructure(title=title, artist=artist, tempo=tempo)
    
    # Standard sections
    templates = [
        (SectionType.INTRO, 4, 1),
        (SectionType.VERSE, 8, 2),
        (SectionType.PRE_CHORUS, 4, 3),
        (SectionType.CHORUS, 8, 1),
        (SectionType.VERSE, 8, 2),
        (SectionType.PRE_CHORUS, 4, 3),
        (SectionType.CHORUS, 8, 1),
        (SectionType.BRIDGE, 8, 3),
        (SectionType.CHORUS, 8, 1),
        (SectionType.OUTRO, 4, 4),
    ]
    
    beat = 1
    for i, (sec_type, measures, midi_cue) in enumerate(templates):
        template = SectionTemplate(
            type=sec_type, 
            name=sec_type.value.capitalize(),
            default_measures=measures,
            midi_cue=midi_cue,
            color=section_color(i)
        )
        beats = measures * 4
        section = LiveSection(
            template=template,
            start_beat=beat,
            end_beat=beat + beats - 1,
            start_time=(beat - 1) * 60.0 / tempo,
            end_time=(beat + beats - 1) * 60.0 / tempo,
        )
        structure.sections.append(section)
        beat += beats
    
    return structure


def section_color(index: int) -> str:
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
              "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"]
    return colors[index % len(colors)]


def load_structure_from_analysis(analysis) -> SongStructure:
    """Create SongStructure from audio analysis."""
    structure = SongStructure(
        title="", artist="", tempo=analysis.tempo,
        time_signature=analysis.time_signature
    )
    
    for i, section in enumerate(analysis.sections):
        template = SectionTemplate(
            type=SectionType.CUSTOM,
            name=section.name,
            default_measures=section.measure_count,
            midi_cue=i + 1,
            color=section.color
        )
        live_section = LiveSection(
            template=template,
            start_beat=section.start_beat,
            end_beat=section.end_beat,
            start_time=section.start_time,
            end_time=section.end_time,
            repeats=section.repeats
        )
        structure.sections.append(live_section)
    
    return structure


class LiveController:
    """
    WebSocket-based live controller for section management.
    
    Receives actions from web client (iPhone) and executes them.
    """
    def __init__(self, structure: SongStructure):
        self.structure = structure
        self.pending_action: LiveAction | None = None
        self.action_queue: asyncio.Queue = asyncio.Queue()
    
    async def handle_message(self, msg: dict) -> dict:
        """Handle incoming WebSocket message from web client."""
        action_str = msg.get("action")
        if not action_str:
            return {"status": "error", "message": "No action specified"}
        
        try:
            action = LiveAction(action_str)
        except ValueError:
            return {"status": "error", "message": f"Unknown action: {action_str}"}
        
        # Queue action for execution on next beat boundary
        await self.action_queue.put(action)
        return {"status": "queued", "action": action_str}
    
    async def process_actions(self) -> None:
        """Process queued actions on beat boundaries."""
        while True:
            try:
                action = await asyncio.wait_for(self.action_queue.get(), timeout=0.1)
                self.structure.trigger_action(action)
            except TimeoutError:
                continue
    
    def get_status(self) -> dict:
        """Get current status for web client."""
        current = self.structure.get_current_section()
        next_sec = self.structure.get_next_section()
        
        return {
            "title": self.structure.title,
            "artist": self.structure.artist,
            "tempo": self.structure.tempo,
            "current_section": current.template.name if current else None,
            "current_section_index": self.structure.current_section_index,
            "current_beat": self.structure.current_beat,
            "current_measure": self.structure.current_measure,
            "section_progress": self._get_section_progress(current) if current else 0,
            "next_section": next_sec.template.name if next_sec else None,
            "playback_state": self.structure.playback_state,
            "available_actions": [a.value for a in LiveAction],
            "sections": [
                {
                    "name": s.template.name,
                    "type": s.template.type.value,
                    "start_beat": s.start_beat,
                    "end_beat": s.end_beat,
                    "repeats": s.repeats,
                    "max_repeats": s.max_repeats,
                    "is_active": s.is_active,
                    "is_extended": s.is_extended,
                    "color": s.template.color
                }
                for s in self.structure.sections
            ]
        }
    
    def _get_section_progress(self, section: LiveSection) -> float:
        if not section:
            return 0.0
        total = section.end_beat - section.start_beat + 1
        current = self.structure.current_beat - section.start_beat + 1
        return max(0.0, min(1.0, current / total))


if __name__ == "__main__":
    # Demo
    structure = create_default_structure("Test Song", "Test Artist", 120.0)
    for _i, _s in enumerate(structure.sections):
        pass
    
    # Simulate live actions
    structure.trigger_action(LiveAction.ADD_CHORUS)
