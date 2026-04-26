<div align="center">

# AutoSplat Studio

### Turn any video or photo set into a 3D Gaussian Splat — in one click.

![Version](https://img.shields.io/badge/version-1.0.0-orange?style=flat-square)
![Platform](https://img.shields.io/badge/platform-Windows-blue?style=flat-square)
![Python](https://img.shields.io/badge/python-3.12%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)
![Build](https://img.shields.io/badge/build-passing-brightgreen?style=flat-square)

</div>

---

> **AutoSplat Studio** is a desktop application for Windows that automates the entire photogrammetry pipeline — from raw footage to a fully trained **Gaussian Splat model** — with no command-line knowledge required. Drop a video. Press a button. Get a `.ply`.

---

<div align="center">

![AutoSplat Studio Interface](./ressources/AutoSplat_workflow.gif)

*The AutoSplat Studio interface — drag a video or image folder, monitor real-time extraction, and track each pipeline step from a single window.*

</div>

---

## ⬇️ Download & Install

> **Just want to use the app? This is the only section you need.**

**[⬇️ Download AutoSplat Studio — Full Package (~5 GB)](YOUR_GOOGLE_DRIVE_LINK_HERE)**

The archive contains everything — the app, COLMAP, Lichtfeld Studio 0.5.0, and FFmpeg already in place. No separate downloads, no manual configuration.

**Once downloaded:**

1. Extract the `.zip` anywhere on your machine *(e.g. `C:\Tools\AutoSplat_Studio\`)*
2. Double-click **`setup.bat`** — installs Python dependencies automatically
3. Double-click **`AutoSplat_Studio.exe.vbs`** — the app opens, you're ready

> **Requirement:** Python 3.12+ must be installed on your machine.
> Download it at [python.org](https://www.python.org/downloads/) and check **"Add to PATH"** during installation.

That's it. No terminal, no configuration, no manual setup.

---

## Why AutoSplat Studio?

Gaussian Splatting is one of the most powerful 3D reconstruction techniques available today — but the toolchain is fragmented, technical, and unforgiving. You need COLMAP for reconstruction, a separate trainer for splatting, and FFmpeg for video handling. Each tool has its own CLI, its own quirks, and its own failure modes.

**AutoSplat Studio exists to remove all of that friction.**

### Core Principles

- 🎯 &nbsp;**One window, one button.** The entire pipeline — extraction, reconstruction, training — runs from a single interface with zero terminal interaction.
- 🔍 &nbsp;**Smart filtering, not brute force.** The packet-picking algorithm + Laplacian blur filter ensures only the sharpest frames enter COLMAP, directly improving reconstruction quality.
- 🔌 &nbsp;**Decoupled by design.** The core pipeline (COLMAP, OpenCV, Lichtfeld) is fully independent from the UI layer — making it testable, scriptable, and extensible without touching a single widget.
- 🔄 &nbsp;**Resumable at every stage.** Interrupted mid-run? Resume from the Mapper or jump straight to Lichtfeld training without starting over.
- 📦 &nbsp;**Export-ready output.** Beyond `.ply`, Lichtfeld's built-in exporter converts your splat to **`.html`** (shareable web viewer) and **`.spz`** (compressed splat format).

---

## Workflow

```
📹 Video  or  🖼️ Image Folder
        │
        ▼
┌─────────────────────────────┐
│  Smart Frame Extraction     │  ← Packet picking + Laplacian blur filter (OpenCV)
│  & Blur Filtering           │
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────┐
│  COLMAP Pipeline            │  ← Feature Extraction → Matching → Mapper → Undistortion
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────┐
│  Gaussian Splat Training    │  ← Lichtfeld Studio (adc / mcmc strategy)
└────────────┬────────────────┘
             │
             ▼
     📄 .ply  ·  🌐 .html  ·  📦 .spz
```

---

## For Developers

> The following sections are intended for contributors who want to work on the source code, modify the pipeline, or build on top of AutoSplat Studio.

### What's in this repository

This GitHub repo contains **only the source code**. The compiled binaries (COLMAP, Lichtfeld Studio, FFmpeg) are not committed here due to their size — they are included in the full package download above.

If you clone this repo, you will need to populate `bin/` manually (see below).

### Prerequisites

- **Python 3.12+** — [python.org](https://www.python.org/downloads/)
- **Git**
- **Windows 10/11**
- **CUDA-capable GPU** *(optional but strongly recommended)*

### Clone & Setup

```bash
# 1. Clone the repository
git clone https://github.com/your-username/AutoSplat_Studio.git
cd AutoSplat_Studio

# 2. Run the automated setup
setup.bat
```

### Populate the `bin/` folder

After cloning, your `bin/` folder will be empty. You need to fill it with the three binaries before the app can run.

**Option A — Quickest:** Download the [full package](YOUR_GOOGLE_DRIVE_LINK_HERE), extract it, and copy only the `bin/` folder into your cloned repo.

**Option B — Manual:** Download each binary separately and place them in the correct folders:

| Binary | Source | Expected path |
|---|---|---|
| COLMAP x64 Windows CUDA | [colmap.github.io](https://colmap.github.io/) | `bin/colmap/` |
| Lichtfeld Studio | [github.com/MrNeRF/LichtFeld-Studio](https://github.com/MrNeRF/LichtFeld-Studio) | `bin/lichtfeld/` |
| FFmpeg | [ffmpeg.org/download](https://ffmpeg.org/download.html) | `bin/ffmpeg.exe` |

> **Note on Lichtfeld:** AutoSplat Studio was designed and tested with the **portable Windows build 0.5.0**. For installation instructions, follow the directions given on the [Lichtfeld Studio repository](https://github.com/MrNeRF/LichtFeld-Studio). Portable Windows builds are available on their portal — consider supporting their project there if you find it useful.

Your `bin/` folder should look exactly like this before launching:

```
bin/
├── colmap/         ← COLMAP x64 Windows CUDA
├── lichtfeld/      ← Lichtfeld Studio portable
├── ffmpeg.exe
├── Icone.ico
└── config.json
```

### Run in Development Mode

```bash
# Launch with a visible console for debug output
venv\Scripts\python.exe main.pyw
```

All logs from the pipeline runners stream directly to your terminal, making it easy to debug COLMAP output, regex parsers, or progress callbacks.

### Project Structure

```
AutoSplat_Studio/
├── main.pyw                  ← Entry point
├── setup.bat                 ← One-click environment setup
├── requirements.txt
│
├── config/                   ← Configuration management (load/save config.json)
│   └── settings.py
│
├── core/                     ← Business logic — zero UI dependencies
│   ├── callbacks.py          ← PipelineCallbacks: the UI ↔ Core bridge
│   ├── paths.py              ← Binary resolution & project path management
│   ├── extractor.py          ← OpenCV frame extraction & blur filtering
│   ├── colmap_runner.py      ← 4 COLMAP steps, each with a dedicated parser
│   ├── lichtfeld_runner.py   ← Lichtfeld training runner (ANSI-aware parser)
│   └── pipeline.py           ← PipelineOrchestrator: coordinates all steps
│
├── ui/                       ← CustomTkinter interface — no business logic
│   ├── theme.py              ← Color palette & BentoCard widget
│   ├── callbacks.py          ← PipelineCallbacks dataclass
│   ├── settings_window.py    ← Modal settings window
│   └── app.py                ← AutoSplatApp main window
│
├── bin/                      ← Third-party binaries (not in git — see above)
│   ├── colmap/
│   ├── lichtfeld/
│   ├── ffmpeg.exe
│   └── config.json
│
└── temp_projects/            ← Generated project folders (gitignored)
```

### Key Design Decision: The Callback Bridge

The most important architectural pattern in this codebase is **`core/callbacks.py`**.

Every pipeline runner receives a `PipelineCallbacks` object at runtime instead of accessing UI widgets directly. This means:

- The entire `core/` package can be imported and tested **without a display**.
- Progress reporting, cancellation signals, and live previews are **injected** — not hardcoded.
- Swapping the UI toolkit requires changing **only `ui/app.py`**.

```python
# How the bridge is constructed in ui/app.py
cb = PipelineCallbacks(
    log                 = self.log,
    set_step            = self.set_step_status,
    update_monitor      = self._cb_update_monitor,
    is_cancelled        = lambda: self.is_cancelled,
    set_current_process = lambda p: setattr(self, "_current_process", p),
)
pipeline.run(..., cb=cb)
```

---

## Architecture & Technologies

| Component | Technology | Docs |
|---|---|---|
| UI Framework | CustomTkinter | [github.com/TomSchimansky/CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) |
| 3D Reconstruction | COLMAP | [colmap.github.io](https://colmap.github.io/) |
| Gaussian Training | Lichtfeld Studio | [github.com/MrNeRF/LichtFeld-Studio](https://github.com/MrNeRF/LichtFeld-Studio) |
| Image Processing | OpenCV | [opencv.org](https://opencv.org/) |
| Video Handling | FFmpeg | [ffmpeg.org](https://ffmpeg.org/) |
| Drag & Drop | tkinterdnd2 | [github.com/pmgagne/tkinterdnd2](https://github.com/pmgagne/tkinterdnd2) |


## Contributing

All contributions are welcome — whether it's a bug report, a new feature, or a documentation fix.

Please open an [issue](../../issues) before submitting a large pull request so we can align on the approach. For smaller fixes, feel free to open a PR directly.

New pipeline steps belong in `core/`, new widgets in `ui/`.

---

## License

Distributed under the **MIT License**. See [`LICENSE`](./LICENSE) for full terms.

---

<div align="center">

Built with ☕ and an unreasonable love for point clouds.

</div>
