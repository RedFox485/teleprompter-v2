"""
Audio Analysis Module for Section Detection and Beat Mapping.

Uses librosa for chroma/spectral analysis to detect song sections
and map them to beat intervals for precise timing control.
"""
import json
from dataclasses import dataclass, field

import librosa
import librosa.display
import numpy as np


@dataclass
class BeatInfo:
    """Information about a single beat."""
    time: float          # Absolute time in seconds
    beat_number: int     # Beat number (1-based within song)
    measure_number: int  # Measure number (1-based)
    beat_in_measure: int # Beat within measure (1-based)
    is_downbeat: bool    # True if beat 1 of measure


@dataclass
class Section:
    """Detected or manually defined song section."""
    name: str                    # "Verse 1", "Chorus", "Bridge", "Guitar Solo", etc.
    start_time: float            # Start time in seconds
    end_time: float              # End time in seconds
    start_beat: int              # Starting beat number
    end_beat: int                # Ending beat number
    start_measure: int           # Starting measure
    end_measure: int             # Ending measure
    confidence: float = 1.0      # Detection confidence (0-1)
    repeats: int = 1             # Number of times to repeat (for live extension)
    color: str = ""              # UI color for section
    
    @property
    def duration(self) -> float:
        return self.end_time - self.start_time
    
    @property
    def beat_count(self) -> int:
        return self.end_beat - self.start_beat + 1
    
    @property
    def measure_count(self) -> int:
        return self.end_measure - self.start_measure + 1


@dataclass
class SongAnalysis:
    """Complete analysis of a song audio file."""
    filepath: str
    duration: float
    tempo: float
    time_signature: str = "4/4"
    beats: list[BeatInfo] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    downbeats: list[float] = field(default_factory=list)
    
    def get_beat_at_time(self, time: float) -> BeatInfo | None:
        """Find the beat info at a given time."""
        for beat in self.beats:
            if beat.time <= time < beat.time + 0.1:  # Small tolerance
                return beat
        return None
    
    def get_section_at_time(self, time: float) -> Section | None:
        """Find the section at a given time."""
        for section in self.sections:
            if section.start_time <= time < section.end_time:
                return section
        return None
    
    def get_section_at_beat(self, beat_number: int) -> Section | None:
        """Find the section containing a beat number."""
        for section in self.sections:
            if section.start_beat <= beat_number <= section.end_beat:
                return section
        return None


def analyze_audio(filepath: str, min_section_duration: float = 4.0) -> SongAnalysis:
    """
    Analyze audio file to detect tempo, beats, downbeats, and sections.
    
    Args:
        filepath: Path to audio file (.wav, .mp3, .m4a, etc.)
        min_section_duration: Minimum section duration in seconds
    
    Returns:
        SongAnalysis with tempo, beats, downbeats, and detected sections
    """
    y, sr = librosa.load(filepath, sr=None)
    duration = len(y) / sr
    
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    
    # Use onset strength for downbeat detection
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    downbeat_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr, 
                                               units='frames')[1]
    downbeat_times = librosa.frames_to_time(downbeat_frames, sr=sr)
    
    
    # Build beat info list
    beats = []
    measure_num = 1
    beat_in_measure = 1
    downbeat_set = set(np.round(downbeat_times, 3))
    
    for i, beat_time in enumerate(beat_times):
        is_downbeat = np.round(beat_time, 3) in downbeat_set
        if is_downbeat and i > 0:
            measure_num += 1
            beat_in_measure = 1
        else:
            beat_in_measure += 1
            
        beats.append(BeatInfo(
            time=float(beat_time),
            beat_number=i + 1,
            measure_number=measure_num,
            beat_in_measure=beat_in_measure,
            is_downbeat=is_downbeat
        ))
    
    # Detect sections using chroma + spectral contrast
    sections = detect_sections(y, sr, beat_times, downbeat_times, min_section_duration)
    
    return SongAnalysis(
        filepath=filepath,
        duration=duration,
        tempo=float(tempo),
        time_signature="4/4",
        beats=beats,
        sections=sections,
        downbeats=downbeat_times.tolist()
    )


def detect_sections(
    y: np.ndarray, 
    sr: int, 
    beat_times: np.ndarray,
    downbeat_times: np.ndarray,
    min_duration: float = 4.0
) -> list[Section]:
    """
    Detect song sections using chroma features and spectral contrast.
    
    Uses self-similarity matrix on chroma features to find structural boundaries,
    then refines boundaries to align with downbeats.
    """
    # Compute chroma features (12 pitch classes)
    hop_length = 512
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop_length)
    librosa.frames_to_time(np.arange(chroma.shape[1]), sr=sr, hop_length=hop_length)
    
    # Compute spectral contrast for additional texture info
    contrast = librosa.feature.spectral_contrast(y=y, sr=sr, hop_length=hop_length)
    
    # Stack features
    features = np.vstack([chroma, contrast])
    
    # Normalize
    features = librosa.util.normalize(features, axis=0)
    
    # Compute self-similarity matrix
    from scipy.spatial.distance import cdist
    1 - cdist(features.T, features.T, metric='cosine')
    
    # Find boundaries using novelty detection
    # (simplified: use librosa's segment detection)
    try:
        boundaries = librosa.segment.agglomerative(features, k=8)  # Target ~8 sections
    except Exception:
        boundaries = librosa.segment.recursive(features, depth=3)
    
    boundary_times = librosa.frames_to_time(boundaries, sr=sr, hop_length=hop_length)
    
    # Ensure boundaries include start and end
    if boundary_times[0] > 0.5:
        boundary_times = np.insert(boundary_times, 0, 0.0)
    if boundary_times[-1] < len(y) / sr - 0.5:
        boundary_times = np.append(boundary_times, len(y) / sr)
    
    # Filter boundaries too close together
    min_boundary_interval = min_duration
    filtered = [boundary_times[0]]
    for t in boundary_times[1:]:
        if t - filtered[-1] >= min_boundary_interval:
            filtered.append(t)
    boundary_times = np.array(filtered)
    
    # Snap boundaries to nearest downbeat
    snapped_boundaries = []
    for bt in boundary_times:
        nearest = min(downbeat_times, key=lambda d: abs(d - bt))
        if abs(nearest - bt) < 2.0:  # Within 2 seconds of downbeat
            snapped_boundaries.append(nearest)
        else:
            snapped_boundaries.append(bt)
    
    # Remove duplicates
    snapped_boundaries = np.unique(np.round(snapped_boundaries, 3))
    
    # Create sections
    sections = []
    section_names = ["Intro", "Verse 1", "Pre-Chorus", "Chorus", "Verse 2", 
                     "Pre-Chorus 2", "Chorus 2", "Bridge", "Guitar Solo", 
                     "Chorus 3", "Outro"]
    
    for i in range(len(snapped_boundaries) - 1):
        start = snapped_boundaries[i]
        end = snapped_boundaries[i + 1]
        
        # Find beat numbers
        start_beat = find_nearest_beat(beat_times, start) + 1
        end_beat = find_nearest_beat(beat_times, end)
        
        start_measure = find_measure_at_beat(beat_times, downbeat_times, start_beat)
        end_measure = find_measure_at_beat(beat_times, downbeat_times, end_beat)
        
        name = section_names[i] if i < len(section_names) else f"Section {i+1}"
        
        sections.append(Section(
            name=name,
            start_time=float(start),
            end_time=float(end),
            start_beat=start_beat,
            end_beat=end_beat,
            start_measure=start_measure,
            end_measure=end_measure,
            confidence=0.8,
            color=section_color(i)
        ))
    
    return sections


def find_nearest_beat(beat_times: np.ndarray, time: float) -> int:
    """Find index of nearest beat to given time."""
    return int(np.argmin(np.abs(beat_times - time)))


def find_measure_at_beat(beat_times: np.ndarray, downbeat_times: np.ndarray, beat_idx: int) -> int:
    """Find measure number for a given beat index."""
    if beat_idx <= 0 or beat_idx > len(beat_times):
        return 1
    beat_time = beat_times[beat_idx - 1]
    return int(np.sum(downbeat_times <= beat_time)) + 1


def section_color(index: int) -> str:
    """Get color for section index."""
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
              "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"]
    return colors[index % len(colors)]


def save_analysis(analysis: SongAnalysis, output_path: str) -> None:
    """Save analysis to JSON file."""
    data = {
        "filepath": analysis.filepath,
        "duration": analysis.duration,
        "tempo": analysis.tempo,
        "time_signature": analysis.time_signature,
        "beats": [
            {
                "time": b.time,
                "beat_number": b.beat_number,
                "measure_number": b.measure_number,
                "beat_in_measure": b.beat_in_measure,
                "is_downbeat": b.is_downbeat
            }
            for b in analysis.beats
        ],
        "sections": [
            {
                "name": s.name,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "start_beat": s.start_beat,
                "end_beat": s.end_beat,
                "start_measure": s.start_measure,
                "end_measure": s.end_measure,
                "confidence": s.confidence,
                "repeats": s.repeats,
                "color": s.color
            }
            for s in analysis.sections
        ],
        "downbeats": analysis.downbeats
    }
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)


def load_analysis(json_path: str) -> SongAnalysis:
    """Load analysis from JSON file."""
    with open(json_path) as f:
        data = json.load(f)
    
    beats = [BeatInfo(**b) for b in data.get("beats", [])]
    sections = [Section(**s) for s in data.get("sections", [])]
    
    return SongAnalysis(
        filepath=data["filepath"],
        duration=data["duration"],
        tempo=data["tempo"],
        time_signature=data.get("time_signature", "4/4"),
        beats=beats,
        sections=sections,
        downbeats=data.get("downbeats", [])
    )


def extend_section(
    analysis: SongAnalysis, section_name: str, additional_repeats: int = 1
) -> list[Section]:
    """
    Extend a section by adding repeats.
    Returns new section list with extended section.
    
    This is for live "let's do another chorus!" functionality.
    """
    new_sections = []
    for section in analysis.sections:
        new_section = Section(
            name=section.name,
            start_time=section.start_time,
            end_time=section.end_time,
            start_beat=section.start_beat,
            end_beat=section.end_beat,
            start_measure=section.start_measure,
            end_measure=section.end_measure,
            confidence=section.confidence,
            repeats=section.repeats,
            color=section.color
        )
        if section.name == section_name:
            new_section.repeats += additional_repeats
            # Extend end time based on tempo
            beats_per_repeat = section.beat_count
            beat_duration = 60.0 / analysis.tempo
            new_section.end_time += beats_per_repeat * additional_repeats * beat_duration
            new_section.end_beat += beats_per_repeat * additional_repeats
            new_section.end_measure += (beats_per_repeat * additional_repeats) // 4
        new_sections.append(new_section)
    
    # Update subsequent sections' timing
    cumulative_extra = 0.0
    for i, section in enumerate(new_sections):
        if i > 0 and new_sections[i-1].name == section_name:
            cumulative_extra = new_sections[i-1].end_time - analysis.sections[i-1].end_time
        if cumulative_extra > 0:
            section.start_time += cumulative_extra
            section.end_time += cumulative_extra
    
    return new_sections


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        sys.exit(1)
    
    audio_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else audio_file.replace('.', '_analysis.')
    
    analysis = analyze_audio(audio_file)
    save_analysis(analysis, output_file)
    for _s in analysis.sections:
        pass