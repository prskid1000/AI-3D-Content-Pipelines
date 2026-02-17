# AI 3D Content Pipelines

An AI-powered pipeline that converts images into 3D meshes (GLB) using ComfyUI and the Trellis2 workflow. Place images in the input folder and run the orchestrator to generate textured 3D assets in the output folder.

## 🎯 What It Does

- **🖼️ Image → 3D** – Convert reference images (characters, objects, etc.) into 3D meshes
- **📦 Batch Processing** – Process all images in the input folder; one GLB (and variants) per image
- **📐 Input Scaling** – Images are scaled to max 1024px (longest side) with aspect ratio preserved before sending to ComfyUI
- **📂 Output Copy** – Generated GLBs are copied from ComfyUI output into `gen.3d/output` (e.g. `stem.glb`, `stem_WhiteMesh.glb`, `stem_Refined.glb`, `stem_Textured.glb`)
- **🔄 Orchestration** – `generate.py` starts ComfyUI, runs the pipeline script, then stops ComfyUI

## 🔧 System Architecture Overview

### Core Services

- **ComfyUI** (Port 8188) – AI model server for Trellis2 image-to-mesh generation
- **Trellis2** – ComfyUI custom nodes for 3D mesh generation from a single image

### Pipeline Orchestration

The `gen.3d` pipeline includes:

- **Service Management** – Automatic startup and shutdown of ComfyUI
- **Folder Cleanup** – ComfyUI input/output folders emptied before each run
- **Logging** – Execution tracking in `gen.3d/log.txt`
- **Path Resolution** – ComfyUI directory from sibling `../ComfyUI` or `COMFYUI_DIR` env

## 🏗️ System Architecture

```
Images (gen.3d/input/) → Scale (max 1024) → ComfyUI/input
                              ↓
                    ComfyUI + Trellis2 workflow
                              ↓
                    ComfyUI/output (GLB files)
                              ↓
                    Copy → gen.3d/output/
```

### Pipeline Overview

- **3D Pipeline** (`gen.3d/`) – One script: image-to-mesh via Trellis2; accepts all image files in input and writes GLBs to output.

## 📁 Project Structure

```
.comfyui.3d/
├── ComfyUI/                    # AI model server (Trellis2 custom nodes)
│   ├── models/                 # Trellis2 / 3D models
│   ├── custom_nodes/           # ComfyUI-Trellis2, etc.
│   ├── input/                  # Scaled images (filled by script)
│   └── output/                 # Raw GLB output (script copies to gen.3d/output)
├── gen.3d/                     # 3D pipeline
│   ├── generate.py             # Main orchestrator (start ComfyUI, run script, stop)
│   ├── input/                  # Your input images (.png, .jpg, .jpeg, .webp, .bmp, .tga)
│   ├── output/                 # Generated GLB meshes (copied here from ComfyUI)
│   ├── scripts/
│   │   └── 1.image2mesh.py      # Process all images → ComfyUI → copy GLBs to output
│   ├── workflow/
│   │   └── assets3d.json        # Trellis2 workflow (image → mesh → export GLB)
│   └── log.txt                 # Run log
└── README.md                   # This file
```

## 🚀 Quick Start

### Prerequisites

1. **ComfyUI** – With Trellis2 custom nodes and required models (e.g. TRELLIS.2-4B)
2. **Python** – With `requests`, `Pillow` (PIL); ComfyUI runs in its own environment
3. **ComfyUI location** – Either a sibling folder `ComfyUI` next to `gen.3d`, or set `COMFYUI_DIR` to your ComfyUI path

### Running the Pipeline

```bash
# Full run (starts ComfyUI, runs 1.image2mesh.py, stops ComfyUI)
cd gen.3d && python generate.py
```

### Running the Script Only (ComfyUI already running)

```bash
cd gen.3d/scripts
python 1.image2mesh.py

# Optional arguments
python 1.image2mesh.py --input-dir ../input --output-dir ../output
python 1.image2mesh.py --comfyui-url http://127.0.0.1:8188/
```

### Environment Variables

- **COMFYUI_DIR** – Override ComfyUI installation path (default: `gen.3d/../ComfyUI`)
- **COMFYUI_BASE_URL** – ComfyUI API base URL (default: `http://127.0.0.1:8188/`)

## 📋 Script Inventory

| # | Script | Purpose | Input | Output | Dependencies |
|---|--------|---------|--------|--------|---------------|
| 1 | `1.image2mesh.py` | Image → 3D mesh (batch) | `gen.3d/input/*` (images) | `gen.3d/output/*.glb` | ComfyUI (Trellis2) |

### Key Features

- **Input** – All image files in `gen.3d/input` (extensions: `.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`, `.tga`)
- **Scaling** – Each image scaled so max(width, height) = 1024 before sending to ComfyUI
- **Naming** – Output GLBs use the image filename stem (e.g. `robot_model.png` → `robot_model.glb`, `robot_model_Textured.glb`, etc.)
- **Copy** – All Trellis2 export variants (WhiteMesh, Refined, Textured) are copied from ComfyUI output to `gen.3d/output`
- **Wait for completion** – Script polls ComfyUI history until the prompt finishes (with timeout), then copies outputs and exits
