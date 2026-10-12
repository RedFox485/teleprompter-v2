"""WebSocket server for iPhone client - minimal, lightweight."""
import asyncio
import contextlib
import json
import time
from dataclasses import dataclass, field

from aiohttp import web

from teleprompter.chordpro import Song
from teleprompter.models import PlayState


@dataclass
class WebClient:
    ws: web.WebSocketResponse
    connected_at: float = field(default_factory=time.time)
    last_ping: float = field(default_factory=time.time)


class WebServer:
    def __init__(self, app_state, host: str = "0.0.0.0", port: int = 8000, library=None):
        self.app_state = app_state
        self.library = library
        self.host = host
        self.port = port
        self.clients: dict[int, WebClient] = {}
        self._client_id = 0
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None
        self._beat_schedule_task: asyncio.Task | None = None
        self._next_beat_times: list[float] = []
        
    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/", self._handle_index)
        app.router.add_get("/ws", self._handle_websocket)
        
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()
        
        # Start beat scheduler for pre-scheduled sync
        self._beat_schedule_task = asyncio.create_task(self._beat_scheduler())
        
    async def stop(self) -> None:
        if self._beat_schedule_task:
            self._beat_schedule_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._beat_schedule_task
                
        for client in self.clients.values():
            await client.ws.close()
        self.clients.clear()
        
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
            
    async def _handle_index(self, request: web.Request) -> web.Response:
        return web.FileResponse("src/teleprompter/web_client.html")
        
    async def _handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=30)
        await ws.prepare(request)
        
        self._client_id += 1
        client_id = self._client_id
        self.clients[client_id] = WebClient(ws=ws)
        
        # Send initial full state
        await self._send_state(ws)
        
        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    await self._handle_message(client_id, msg.data)
                elif msg.type == web.WSMsgType.ERROR:
                    break
        finally:
            self.clients.pop(client_id, None)
            
        return ws
        
    async def _handle_message(self, client_id: int, data: str) -> None:
        try:
            msg = json.loads(data)
        except json.JSONDecodeError:
            return
            
        msg_type = msg.get("type")
        
        if msg_type == "tapTempo":
            self.app_state.bpm_tap()
            await self.broadcast_bpm()
            
        elif msg_type == "selectSong":
            index = msg.get("index", 0)
            if 0 <= index < len(self.app_state.current_setlist.songs):
                self.app_state.current_song_index = index
                await self._load_current_song()
                await self.broadcast_state()
                
        elif msg_type == "transpose":
            delta = msg.get("delta", 0)
            self.app_state.transpose(delta)
            await self.broadcast_state()
            
        elif msg_type == "scroll":
            position = msg.get("position", 0.0)
            self.app_state.set_scroll_position(position)
            await self.broadcast_scroll(position)
            
        elif msg_type == "search":
            query = msg.get("query", "")
            results = self.app_state.library.search(query)
            await self._send_to_client(client_id, {
                "type": "searchResults",
                "results": [
                    {
                        "id": s.id,
                        "title": s.title,
                        "artist": s.artist,
                        "key": s.key,
                        "tempo": s.tempo,
                    }
                    for s in results[:8]
                ],
            })
            
        elif msg_type == "addToSetlist":
            song_id = msg.get("songId")
            if song_id:
                song = self.app_state.library.get_song(song_id)
                if song:
                    self.app_state.current_setlist.add_song(
                        song_path=song.filepath,
                        song_title=song.title,
                        song_artist=song.artist,
                        song_key=song.key,
                        song_tempo=song.tempo,
                        song_time_signature=song.time_signature,
                    )
                    await self.broadcast_setlist()
                    
        elif msg_type == "removeFromSetlist":
            index = msg.get("index")
            if index is not None and 0 <= index < len(self.app_state.current_setlist.songs):
                self.app_state.current_setlist.remove_song(index)
                await self.broadcast_setlist()
                
        elif msg_type == "reorderSetlist":
            from_idx = msg.get("from")
            to_idx = msg.get("to")
            if from_idx is not None and to_idx is not None:
                self.app_state.current_setlist.move_song(from_idx, to_idx)
                await self.broadcast_setlist()
                
        elif msg_type == "toggleAutoScroll":
            self.app_state.config.auto_scroll_enabled = (
                not self.app_state.config.auto_scroll_enabled
            )
            await self.broadcast_state()
            
        elif msg_type == "play":
            self.app_state.play_state = PlayState.PLAYING
            await self.broadcast_state()
            
        elif msg_type == "pause":
            self.app_state.play_state = PlayState.PAUSED
            await self.broadcast_state()
            
        elif msg_type == "stop":
            self.app_state.play_state = PlayState.STOPPED
            await self.broadcast_state()
            
        elif msg_type == "ping":
            if client_id in self.clients:
                self.clients[client_id].last_ping = time.time()
            await self._send_to_client(client_id, {"type": "pong", "serverTime": time.time()})
            
    async def _send_to_client(self, client_id: int, msg: dict) -> None:
        client = self.clients.get(client_id)
        if client:
            with contextlib.suppress(Exception):
                await client.ws.send_str(json.dumps(msg))
                
    async def _send_state(self, ws: web.WebSocketResponse) -> None:
        song = self._get_current_song()
        await ws.send_str(json.dumps({
            "type": "state",
            "song": self._song_to_dict(song) if song else None,
            "scroll": 0.0,
            "transpose": self.app_state.transpose,
            "bpm": self.app_state.bpm,
            "autoScroll": self.app_state.config.auto_scroll_enabled,
            "playState": self.app_state.play_state.value,
            "setlist": self._setlist_to_list(),
            "currentSongIndex": self.app_state.current_song_index,
            "midiConnected": self.app_state.midi_connected,
            "serverTime": time.time(),
        }))
        
    def _song_to_dict(self, song: Song) -> dict:
        section_names = ("section", "soc", "start_of_chorus", "chorus")
        return {
            "id": song.filepath,
            "title": song.title,
            "artist": song.artist,
            "key": song.key,
            "tempo": song.tempo,
            "sections": [
                {
                    "name": sec.name,
                    "lines": [
                        {
                            "text": line.plain_text,
                            "chords": [c.raw for t, c in line.segments if c],
                            "is_section_header": (
                                line.is_directive and line.directive in section_names
                            ),
                        }
                        for line in sec.lines
                    ]
                }
                for sec in song.sections
            ]
        }
        
    def _get_current_song(self):
        """Get the currently selected song from the library."""
        if (self.library and self.app_state.current_setlist 
            and self.app_state.current_song_index >= 0 
            and self.app_state.current_song_index < len(self.app_state.current_setlist.songs)):
            song_entry = self.app_state.current_setlist.songs[self.app_state.current_song_index]
            return self.library.get_song(song_entry.song_path)
        return None
    
    async def broadcast_state(self) -> None:
        song = self._get_current_song()
        msg = {
            "type": "state",
            "song": self._song_to_dict(song) if song else None,
            "scroll": 0.0,
            "transpose": self.app_state.transpose,
            "bpm": self.app_state.bpm,
            "autoScroll": self.app_state.config.auto_scroll_enabled,
            "playState": self.app_state.play_state.value,
            "setlist": self._setlist_to_list(),
            "currentSongIndex": self.app_state.current_song_index,
            "midiConnected": self.app_state.midi_connected,
            "serverTime": time.time(),
        }
        await self._broadcast(msg)
        
    async def broadcast_bpm(self) -> None:
        # Send current BPM and pre-calculated next beat times for client-side scheduling
        await self._broadcast({
            "type": "bpm",
            "bpm": self.app_state.bpm,
            "nextBeats": self._next_beat_times[:10],
            "serverTime": time.time(),
        })
        
    async def broadcast_setlist(self) -> None:
        await self._broadcast({"type": "setlist", "setlist": self._setlist_to_list()})
        
    def _setlist_to_list(self) -> list:
        if not self.app_state.current_setlist:
            return []
        return [
            {
                "id": s.id,
                "title": s.title,
                "artist": s.artist,
                "key": s.key,
                "tempo": s.tempo,
                "status": s.status.value,
            }
            for s in self.app_state.current_setlist.songs
        ]
        
    async def _broadcast(self, msg: dict) -> None:
        data = json.dumps(msg)
        for client_id, client in list(self.clients.items()):
            try:
                await client.ws.send_str(data)
            except Exception:
                self.clients.pop(client_id, None)
                
    async def _beat_scheduler(self) -> None:
        """Pre-calculate beat times for client-side scheduling to minimize WiFi latency."""
        while True:
            await asyncio.sleep(0.1)
            bpm = self.app_state.bpm
            if bpm <= 0:
                continue
                
            beat_interval = 60.0 / bpm
            now = time.time()
            
            # Calculate next 10 beat times
            self._next_beat_times = []
            next_beat = now + beat_interval
            for _ in range(10):
                self._next_beat_times.append(next_beat)
                next_beat += beat_interval
                
    def get_connection_info(self) -> dict:
        import socket
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        return {
            "host": self.host,
            "port": self.port,
            "url": f"http://{local_ip}:{self.port}",
            "clients": len(self.clients),
        }