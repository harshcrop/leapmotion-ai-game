"""
leap_handy_bridge.py

Gesture-triggered voice+intent pipeline:
  Leap Motion (raw hand frames over legacy WebSocket)
    -> gesture state machine (point/raise-hand = "listening")
    -> Handy STT (toggled via CLI, offline Whisper/Parakeet)
    -> clipboard watcher grabs the transcript
    -> your LLM/agent call

ASSUMPTIONS (verify against your setup before relying on this):
  1. Your old Leap Motion Controller is running the legacy Orion tracking
     service, which exposes a WebSocket at ws://127.0.0.1:6437/v6.json.
     This is the original Leap Motion Control Panel daemon behavior, not
     the newer Gemini/LeapC service used by Leap Motion Controller 2.
     If you're on Gemini, use the leapc-python-bindings instead of this
     websocket client -- the gesture state machine below is unaffected,
     only get_frame() would change.
  2. Handy is installed and already running in the background, with a
     model loaded and ready (Whisper/Parakeet).
  3. Handy pastes transcripts via the clipboard. This script reads the
     clipboard after toggling recording off. If your Handy build instead
     types directly via enigo/wtype without touching the clipboard, swap
     the "grab transcript" step for a filesystem/log watcher instead --
     check Handy's transcript history storage location.

Install:
  pip install websocket-client pyperclip
"""

import json
import subprocess
import sys
import threading
import time

import pyperclip
import websocket

LEAP_WS_URL = "ws://127.0.0.1:6437/v6.json"

# --- Gesture thresholds (tune these against your own sensor/hand size) ---
POINT_HOLD_FRAMES = 6        # consecutive frames pointing before we trust it
RELEASE_GRACE_FRAMES = 10    # consecutive frames hand-lost before we stop
PINCH_CANCEL_THRESHOLD = 0.8 # pinch this strong while listening = cancel


class GestureState:
    IDLE = "idle"
    LISTENING = "listening"


def is_pointing(hand: dict) -> bool:
    """
    Heuristic: exactly one extended finger (index), the rest curled,
    grabStrength low. Leap's v6 JSON gives pointables with 'extended' bool
    when timeVisible is used, but classic frames give per-finger data
    under hand['pointables'] via bones -- adjust to your SDK version.
    """
    extended = [p for p in hand.get("pointables", []) if p.get("extended")]
    grab_strength = hand.get("grabStrength", 1.0)
    return len(extended) == 1 and grab_strength < 0.3


def is_open_palm_raised(hand: dict, y_threshold: float = 150.0) -> bool:
    """Alternative wake gesture: open hand raised above a height threshold."""
    extended = [p for p in hand.get("pointables", []) if p.get("extended")]
    palm_y = hand.get("palmPosition", [0, 0, 0])[1]
    return len(extended) >= 4 and palm_y > y_threshold


def toggle_handy():
    """Fire Handy's cross-platform remote-control flag."""
    try:
        subprocess.run(["handy", "--toggle-transcription"], check=False, timeout=5)
    except FileNotFoundError:
        print("[!] 'handy' not found on PATH -- adjust the path in toggle_handy()", file=sys.stderr)


def cancel_handy():
    try:
        subprocess.run(["handy", "--cancel"], check=False, timeout=5)
    except FileNotFoundError:
        pass


def grab_transcript(timeout_s: float = 8.0, poll_interval: float = 0.2) -> str | None:
    """
    Poll the clipboard for a change after we stop recording. Handy needs a
    moment to run STT locally, so we wait for the clipboard to update
    rather than reading it immediately.
    """
    before = pyperclip.paste()
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(poll_interval)
        current = pyperclip.paste()
        if current and current != before:
            return current
    return None


def route_to_llm(text: str):
    """
    Plug your agent/LLM call in here. Kept separate so you can swap in
    the Anthropic API, a local model, or your n8n webhook.
    """
    print(f"[agent] routing transcript -> LLM: {text!r}")
    # Example:
    # response = client.messages.create(
    #     model="claude-sonnet-5",
    #     max_tokens=1024,
    #     messages=[{"role": "user", "content": text}],
    # )
    # print(response.content)


class LeapGestureListener:
    def __init__(self, ws_url: str = LEAP_WS_URL):
        self.ws_url = ws_url
        self.state = GestureState.IDLE
        self.point_frame_count = 0
        self.lost_frame_count = 0

    def on_frame(self, frame: dict):
        hands = frame.get("hands", [])

        if not hands:
            self._handle_no_hand()
            return

        hand = hands[0]  # single-hand control for simplicity

        if self.state == GestureState.IDLE:
            if is_pointing(hand) or is_open_palm_raised(hand):
                self.point_frame_count += 1
                if self.point_frame_count >= POINT_HOLD_FRAMES:
                    self._start_listening()
            else:
                self.point_frame_count = 0

        elif self.state == GestureState.LISTENING:
            self.lost_frame_count = 0
            if hand.get("pinchStrength", 0.0) >= PINCH_CANCEL_THRESHOLD:
                self._cancel_listening()

    def _handle_no_hand(self):
        if self.state == GestureState.LISTENING:
            self.lost_frame_count += 1
            if self.lost_frame_count >= RELEASE_GRACE_FRAMES:
                self._stop_listening()
        else:
            self.point_frame_count = 0

    def _start_listening(self):
        print("[gesture] point/raise detected -> starting Handy recording")
        self.state = GestureState.LISTENING
        self.point_frame_count = 0
        self.lost_frame_count = 0
        toggle_handy()  # start

    def _stop_listening(self):
        print("[gesture] hand lost -> stopping Handy recording")
        self.state = GestureState.IDLE
        toggle_handy()  # stop
        transcript = grab_transcript()
        if transcript:
            threading.Thread(target=route_to_llm, args=(transcript,), daemon=True).start()
        else:
            print("[!] no transcript captured within timeout")

    def _cancel_listening(self):
        print("[gesture] pinch detected -> cancelling recording")
        self.state = GestureState.IDLE
        cancel_handy()

    def run(self):
        def on_message(ws, message):
            try:
                frame = json.loads(message)
            except json.JSONDecodeError:
                return
            self.on_frame(frame)

        def on_open(ws):
            print(f"[leap] connected to {self.ws_url}")
            # Enable gestures/background frames as needed, e.g.:
            # ws.send(json.dumps({"background": True}))

        def on_error(ws, error):
            print(f"[leap] error: {error}", file=sys.stderr)

        def on_close(ws, code, msg):
            print("[leap] connection closed")

        ws_app = websocket.WebSocketApp(
            self.ws_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        ws_app.run_forever()


if __name__ == "__main__":
    listener = LeapGestureListener()
    listener.run()
