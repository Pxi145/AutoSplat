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

> **AutoSplat Studio** is a desktop application for Windows that automates the entire photogrammetry pipeline — from raw footage to a fully trained **Gaussian Splat model** — with no command-line knowledge required.  **Drop a video**. Press a button. **Get a `.ply`**.

---

<div align="center">

![AutoSplat Studio Interface](./ressources/AutoSplat_workflow.gif)

*The AutoSplat Studio interface — drag a video or image folder, monitor real-time extraction, and track each pipeline step from a single window.*

</div>

---

## ⬇️ Download & Install

> **Just want to use the app? This is the only section you need.**

**[⬇️ Download AutoSplat Studio — Full Package (~4 GB)](https://mega.nz/file/8ccByJTR#2WN_eFzrg9xjen6zYniXYVN0w1u86FB-2YtqA-VAkkI)**

The archive contains everything — the app, COLMAP, Lichtfeld Studio 0.5.0, and FFmpeg already in place. No separate downloads, no manual configuration.

**Once downloaded:**

1. Extract the `.zip` anywhere on your machine *(e.g. `C:\Tools\AutoSplat\`)*
2. Double-click **`setup.bat`** — installs Python dependencies automatically, wait for the venv to be created
3. Double-click **`AutoSplat_Studio.vbs`** — the app opens, you're ready to splat

> **Requirement:** Python 3.12+ must be installed on your machine.
> Download it at [python.org](https://www.python.org/downloads/release/python-3120/) and check **"Add to PATH"** during installation.

That's it. No terminal, no configuration, no manual setup.

---

## Why AutoSplat Studio?

Gaussian Splatting is one of the most powerful 3D reconstruction techniques available today, but the toolchain is fragmented, technical, and unforgiving. You need COLMAP for reconstruction, a separate trainer for splatting, and FFmpeg for video handling. Each tool has its own CLI, its own quirks, and its own failure modes.

**AutoSplat Studio exists to remove all of that friction.**

### Core Principles

- 🎯 &nbsp;**One window, one button.** The entire pipeline — extraction, reconstruction, training — runs from a single interface with zero terminal interaction, watch the console to folow the progress simply.
- 🔍 &nbsp;**Smart filtering.** The choice of the number of frames + Laplacian blur filter ensures only the sharpest frames enter COLMAP, directly improving reconstruction quality.
- 🚀 &nbsp;**Advanced Engine Integration.** Powered by COLMAP 4.0.2 (featuring GLOMAP and ALIKED AI extractors) and LichtFeld Studio 0.5.0 (with advanced tile rendering and anti-aliasing) to deliver cutting-edge reconstruction speed and quality.
- 🔌 &nbsp;**Decoupled by design.** The core pipeline (COLMAP, OpenCV, Lichtfeld) is fully independent from the UI layer — making it testable, scriptable, and extensible without touching a single widget.
- 🔄 &nbsp;**Resumable at every stage.** Interrupted mid-run?! Resume from the Mapper **or** jump straight to Lichtfeld training without starting over.
- 📦 &nbsp;**Export-ready output.** Beyond `.ply`, Lichtfeld's built-in exporter converts your splat to **`.html`** (shareable web viewer) and **`.spz`** (compressed splat format), ~~**`.usd`**~~ not currently working.

---

## Available Parameters

AutoSplat Studio exposes a comprehensive set of parameters via its main interface and advanced settings menu, giving you full control over every step of the pipeline.

### Frames
| Parameter | Description |
| :--- | :--- |
| **Target FPS** | The frequency at which to extract frames from a video source. 2-5 fps recommended |
| **Anti-Blur Filter** | A dynamic Laplacian variance threshold. Images below this sharpness score are automatically discarded. |

### How it work
The video is split into equal time packets by the target fps. From each packet, **the sharpest frame** (highest variance number) is selected:

```
Timeline with sharpness scores:
┌──────────────────────────────────┬──────────────────────────────────┬─────┐
│ Packet 1 (frames 0–14)           │ Packet 2 (frames 15–29)          │ ... │
│ 85  92  76  113 ← BEST           │ 62  91  75  142 ← BEST           │     │
│ 88  79  95   81 ...              │ 54  88  120  68 ...              │     │
└──────────────────────────────────┴──────────────────────────────────┴─────┘
```
The **Anti-Blur Filter** acts as a quality gate: frames below it are not choosen, even if they're the best in their packet. Higher numbers = sharper images but potentialy fewer.

**Why set it low (2–15)?** You'll keep your target FPS while guaranteeing every saved frame is the sharpest available from its time slot. 

**Low threshold = most packets pass** → set fps images. **High threshold (50+) = only perfect frames** → fewer images.
### COLMAP 4.0
| Parameter | Options / Description |
| :--- | :--- |
| **Reconstruction Mode** | **`Incremental (Standard)`**: Classic, robust 3D reconstruction.<br>**`Global GLOMAP (Faster)`**: Faster reconstruction for large datasets. |
| **Feature Extraction** | **`SIFT (Standard)`**: Classic feature extractor.<br>**`ALIKED N16 (IA Light)`**: Fast AI-powered extraction.<br>**`ALIKED N32 (IA Precise)`**: High-precision AI extraction. |
| **Matching Mode** | **`Sequential`**: For videos (chronological frames).<br>**`Exhaustive`**: For unordered photo sets. |
| **Matcher Overlap** | Number of adjacent frames to compare during sequential matching. |
| **Camera Model** | Supports `OPENCV`, `SIMPLE_RADIAL`, `PINHOLE`, `FISHEYE`, `DIVISION`, etc. |

### Gaussian Splat Training
| Parameter | Options / Description |
| :--- | :--- |
| **Iterations** | Total number of training steps. |
| **Training Strategy** | **`mrnf`** (Standard), **`mcmc`** (High Quality), **`igs+`** (Advanced). |
| **Resolution Resize** | Downscale input images to save VRAM (`auto`, `1`, `2`, `4`, `8`). |
| **Tile Mode (VRAM)** | Control GPU memory usage (`1 Default`, `2 Medium`, `4 Economy`). |
| **Maximum Splats** | Hard cap on the total number of Gaussians generated. |
| **Export Format** | Choose format for native export (`usd`, `usda`, `usdc`, `spz`, `html`). |
| **MIP Anti-aliasing** | Enable multi-resolution filtering for smoother distant viewing. |
| **GUT (3DGUT)** | Enable Gaussian Unscented Transform to train directly on distorted lenses. |

The **Settings** are save in the **`bin/config.json`** overriding the base settings of the app.

### Heavy files management
| Parameter | Description |
| :--- | :--- |
| **Auto-Cleanup** | Automatically delete heavy intermediate files (raw images, COLMAP db) after successful training, keeping only the final 3D model. |

---

## AutoSplat Workflow

```
              Video  or  Image Folder
                       │
                       ▼
  ┌───────────────────────────────────────────┐
  │  Smart Frame Extraction + Blur Filtering  │
  └───────────────────────────────────────────┘
      Choose how many frame you want to keep
       And the minimum sharpness authorized
                       │
                       ▼
         ┌─────────────────────────────┐
         │  COLMAP / GLOMAP  Pipeline  │  
         └─────────────────────────────┘
Feature Extraction → Matching → Mapper → Undistortion
    The result in output_gs ready for lichtFeld
                       │
                       ▼
         ┌─────────────────────────────┐
         │  Gaussian Splat Training    │
         └─────────────────────────────┘
        Lichtfeld Studio (mcmc / igs+ ...)
                      │
                      ▼
          📄.ply  · 🌐.html  · 📦.spz 
```

---

## For Developers

> The following sections are intended for contributors who want to work on the source code, modify the pipeline, or build on top of AutoSplat Studio.

### What's in this repository

This GitHub repo contains **only the source code**. The compiled binaries (COLMAP, Lichtfeld Studio, FFmpeg) are not committed here — they are included in the full package download.

If you clone this repo, you will need to populate `bin/` manually (see below).

### Prerequisites

- **Python 3.12+** — [python.org](https://www.python.org/downloads/release/python-3120/)
- **Git**
- **Windows 10/11**
- **CUDA-capable GPU** *(Work for Nvidia GPU only)*

### Clone & Setup

```bash
# 1. Clone the repository
git clone https://github.com/Pxi145/AutoSplat.git
cd AutoSplat

# 2. Run the automated setup
setup.bat
```

### Populate the `bin/` folder

After cloning, your `bin/` folder will be empty of the working elements. You need to fill it with the three binaries before the app can run.

**Option A — Quickest:** Download the [full package](https://mega.nz/file/8ccByJTR#2WN_eFzrg9xjen6zYniXYVN0w1u86FB-2YtqA-VAkkI), extract it, and copy only the `bin/` folder into your cloned repo.

**Option B — Manual:** Download each binary separately and place them in the correct folders:

| Binary | Source | Expected path |
|---|---|---|
| COLMAP x64 Windows CUDA | [colmap.github.io](https://github.com/colmap/colmap/releases) | `bin/colmap-x64-windows-cuda/` |
| Lichtfeld Studio | [github.com/MrNeRF/LichtFeld-Studio](https://github.com/MrNeRF/LichtFeld-Studio#installation) | `bin/LichtFeld-Studio/` |
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
For developpers and non developpers there is a `pipeline.log` file where everything is loged for debugging a run or looking at numbers.

### Project Structure

```
AutoSplat_Studio/
├── AutosSplat_Studio.vbs     ← executable for using the app
├── main.pyw                  ← main script for the app
├── setup.bat                 ← One-click environment setup (only once)
├── requirements.txt
│
├── config/                   ← Configuration management (load/save /config.json)
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
├── ui/                       ← CustomTkinter interface
│   ├── theme.py              ← Color palette & BentoCard widget
│   ├── callbacks.py          ← PipelineCallbacks dataclass
│   ├── settings_window.py    ← Modal settings window
│   └── app.py                ← AutoSplatApp main window
│
├── bin/                      ← Third-party binaries
│   ├── colmap-x64-windows-cuda/
│   ├── LichtFeld-Studio/
│   ├── ffmpeg.exe
│   ├── config.json           ← The JSON that saves your settings
│   └── Icone.ico
│
└── temp_projects/            ← Generated project folders
```

### Key Design Decisions

**1. The Callback Bridge (UI / Core Separation)**
The most important architectural pattern in this codebase is **`core/callbacks.py`**.
Every pipeline runner receives a `PipelineCallbacks` object at runtime instead of accessing UI widgets directly. This means:

- The entire `core/` package can be imported and tested **without a display**.
- Progress reporting, cancellation signals, and live previews are **injected**.
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
**2. Subprocess Wrappers & Real-Time Parsing**
AutoSplat does not hook into COLMAP or Lichtfeld via C++ bindings. Instead, it runs them as asynchronous background processes via `subprocess.Popen`. 
- `core/colmap_runner.py` and `core/lichtfeld_runner.py` intercept the standard output (`stdout`) of these engines in real-time.
- Regular expressions (Regex) parse the terminal output to extract current progress, loss values, and splat counts, streaming them back to the UI via the Callback Bridge.
- *Note:* Lichtfeld outputs raw ANSI escape codes (colors, cursor movements), which are stripped on-the-fly to keep the regex parsing robust.

**3. Project-Based File Lifecycle**
Every run is isolated into a self-contained folder within `temp_projects/` (or a custom path). The pipeline operates sequentially on this folder:
1. `images/` - Extracted and filtered frames.
2. `database.db` - The COLMAP SQLite database.
3. `sparse_raw/` - The raw sparse 3D reconstruction.
4. `output_gs/` - Undistorted images prepared for splatting.
5. `splat_model/` - The final trained Gaussian model.
If **Auto-Cleanup** is enabled, intermediate files (1-4) are deleted automatically, leaving only `splat_model/` and the comprehensive `pipeline.log`.

---
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

New pipeline steps belong in `core/`, new widgets in `ui/`.

---

## License

Distributed under the **MIT License**. Do what you want with my code it's free and don't forget to support the projects that are used here.

---

<div align="center">

Built with AI and a compulsive obsession for turning everything into Gaussian.

</div>
