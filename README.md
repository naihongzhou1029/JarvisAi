# J.A.R.V.I.S. — Local AI Voice Assistant

A fully local, agentic AI voice assistant with wake word detection, screen vision, desktop control, and an Iron Man-inspired web UI. Voice, vision, STT and TTS all run locally; the LLM here uses a cloud provider (OpenRouter Auto Router) by default.

> Say **"Hey Jarvis"** → ask anything → Jarvis sees your screen, controls your apps, searches the web, and speaks back.

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![Windows](https://img.shields.io/badge/platform-Windows-0078D6)
![Ubuntu](https://img.shields.io/badge/platform-Ubuntu%20(GNOME%20Wayland)-E95420)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Ubuntu / GNOME Wayland port (this branch: `ubuntu`)

This fork ports the Windows assistant to **Ubuntu 26.04 (GNOME 50, Wayland)** and swaps the LLM backend to **OpenRouter Auto Router** (`openrouter/auto`) instead of a local Ollama model. Everything else (wake word, Whisper STT, Kokoro TTS, the 31 tools, the Iron Man web UI at `localhost:7860`) is unchanged.

### What changed for Wayland

| Area | Windows upstream | Ubuntu / GNOME Wayland port |
|------|------------------|------------------------------|
| Input (mouse/keyboard) | PyAutoGUI | `ydotool` (uinput) via a persistent `ydotoold` |
| Screenshot | PyAutoGUI capture | XDG Desktop Portal `Screenshot` (`interactive=false`, silent) |
| OCR / screen reading | PowerShell WinRT OCR | `tesseract` (TSV → text + coordinates) |
| Volume | Windows Core Audio | `wpctl` (PipeWire) |
| Brightness | WMI | `brightnessctl` |
| Lock / power | `rundll32` / `shutdown.exe` | `loginctl lock-session` / `systemctl` |
| Notification | Windows toast | `notify-send` |
| Clipboard | PowerShell | `wl-clipboard` (`wl-copy`/`wl-paste`) |
| Media keys | PyAutoGUI | `playerctl` (MPRIS) |
| Apps (30+) | `%LocalAppData%` paths | Linux executables + `shutil.which`/`gtk-launch`/`xdg-open` |
| LLM | Ollama (local) | OpenRouter Auto Router (OpenAI-compatible) |
| Audio I/O | PyAudio | `sounddevice` (PortAudio on PipeWire) |
| Mic capture | PyAudio | `sounddevice` |

### Known Wayland limitations

- `get_open_windows` / `focus_window` are **not available** on stock GNOME Wayland (the compositor sandbox forbids window enumeration/activation for external clients). The agent is prompted to work by coordinate (`read_screen` → `find_on_screen` → `click_at`) instead of by window. To restore these, install a companion GNOME Shell extension.
- `type_text` cannot inject CJK text through `ydotool` (no IME); ASCII works.
- The first portal screenshot may show a one-time permission dialog; GNOME then remembers it for the session.

### Quick start (Ubuntu)

```bash
# 1. System packages + /dev/uinput setup (needs sudo, run once)
sudo bash setup_system.sh        # tesseract, ydotool, espeak-ng, brightnessctl, playerctl, libportaudio2
# → then LOG OUT and back in so the 'uinput'/'input' group takes effect

# 2. Python environment (uses managed Python 3.11 via uv; CPU torch)
./install.sh

# 3. Configure your key (never committed)
mkdir -p ~/.config/ubuntu-siri
printf 'OPENROUTER_API_KEY=sk-or-...\n' > ~/.config/ubuntu-siri/env
chmod 600 ~/.config/ubuntu-siri/env

# 4. Launch (starts ydotoold if needed, then wake word + web UI)
./start.sh
```

Web UI opens at **http://localhost:7860**. Say **"Hey Jarvis"**, or type a command in the chat bar.

---

## Features

- **Voice-first interaction** — wake word detection ("Hey Jarvis"), natural speech input, streaming TTS responses
- **31 built-in tools** — desktop automation, screen reading (OCR), app control, web search, file ops, system commands
- **Agentic tool chaining** — up to 15 sequential tool calls per request (click → verify → scroll → click → done)
- **Screen vision** — reads your screen via OCR, finds UI elements by text, clicks buttons by coordinates
- **Multiple LLM providers** — OpenRouter (Auto Router, default here), any OpenAI-compatible API (LM Studio, vLLM, Groq, …)
- **Iron Man HUD web UI** — real-time chat, tool execution logs, provider management, settings, quick actions
- **Persistent memory** — remembers facts across sessions using SQLite + ChromaDB (offline lexical embeddings)
- **Context management** — sliding window with auto-summarization to stay within token limits
- **One-click install** — `install.sh` sets up everything, `start.sh` launches (`setup_system.sh` for the sudo/`uinput` step)

---
Coffe helps: https://buymeacoffee.com/azzren
---

## Quick Start (Windows — upstream reference)

> See the **Ubuntu / GNOME Wayland port** section above for how to run this fork. The steps below are the original upstream Windows flow.

### Prerequisites

- **Windows 10/11**
- **Python 3.11+** — [python.org/downloads](https://www.python.org/downloads/)
- **Ollama** — [ollama.com/download](https://ollama.com/download) (for local LLM)

### 1. Install

```bash
git clone https://github.com/PanPenek/jarvis.git
cd jarvis
install.bat
```

This will:
1. Create a Python virtual environment (`.venv`)
2. Install all 18 dependencies
3. Download wake word ONNX models

### 2. Pull an LLM model

```bash
ollama pull qwen3:8b
```

Any Ollama model works — `qwen3:8b` is a good balance of speed and quality. Smaller options: `qwen3:4b`, `llama3.2:3b`. Larger: `qwen3:14b`, `llama3.1:8b`.

### 3. Launch

```bash
start.bat
```

Jarvis will:
- Start the voice listener (wake word detection)
- Open the web UI at **http://localhost:7860**
- Speak "Good morning. Jarvis online."

### 4. Use it

| Method | How |
|--------|-----|
| **Voice** | Say **"Hey Jarvis"** → wait for "Yes?" → speak your command |
| **Web UI** | Type in the chat bar at the bottom → click Send |
| **Keyboard** | Press **F2** → type command in terminal → Enter |

---

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  Wake Word  │────▶│   STT        │────▶│    LLM       │
│(openWakeWord)│    │ (Whisper)    │     │ (OpenRouter) │
└─────────────┘     └──────────────┘     └──────┬───────┘
                                                │
┌─────────────┐     ┌──────────────┐     ┌──────▼───────┐
│   Web UI    │◀───▶│  Event Bus   │◀────│  Tool Router │
│  (FastAPI)  │     │ (WebSocket)  │     │  (31 tools)  │
└─────────────┘     └──────────────┘     └──────┬───────┘
                    │   ydotool + portal + tesseract (Wayland)
                    ┌──────▼───────┐     ┌──────▼───────┐
                    │   Memory     │     │    TTS       │
                    │(SQLite+Chroma│     │  (Kokoro)    │
                    └──────────────┘     └──────────────┘
```

**Pipeline:** Wake word → Record speech → Transcribe (Whisper) → LLM with tools (OpenRouter) → Speak response (Kokoro)

**Voice, vision, STT and TTS run locally.** The LLM is a cloud call to OpenRouter (unless you point `config.yaml` at a local OpenAI-compatible server). No audio ever leaves the machine.

---

## Tools (31)

### Desktop Automation & Vision
| Tool | Description |
|------|-------------|
| `read_screen` | Screenshot + OCR — returns all visible text with coordinates |
| `find_on_screen` | Find text/button on screen, returns (x, y) coordinates |
| `click_at` | Click at screen coordinates (left/right/double click) |
| `type_text` | Type text at current cursor position |
| `press_key` | Keyboard shortcuts (ctrl+c, alt+tab, win+d, etc.) |
| `scroll_screen` | Scroll up/down |
| `move_mouse` | Move cursor to coordinates |
| `focus_window` | Bring window to foreground by title |
| `get_open_windows` | List all open window titles |
| `media_control` | Play/pause/next/previous/mute media |
| `screenshot` | Save screenshot to Desktop |

### Apps & Web
| Tool | Description |
|------|-------------|
| `open_app` | Launch apps by name (30+ mapped: Chrome, Discord, VS Code, Spotify...) |
| `open_url` | Open URL in default browser |
| `kill_process` | Close a running process |
| `web_search` | Search DuckDuckGo, return top results |
| `fetch_page` | Fetch and extract text from a URL |
| `get_weather` | Current weather for any location |

### System Control
| Tool | Description |
|------|-------------|
| `set_volume` / `get_volume` | Control system volume (0-100%) |
| `set_brightness` | Screen brightness (laptops) |
| `get_system_info` | CPU, RAM, disk usage |
| `get_clipboard` / `set_clipboard` | Read/write clipboard |
| `show_notification` | Windows toast notification |
| `set_timer` | Countdown timer with notification |
| `lock_screen` | Lock workstation |
| `power_command` | Shutdown, restart, or sleep |

### Files & Code
| Tool | Description |
|------|-------------|
| `read_file` / `write_file` | Read/write files (sandboxed to allowed paths) |
| `list_files` | List directory contents |
| `run_python` | Execute Python code in sandbox (10s timeout) |
| `delegate_task` | Send subtask to local LLM for parallel processing |

---

## Web UI

The web interface runs at `http://localhost:7860` and provides:

- **Real-time chat** — voice and typed conversations displayed together
- **Arc Reactor status** — animated indicator (listening / thinking / speaking / idle)
- **Tool execution panel** — see every tool call and result as it happens
- **Live event feed** — full timeline of all events
- **Quick actions** — one-click buttons for weather, screenshot, system info, etc.
- **Provider management** — add, edit, delete, and switch LLM providers
- **Settings** — configure TTS voice/speed, STT model, wake word threshold, LLM temperature

---

## Configuration

All settings are in `config.yaml`. You can also change most of them from the web UI's Config tab.

### Adding a Cloud LLM Provider

Open the web UI → Config tab → **Add Provider**, or edit `config.yaml`:

```yaml
llm:
  active_provider: nvidia   # Switch to this provider
  providers:
    ollama:
      type: ollama
      label: Ollama (Local)
      model: qwen3:8b
    nvidia:
      type: openai
      label: NVIDIA NIM
      model: meta/llama-3.1-70b-instruct
      base_url: https://integrate.api.nvidia.com/v1
      api_key: nvapi-xxxx
    lmstudio:
      type: openai
      label: LM Studio
      model: local-model
      base_url: http://localhost:1234/v1
```

Any OpenAI-compatible API works (LM Studio, vLLM, Together AI, Groq, etc.)

### STT Options

```yaml
stt:
  model: small      # tiny (fastest) | base | small (default) | medium | large-v3 (best)
  device: cuda      # cuda (GPU) or cpu — auto-falls back to CPU if CUDA fails
  compute_type: int8
```

### TTS Options

```yaml
tts:
  voice: af_heart   # Kokoro voice name
  speed: 1.1        # Speech speed (0.5 = slow, 2.0 = fast)
```

---

## Controls

| Input | Action |
|-------|--------|
| **"Hey Jarvis"** (idle) | Wake up — starts listening for your command |
| **"Hey Jarvis"** (busy) | Stop — interrupts current task/speech |
| **"Stop"** / **"Cancel"** / **"Shut up"** | Voice stop command (after wake word) |
| **Esc** | Keyboard abort — stops everything instantly |
| **F2** | Type a command in the terminal |
| **Insert** | Toggle mute (TTS on/off) |
| **ABORT button** (web UI) | Stop current task |
| **"stop"** (typed in web chat) | Stop current task |

---

## Project Structure

```
jarvis/
├── config.yaml          # All configuration (OpenRouter provider)
├── setup_system.sh      # sudo: apt deps + /dev/uinput (run once)
├── install.sh           # One-click installer (uv venv + deps + wake models)
├── start.sh             # Launcher (starts ydotoold + main)
├── requirements.txt     # Python dependencies
│
├── jarvis/
│   ├── main.py          # Core orchestrator — pipeline, abort, events
│   ├── wake.py          # Wake word detection (openWakeWord + sounddevice)
│   ├── stt.py           # Speech-to-text (faster-whisper)
│   ├── tts.py           # Text-to-speech (Kokoro)
│   ├── web.py           # Web UI server (FastAPI + WebSocket)
│   ├── context.py       # Sliding window context manager
│   ├── memory.py        # Long-term memory (SQLite + ChromaDB, offline embeddings)
│   ├── llm.py           # Internal LLM calls + ${ENV} api-key resolution
│   ├── static/
│   │   └── index.html   # Iron Man HUD web interface
│   └── tools/
│       ├── router.py    # Tool registry and dispatch
│       ├── desktop.py   # Wayland automation (ydotool input, portal shot, OCR)
│       ├── _shot.py     # XDG portal screenshot helper (run by system python)
│       ├── app_control.py  # App launching (Linux), URL opening
│       ├── web_search.py   # DuckDuckGo, weather, page fetch
│       ├── system.py    # wpctl volume, brightnessctl, notify-send, wl-clipboard, power
│       ├── file_ops.py  # Sandboxed file read/write/list
│       ├── code_exec.py # Python code execution sandbox
│       └── subagent.py  # Task delegation to the active provider
│
└── tests/               # Unit tests (pytest)
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `cublas64_12.dll not found` | Normal on systems without CUDA toolkit. STT auto-falls back to CPU. |
| Wake word not detecting | Lower `threshold` in config (try 0.3). Check your mic is set as default input. |
| No sound from Jarvis | Check `is_muted` state (Insert key toggles). Check system audio output. |
| STT recording hangs | Mic conflict resolved — wake word mic auto-pauses during recording. |
| OpenRouter 401 / connection error | Ensure `OPENROUTER_API_KEY` is set (`~/.config/ubuntu-siri/env`) and `base_url` is `https://openrouter.ai/api/v1`. |
| Web UI not updating | Open browser console (F12) — check for `[WS]` log messages. Refresh page. |

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Wake Word | [openWakeWord](https://github.com/dscripka/openWakeWord) (ONNX) |
| Speech-to-Text | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) |
| Text-to-Speech | [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) |
| LLM | [OpenRouter](https://openrouter.ai/) Auto Router (`openrouter/auto`, OpenAI-compatible) / any OpenAI-compatible API |
| Memory | SQLite + [ChromaDB](https://www.trychroma.com/) (offline lexical embeddings) |
| Web UI | [FastAPI](https://fastapi.tiangolo.com/) + WebSocket |
| Desktop Control (Wayland) | [ydotool](https://github.com/ReimuNotMoe/ydotool) input + XDG portal screenshot + [Tesseract](https://github.com/tesseract-ocr/tesseract) OCR |
| Audio I/O | [sounddevice](https://python-sounddevice.readthedocs.io/) on PipeWire |

---

## License

MIT
