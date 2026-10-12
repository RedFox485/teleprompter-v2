"""
MIDI clock input handler for BPM sync.
Receives MIDI clock (0xF8) and calculates tempo.
"""
import asyncio
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

import rtmidi


@dataclass
class MidiClockState:
    bpm: float = 120.0
    is_running: bool = False
    last_tick_time: float = 0.0
    tick_intervals: deque = field(default_factory=lambda: deque(maxlen=24))  # 1 bar at 24 PPQN


class MidiClockHandler:
    """Handles MIDI clock input for tempo synchronization."""

    PPQN = 24  # MIDI clocks per quarter note

    def __init__(self, on_bpm_change: Callable[[float], None] | None = None,
                 on_start: Callable[[], None] | None = None,
                 on_stop: Callable[[], None] | None = None,
                 on_continue: Callable[[], None] | None = None,
                 midi_channel: int = 0):  # 0 = omni
        self.on_bpm_change = on_bpm_change
        self.on_start = on_start
        self.on_stop = on_stop
        self.on_continue = on_continue
        self.midi_channel = midi_channel
        self.state = MidiClockState()
        self._midi_in: rtmidi.MidiIn | None = None
        self._port_name: str = ""
        self._running = False
        self._task: asyncio.Task | None = None

    def list_ports(self) -> list[str]:
        """List available MIDI input ports."""
        midi_in = rtmidi.MidiIn()
        return midi_in.get_ports()

    def open_port(self, port_name: str) -> bool:
        """Open MIDI input port by name."""
        try:
            self._midi_in = rtmidi.MidiIn()
            ports = self._midi_in.get_ports()
            for i, port in enumerate(ports):
                if port_name.lower() in port.lower():
                    self._midi_in.open_port(i)
                    self._port_name = port
                    self._midi_in.set_callback(self._midi_callback)
                    self._midi_in.ignore_types(sysex=False, timing=False, active_sense=True)
                    return True
            return False
        except Exception:
            return False

    def open_virtual_port(self, name: str = "Teleprompter MIDI In") -> bool:
        """Create a virtual MIDI input port."""
        try:
            self._midi_in = rtmidi.MidiIn()
            self._midi_in.open_virtual_port(name)
            self._port_name = name
            self._midi_in.set_callback(self._midi_callback)
            self._midi_in.ignore_types(sysex=False, timing=False, active_sense=True)
            return True
        except Exception:
            return False

    def close(self) -> None:
        """Close MIDI port."""
        if self._midi_in:
            self._midi_in.close_port()
            self._midi_in = None

    def _midi_callback(self, message, time_stamp) -> None:
        """Process incoming MIDI messages."""
        if not message:
            return
        status = message[0]

        # MIDI Real-time messages
        if status == 0xF8:  # Clock tick
            self._handle_clock_tick(time_stamp)
        elif status == 0xFA:  # Start
            self._handle_start()
        elif status == 0xFC:  # Stop
            self._handle_stop()
        elif status == 0xFB:  # Continue
            self._handle_continue()

    def _handle_clock_tick(self, time_stamp: float) -> None:
        now = time_stamp if time_stamp > 0 else time.monotonic()

        if self.state.last_tick_time > 0:
            interval = now - self.state.last_tick_time
            if 0.01 < interval < 2.0:  # Sanity check
                self.state.tick_intervals.append(interval)
                if len(self.state.tick_intervals) >= 6:  # At least 1 beat
                    avg_interval = sum(self.state.tick_intervals) / len(self.state.tick_intervals)
                    # 24 ticks per quarter note, so quarter note = 24 * avg_interval
                    # BPM = 60 / quarter_note_duration
                    bpm = 60.0 / (avg_interval * self.PPQN)
                    # Smooth BPM changes
                    self.state.bpm = self.state.bpm * 0.7 + bpm * 0.3
                    if self.on_bpm_change:
                        self.on_bpm_change(self.state.bpm)

        self.state.last_tick_time = now
        self.state.is_running = True

    def _handle_start(self) -> None:
        self.state.is_running = True
        self.state.tick_intervals.clear()
        self.state.last_tick_time = 0
        if self.on_start:
            self.on_start()

    def _handle_stop(self) -> None:
        self.state.is_running = False
        if self.on_stop:
            self.on_stop()

    def _handle_continue(self) -> None:
        self.state.is_running = True
        if self.on_continue:
            self.on_continue()

    @property
    def current_bpm(self) -> float:
        return self.state.bpm

    @property
    def is_running(self) -> bool:
        return self.state.is_running

    @property
    def port_name(self) -> str:
        return self._port_name