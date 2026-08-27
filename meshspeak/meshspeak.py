#!/usr/bin/env python3
"""meshspeak: read incoming Meshtastic text messages aloud, fully offline.

Listens to a Meshtastic node (e.g. Nano G2 Ultra) over USB serial and speaks
every received text message through the speaker using Piper TTS. No internet
required at runtime -- the voice model lives in this repo under voices/.

Usage:
    python meshspeak.py                 # auto-detect serial port
    python meshspeak.py --port COM5     # explicit port (Windows)
    python meshspeak.py --port /dev/tty.usbmodem1101   # explicit port (mac)
"""

import argparse
import platform
import queue
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import meshtastic.serial_interface
from pubsub import pub

HERE = Path(__file__).resolve().parent
DEFAULT_MODEL = HERE / "voices" / "en_US-lessac-medium.onnx"

speech_queue = queue.Queue()


def play_wav(wav_path):
    """Play a wav file with whatever the OS has built in. Blocks until done."""
    system = platform.system()
    if system == "Windows":
        import winsound
        winsound.PlaySound(str(wav_path), winsound.SND_FILENAME)
    elif system == "Darwin":
        subprocess.run(["afplay", str(wav_path)], check=False)
    else:
        subprocess.run(["aplay", "-q", str(wav_path)], check=False)


def speak(text, model_path):
    """Synthesize text with Piper and play it. Blocks until playback ends."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = Path(f.name)
    try:
        subprocess.run(
            [sys.executable, "-m", "piper",
             "--model", str(model_path),
             "--output_file", str(wav_path)],
            input=text.encode("utf-8"),
            check=True,
            capture_output=True,
        )
        play_wav(wav_path)
    finally:
        wav_path.unlink(missing_ok=True)


def tts_worker(model_path):
    """Speak queued messages one at a time so bursts don't overlap."""
    while True:
        text = speech_queue.get()
        try:
            speak(text, model_path)
        except Exception as e:
            print(f"[tts error] {e}", file=sys.stderr)
        finally:
            speech_queue.task_done()


def sender_name(packet, interface):
    """Prefer the sender's long name from the node db, fall back to node id."""
    from_id = packet.get("fromId")
    try:
        node = (interface.nodes or {}).get(from_id, {})
        long_name = node.get("user", {}).get("longName")
        if long_name:
            return long_name
    except Exception:
        pass
    return from_id or "someone"


def on_receive(packet, interface):
    decoded = packet.get("decoded", {})
    if decoded.get("portnum") != "TEXT_MESSAGE_APP":
        return
    text = decoded.get("text", "").strip()
    if not text:
        return
    who = sender_name(packet, interface)
    print(f"[msg] {who}: {text}")
    speech_queue.put(f"Message from {who}: {text}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default=None,
                        help="serial port (default: auto-detect)")
    parser.add_argument("--model", default=str(DEFAULT_MODEL),
                        help="path to Piper .onnx voice model")
    parser.add_argument("--no-hello", action="store_true",
                        help="skip the spoken startup announcement")
    args = parser.parse_args()

    model_path = Path(args.model)
    if not model_path.exists():
        sys.exit(f"voice model not found: {model_path}")

    threading.Thread(target=tts_worker, args=(model_path,), daemon=True).start()

    pub.subscribe(on_receive, "meshtastic.receive")

    print(f"connecting to Meshtastic node ({args.port or 'auto-detect'})...")
    iface = meshtastic.serial_interface.SerialInterface(devPath=args.port)
    me = iface.getMyNodeInfo() or {}
    long_name = me.get("user", {}).get("longName", "unknown node")
    print(f"connected to {long_name}; listening for messages (ctrl-c to quit)")

    if not args.no_hello:
        speech_queue.put(f"mesh speak online, connected to {long_name}")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        iface.close()


if __name__ == "__main__":
    main()
