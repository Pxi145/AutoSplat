<div align="center">

# AutoSplat Studio

### Turn any video or photo set into a 3D Gaussian Splat — in one click.

![Version](https://img.shields.io/badge/version-1.0.0-orange?style=flat-square)
![Platform](https://img.shields.io/badge/platform-Windows-blue?style=flat-square)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)
![Build](https://img.shields.io/badge/build-passing-brightgreen?style=flat-square)

</div>

---

> **AutoSplat Studio** is a desktop application for Windows that automates the entire photogrammetry pipeline — from raw footage to a fully trained **Gaussian Splat model** — with no command-line knowledge required. Drop a video. Press a button. Get a `.ply`.

---

<div align="center">

<!-- 📸 INSERT SCREENSHOT OR GIF HERE -->
![AutoSplat Studio Interface](./assets/preview.gif)

*The AutoSplat Studio interface — drag a video or image folder, monitor real-time extraction, and track each pipeline step from a single window.*

</div>

---

## Why AutoSplat Studio?

Gaussian Splatting is one of the most powerful 3D reconstruction techniques available today — but the toolchain is fragmented, technical, and unforgiving. You need COLMAP for reconstruction, a separate trainer for splatting, FFmpeg for video handling, and a custom export pipeline for USD/USDZ. Each tool has its own CLI, its own quirks, and its own failure modes.

**AutoSplat Studio exists to remove all of that friction.**

It wraps COLMAP, Lichtfeld Studio, and FFmpeg into a single cohesive desktop application, with an interface designed for creators, not engineers. Whether you're a 3D artist capturing real-world environments, a developer experimenting with NeRF-adjacent workflows, or a researcher who just wants a reliable pipeline — AutoSplat Studio gets out of your way.

### Core Principles

- 🎯 &nbsp;**One window, one button.** The entire pipeline — extraction, reconstruction, training — runs from a single interface with zero terminal interaction.
- 🔍 &nbsp;**Smart filtering, not brute force.** The packet-picking algorithm + Laplacian blur filter ensures only the sharpest frames enter COLMAP, directly improving reconstruction quality.
- 🔌 &nbsp;**Decoupled by design.** The core pipeline (COLMAP, OpenCV, Lichtfeld) is fully independent from the UI layer — making it testable, scriptable, and extensible without touching a single widget.
- 🔄 &nbsp;**Resumable at every stage.** Interrupted mid-run? You can resume from the Mapper, or jump straight to Lichtfeld training, without starting over.
- 📦 &nbsp;**Export-ready output.** Beyond `.ply`, the built-in USD exporter converts your Gaussian Splat into a `.usdz` file ready for Apple Reality Composer, USD pipelines, or archival.

---

## Getting Started

> **Prerequisites:** Windows 10/11 · GPU with CUDA support recommended · ~4 GB free disk space

### 1. Download the latest release

Head to the [**Releases**](../../releases) page and download the latest `.zip` archive.

### 2. Extract and run setup

Unzip the archive anywhere on your machine, then double-click:

```
setup.bat
```

This script will automatically create the Python virtual environment and install all required dependencies. A confirmation message will appear when setup is complete.

### 3. Launch the application

Double-click **`AutoSplat_Studio.exe.vbs`** — no console window, no terminal, just the app.

> 💡 **First run:** Make sure the `bin/` folder contains your COLMAP and Lichtfeld distributions. See the [Architecture section](#architecture--technologies) below for the expected layout.

---

## Workflow

```
📹 Video or 🖼️ Image Folder
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
      📄 .ply  +  📦 .usdz
```

---

## Development Setup

Contributions are welcome. Here's how to get a local development environment running in under five minutes.

### Prerequisites

- Python **3.10 or higher**
- Git
- Windows 10/11 (the pipeline relies on Windows-specific binaries and `subprocess` flags)
- CUDA-capable GPU *(optional but strongly recommended for COLMAP and Lichtfeld)*

### Clone & Install

```bash
# 1. Clone the repository
git clone https://github.com/your-username/AutoSplat_Studio.git
cd AutoSplat_Studio

# 2. Create and activate the virtual environment
python -m venv venv
venv\Scripts\activate

# 3. Install Python dependencies
pip install -r requirements.txt
```

### Run in Development Mode

```bash
# Activate the venv if not already active
venv\Scripts\activate

# Launch the application (with console output for debugging)
python main.pyw
```

> All logs from the pipeline runners (`core/`) will stream directly to your terminal, making it easy to debug COLMAP output, regex parsers, or progress callbacks.

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
│   ├── usd_exporter.py       ← USDZ export runner
│   └── pipeline.py           ← PipelineOrchestrator: coordinates all steps
│
├── ui/                       ← CustomTkinter interface — no business logic
│   ├── theme.py              ← Color palette & BentoCard widget
│   ├── callbacks.py          ← PipelineCallbacks dataclass
│   ├── settings_window.py    ← Modal settings window
│   └── app.py                ← AutoSplatApp main window
│
├── bin/                      ← Third-party binaries (not committed to git)
│   ├── colmap/               ← COLMAP x64 Windows (CUDA build)
│   ├── lichtfeld/            ← Lichtfeld Studio portable
│   ├── ffmpeg.exe
│   └── config.json
│
└── temp_projects/            ← Generated project folders (gitignored)
```

### Key Design Decision: The Callback Bridge

The most important architectural pattern in this codebase is **`core/callbacks.py`**.

Every pipeline runner (`colmap_runner`, `lichtfeld_runner`, etc.) receives a `PipelineCallbacks` object at runtime instead of accessing UI widgets directly. This means:

- The entire `core/` package can be imported and tested without a display.
- Progress reporting, cancellation signals, and live previews are **injected** — not hardcoded.
- Swapping the UI toolkit (e.g. from CustomTkinter to PyQt) requires changing only `ui/app.py`.

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

| Component | Technology | Purpose |
|---|---|---|
| UI Framework | [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) | Modern dark-mode desktop interface |
| 3D Reconstruction | [COLMAP](https://colmap.github.io/) | Feature extraction, matching, SfM mapping |
| Gaussian Training | [Lichtfeld Studio](https://github.com/MrNeRF/LichtFeld-Studio) | 3D Gaussian Splat training |
| Image Processing | [OpenCV](https://opencv.org/) | Frame extraction, Laplacian blur filtering |
| Video Handling | [FFmpeg](https://ffmpeg.org/) | Video decoding & media utilities |
| USD Export | [USD Python](https://openusd.org/) | `.ply` → `.usdz` conversion |
| Drag & Drop | [tkinterdnd2](https://github.com/pmgagne/tkinterdnd2) | Native file drag & drop support |

---

## Roadmap

- [ ] Linux / macOS support (decoupling Windows-specific `creationflags`)
- [ ] Batch processing — queue multiple videos in one session
- [ ] Model preview — embedded `.ply` viewer inside the app
- [ ] Cloud export — direct upload to Sketchfab / Polycam-compatible formats
- [ ] Plugin architecture — drop-in support for alternative trainers (3DGS, Mip-Splatting)

---

## Contributing

All contributions are welcome — whether it's a bug report, a new feature, or a documentation fix.

Please open an [issue](../../issues) before submitting a large pull request so we can align on the approach. For smaller fixes, feel free to open a PR directly.

This project follows standard Python conventions (`PEP 8`) and the architectural separation described above. New pipeline steps should live in `core/`, new widgets in `ui/`.

---

## License

Distributed under the **MIT License**. See [`LICENSE`](./LICENSE) for full terms.

---

<div align="center">

Built with ☕ and an unreasonable love for point clouds.

</div>
