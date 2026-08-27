# meshspeak

Reads incoming Meshtastic text messages aloud through the speaker, fully
offline. Built for the glorb Windows laptop with a Nano G2 Ultra plugged in
over USB — anyone on the mesh can text the glorb and it talks.

Everything needed at runtime is in this folder, including the Piper voice
model (`voices/en_US-lessac-medium.onnx`, ~60 MB, committed to the repo on
purpose) — so `git pull` while you have internet, `pip install` once, and
you're good to go on playa with zero connectivity.

## One-time setup (needs internet)

```
cd meshspeak
python -m venv venv
venv\Scripts\pip install -r requirements.txt     # Windows
# or: venv/bin/pip install -r requirements.txt   # mac/linux
```

On Windows the Nano G2 Ultra usually shows up as a COM port out of the box.
If it doesn't, install the CP210x/CH34x USB serial driver while you still
have internet.

## Run (fully offline)

```
venv\Scripts\python meshspeak.py                 # auto-detects the port
venv\Scripts\python meshspeak.py --port COM5     # or pick it explicitly
```

On mac: `venv/bin/python meshspeak.py --port /dev/tty.usbmodem1101`

On startup it says "mesh speak online" through the speaker so you know the
audio path works (skip with `--no-hello`). Then every text message received
on the mesh is spoken as "Message from <sender>: <text>", using the sender's
long name when the node database knows it. Messages queue up and play one at
a time, so bursts don't talk over each other.

## Autostart on the glorb laptop

Task Scheduler → Create Task → trigger "At log on" → action:

```
Program:   C:\path\to\glorb\meshspeak\venv\Scripts\python.exe
Arguments: C:\path\to\glorb\meshspeak\meshspeak.py
Start in:  C:\path\to\glorb\meshspeak
```

## Notes

- TTS is [Piper](https://github.com/OHF-Voice/piper1-gpl) running locally on
  CPU; the voice is `en_US-lessac-medium` from
  [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices).
  To swap voices, download another `.onnx` + `.onnx.json` pair into
  `voices/` and pass `--model`.
- Playback uses `winsound` on Windows, `afplay` on mac, `aplay` on Linux —
  no extra audio dependencies.
- The radio pushes packets over serial; there's no polling and no network
  anywhere in the loop.
