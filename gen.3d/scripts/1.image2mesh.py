"""
Process all image files from input folder and generate 3D meshes (GLB) to output folder.
Uses ComfyUI Trellis2 workflow: one image -> one mesh per image.
"""
import os
import sys
import time
import json
import shutil
import argparse
from pathlib import Path
from functools import partial
import builtins as _builtins
import requests
from PIL import Image

print = partial(_builtins.print, flush=True)

# Scale image so max(width, height) == this before sending to ComfyUI (aspect ratio preserved)
MAX_IMAGE_SIZE = 1024

# Resumable processing (skip already-generated meshes, resume after interrupt)
ENABLE_RESUMABLE_MODE = True
CLEANUP_TRACKING_FILES = False  # Set True to delete tracking JSON after successful run

# Supported image extensions (lowercase)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tga"}


def resolve_comfyui_dir(base_dir: str) -> str:
    """Resolve ComfyUI directory: sibling ComfyUI or COMFYUI_DIR env."""
    candidate = os.path.abspath(os.path.join(base_dir, "..", "ComfyUI"))
    if os.path.exists(os.path.join(candidate, "main.py")):
        return candidate
    alt = os.environ.get("COMFYUI_DIR")
    if alt and os.path.exists(os.path.join(alt, "main.py")):
        return alt
    return candidate


def get_image_files(input_dir: str) -> list[tuple[str, str]]:
    """
    Return list of (full_path, stem) for all image files in input_dir.
    stem = filename without extension, used for naming output.
    """
    if not os.path.isdir(input_dir):
        return []
    out = []
    for name in sorted(os.listdir(input_dir)):
        p = os.path.join(input_dir, name)
        if not os.path.isfile(p):
            continue
        ext = Path(name).suffix.lower()
        if ext in IMAGE_EXTENSIONS:
            stem = Path(name).stem
            out.append((p, stem))
    return out


class ResumableState:
    """Manages resumable state for image-to-mesh generation (skip completed, resume after interrupt)."""

    def __init__(self, checkpoint_dir: str, script_name: str, force_start: bool = False):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.checkpoint_dir / f"{script_name}.state.json"
        if force_start and self.state_file.exists():
            try:
                self.state_file.unlink()
                print("Force start enabled - removed existing checkpoint")
            except Exception as ex:
                print(f"WARNING: Failed to remove checkpoint for force start: {ex}")
        self.state = self._load_state()

    def _load_state(self) -> dict:
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as ex:
                print(f"WARNING: Failed to load checkpoint file: {ex}")
        return {"meshes": {"completed": [], "results": {}}}

    def _save_state(self):
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
        except Exception as ex:
            print(f"WARNING: Failed to save checkpoint: {ex}")

    def is_mesh_complete(self, stem: str) -> bool:
        """True if this stem was completed and the output file still exists."""
        if stem not in self.state["meshes"]["results"]:
            return False
        path = self.state["meshes"]["results"][stem].get("path", "")
        return bool(path and os.path.exists(path))

    def set_mesh_result(self, stem: str, path: str):
        self.state["meshes"]["results"][stem] = {"path": path}
        if stem not in self.state["meshes"]["completed"]:
            self.state["meshes"]["completed"].append(stem)
        self._save_state()

    def validate_and_cleanup_results(self, output_dir: str) -> int:
        """Remove completed entries whose output file no longer exists. Returns count removed."""
        removed = 0
        for stem in list(self.state["meshes"]["completed"]):
            res = self.state["meshes"]["results"].get(stem, {})
            path = res.get("path", "")
            if not path or not os.path.exists(path):
                if stem in self.state["meshes"]["completed"]:
                    self.state["meshes"]["completed"].remove(stem)
                if stem in self.state["meshes"]["results"]:
                    del self.state["meshes"]["results"][stem]
                removed += 1
        if removed:
            self._save_state()
        return removed

    def get_progress_summary(self) -> str:
        completed = len(self.state["meshes"]["completed"])
        return f"Progress: Meshes completed {completed}"

    def cleanup(self):
        try:
            if CLEANUP_TRACKING_FILES and self.state_file.exists():
                self.state_file.unlink()
                print("All operations completed - tracking file removed")
            else:
                print("All operations completed - tracking file preserved")
        except Exception as ex:
            print(f"WARNING: Error in cleanup: {ex}")


class Image2MeshGenerator:
    def __init__(
        self,
        comfyui_url: str = "http://127.0.0.1:8188/",
        workflow_path: str = None,
        comfyui_input_dir: str = None,
        comfyui_output_dir: str = None,
        output_dir: str = None,
    ):
        self.comfyui_url = comfyui_url.rstrip("/") + "/"
        script_dir = os.path.dirname(os.path.abspath(__file__))
        base_dir = os.path.dirname(script_dir)
        self.base_dir = base_dir
        self.workflow_path = workflow_path or os.path.join(base_dir, "workflow", "assets3d.json")
        comfy_dir = resolve_comfyui_dir(base_dir)
        self.comfyui_input_dir = os.path.abspath(comfyui_input_dir or os.path.join(comfy_dir, "input"))
        self.comfyui_output_dir = os.path.abspath(comfyui_output_dir or os.path.join(comfy_dir, "output"))
        self.output_dir = os.path.abspath(output_dir or os.path.join(base_dir, "output"))
        os.makedirs(self.output_dir, exist_ok=True)

    def _load_workflow(self) -> dict:
        with open(self.workflow_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _set_workflow_image_and_prefix(self, workflow: dict, image_filename: str, prefix: str) -> dict:
        """Set image input (node 13) and output filename prefix (node 35) in workflow."""
        w = json.loads(json.dumps(workflow))  # copy
        # Trellis2LoadImageWithTransparency
        for nid, node in w.items():
            if not isinstance(node, dict):
                continue
            if node.get("class_type") == "Trellis2LoadImageWithTransparency":
                node.setdefault("inputs", {})["image"] = image_filename
                break
        # PrimitiveString = base name for export prefixes (WhiteMesh, Refined, Textured)
        for nid, node in w.items():
            if not isinstance(node, dict):
                continue
            if node.get("class_type") == "PrimitiveString":
                node.setdefault("inputs", {})["value"] = prefix
                break
        return w

    def _scale_image_to_max_size(self, image_path: str, max_side: int) -> Image.Image | None:
        """Load image and scale so max(width, height) == max_side, preserving aspect ratio. Return PIL Image or None."""
        try:
            im = Image.open(image_path)
            im.load()
            # Preserve RGBA for transparency (Trellis2 can use alpha)
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA")
            w, h = im.size
            if max(w, h) <= max_side:
                return im
            scale = max_side / max(w, h)
            new_w = max(1, int(round(w * scale)))
            new_h = max(1, int(round(h * scale)))
            return im.resize((new_w, new_h), Image.Resampling.LANCZOS)
        except Exception as e:
            print(f"WARNING: Failed to load/scale image {image_path}: {e}")
            return None

    def _copy_image_to_comfyui(self, image_path: str) -> str:
        """Scale image to max 1024 on longest side (aspect ratio preserved), then save to ComfyUI input folder; return basename."""
        name = os.path.basename(image_path)
        dest = os.path.join(self.comfyui_input_dir, name)
        im = self._scale_image_to_max_size(image_path, MAX_IMAGE_SIZE)
        if im is None:
            # Fallback: copy original
            shutil.copy2(image_path, dest)
            return name
        w, h = im.size
        if w * h == 0:
            shutil.copy2(image_path, dest)
            return name
        try:
            ext = Path(name).suffix.lower()
            if ext in (".jpg", ".jpeg"):
                im = im.convert("RGB")
                im.save(dest, quality=95)
            else:
                im.save(dest)
            return name
        except Exception as e:
            print(f"WARNING: Failed to save scaled image, copying original: {e}")
            shutil.copy2(image_path, dest)
            return name

    def _queue_prompt(self, workflow: dict) -> str | None:
        """Submit workflow to ComfyUI; return prompt_id or None."""
        try:
            resp = requests.post(
                f"{self.comfyui_url}prompt",
                json={"prompt": workflow},
                timeout=120,
            )
            if resp.status_code != 200:
                print(f"ERROR: ComfyUI API returned {resp.status_code}: {resp.text[:500]}")
                return None
            data = resp.json()
            prompt_id = data.get("prompt_id")
            if not prompt_id:
                err = data.get("error", data)
                print(f"ERROR: No prompt_id in response: {err}")
                return None
            return prompt_id
        except Exception as e:
            print(f"ERROR: Failed to queue prompt: {e}")
            return None

    def _wait_for_completion(self, prompt_id: str, poll_interval: float = 2.0, max_wait_seconds: float = 3600.0) -> bool:
        """Poll ComfyUI history until this prompt is finished. Match gen.image 2.character.py behavior."""
        start = time.perf_counter()
        while True:
            elapsed = time.perf_counter() - start
            if elapsed >= max_wait_seconds:
                print(f"  WARNING: Max wait {max_wait_seconds}s reached, proceeding to copy outputs.")
                return False
            try:
                h = requests.get(f"{self.comfyui_url}history/{prompt_id}", timeout=30)
                if h.status_code == 200:
                    data = h.json()
                    if prompt_id in data:
                        status = data[prompt_id].get("status", {})
                        # Same as 2.character.py: default 0 so missing key is treated as done
                        if status.get("exec_info", {}).get("queue_remaining", 0) == 0:
                            time.sleep(2)  # Give it a moment to finish
                            return True
            except Exception as e:
                print(f"  WARNING: History poll error: {e}")
            time.sleep(poll_interval)

    def _find_newest_glb_with_prefix(self, prefix: str) -> str | None:
        """Find newest .glb in ComfyUI output that starts with prefix (e.g. myimage_Textured)."""
        if not os.path.isdir(self.comfyui_output_dir):
            return None
        latest = None
        latest_mtime = -1.0
        for root, _dirs, files in os.walk(self.comfyui_output_dir):
            for name in files:
                if not name.lower().endswith(".glb"):
                    continue
                # Match prefix: exact or prefix_ (e.g. model_Textured_00001_.glb or modelWhiteMesh_00001_.glb)
                if name.startswith(prefix) or name.startswith(prefix + "_"):
                    full = os.path.join(root, name)
                    try:
                        mtime = os.path.getmtime(full)
                    except OSError:
                        continue
                    if mtime > latest_mtime:
                        latest_mtime = mtime
                        latest = full
        return latest

    def _list_glbs_with_prefix(self, prefix: str) -> list[tuple[str, float]]:
        """List all .glb paths in ComfyUI output that start with prefix; return [(path, mtime), ...] sorted newest first."""
        if not os.path.isdir(self.comfyui_output_dir):
            return []
        found = []
        for root, _dirs, files in os.walk(self.comfyui_output_dir):
            for name in files:
                if not name.lower().endswith(".glb"):
                    continue
                if name.startswith(prefix) or name.startswith(prefix + "_"):
                    full = os.path.join(root, name)
                    try:
                        mtime = os.path.getmtime(full)
                    except OSError:
                        continue
                    found.append((full, mtime))
        return sorted(found, key=lambda x: -x[1])

    def _copy_glbs_from_comfyui_to_output(self, stem: str) -> str | None:
        """
        Find all GLB outputs for this stem in ComfyUI output and copy them to gen.3d/output.
        Copies: stem.glb (newest, usually Textured), stem_WhiteMesh.glb, stem_Refined.glb, stem_Textured.glb.
        Returns path to primary output (stem.glb) or None if none found.
        """
        os.makedirs(self.output_dir, exist_ok=True)
        print(f"  Looking for .glb in: {self.comfyui_output_dir}")
        print(f"  Copying to: {self.output_dir}")
        candidates = self._list_glbs_with_prefix(stem)
        if not candidates:
            print(f"  WARNING: No .glb files found with prefix '{stem}' in ComfyUI output.")
            return None
        primary_out = None
        seen_bases = set()
        for glb_path, _mtime in candidates:
            name = os.path.basename(glb_path)
            # Derive a clean base: model_Textured_00001_.glb -> model_Textured; modelWhiteMesh_00001_.glb -> model_WhiteMesh
            base = name.replace(".glb", "").rstrip("_")
            while base and base[-1].isdigit():
                base = base.rstrip("0123456789").rstrip("_")
            if not base.startswith(stem):
                continue
            suffix = base[len(stem):].lstrip("_") or "Textured"
            if suffix in seen_bases:
                continue
            seen_bases.add(suffix)
            out_name = f"{stem}.glb" if suffix == "Textured" else f"{stem}_{suffix}.glb"
            out_path = os.path.join(self.output_dir, out_name)
            try:
                shutil.copy2(glb_path, out_path)
                print(f"  Copied to output: {out_path}")
            except Exception as e:
                print(f"  ERROR copying {glb_path} -> {out_path}: {e}")
                continue
            if suffix == "Textured":
                primary_out = out_path
            elif primary_out is None:
                primary_out = out_path
        return primary_out

    def process_one(self, image_path: str, stem: str) -> str | None:
        """
        Process one image: copy to ComfyUI input, run workflow, then copy all result GLBs to gen.3d/output.
        Returns path to primary output GLB or None on failure.
        """
        print(f"Processing: {image_path} -> prefix '{stem}'")
        image_basename = self._copy_image_to_comfyui(image_path)
        workflow = self._load_workflow()
        workflow = self._set_workflow_image_and_prefix(workflow, image_basename, stem)

        prompt_id = self._queue_prompt(workflow)
        if not prompt_id:
            return None
        print(f"  Queued prompt_id: {prompt_id}, waiting for completion...")
        if not self._wait_for_completion(prompt_id):
            print("  WARNING: Wait timed out or failed")
        primary_out = self._copy_glbs_from_comfyui_to_output(stem)
        if not primary_out:
            print(f"  ERROR: No .glb found for prefix '{stem}' in ComfyUI output: {self.comfyui_output_dir}")
            return None
        return primary_out

    def process_all(
        self,
        input_dir: str,
        resumable_state: ResumableState | None = None,
        force_regenerate: bool = False,
    ) -> dict[str, str]:
        """Process all images in input_dir. Skips completed stems if resumable_state provided. Returns {stem: output_glb_path}."""
        images = get_image_files(input_dir)
        if not images:
            print(f"No image files found in {input_dir} (extensions: {IMAGE_EXTENSIONS})")
            return {}
        print(f"Found {len(images)} image(s) in {input_dir}")
        print(f"ComfyUI output folder: {self.comfyui_output_dir}")
        print(f"gen.3d output folder:  {self.output_dir}")

        if resumable_state:
            resumable_state.validate_and_cleanup_results(self.output_dir)
            completed_stems = {stem for image_path, stem in images if resumable_state.is_mesh_complete(stem)}
        else:
            completed_stems = set()

        to_process = [(image_path, stem) for image_path, stem in images if force_regenerate or stem not in completed_stems]
        if completed_stems and not force_regenerate:
            print(f"Resumable: skipping {len(completed_stems)} already completed: {sorted(completed_stems)}")
        if not to_process:
            print("All meshes already generated.")
            return {stem: resumable_state.state["meshes"]["results"][stem]["path"] for stem in completed_stems} if resumable_state else {}

        print(f"Processing {len(to_process)} image(s), skipped {len(completed_stems)}")
        results = {}
        for image_path, stem in to_process:
            out_path = self.process_one(image_path, stem)
            if out_path:
                results[stem] = out_path
                if resumable_state:
                    resumable_state.set_mesh_result(stem, out_path)
        # Include previously completed in results for summary
        if resumable_state:
            for stem in completed_stems:
                path = resumable_state.state["meshes"]["results"].get(stem, {}).get("path", "")
                if path and os.path.exists(path):
                    results[stem] = path
        return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert all images in input folder to 3D meshes (GLB) in output folder."
    )
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.dirname(script_dir)
    default_input = os.path.join(base_dir, "input")
    default_output = os.path.join(base_dir, "output")
    parser.add_argument(
        "--input-dir", "-i",
        default=default_input,
        help=f"Folder containing input images (default: {default_input})",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=default_output,
        help=f"Folder for output GLB files (default: {default_output})",
    )
    parser.add_argument(
        "--workflow",
        default=os.path.join(base_dir, "workflow", "assets3d.json"),
        help="Path to Trellis2 workflow JSON",
    )
    parser.add_argument(
        "--comfyui-url",
        default=os.environ.get("COMFYUI_BASE_URL", "http://127.0.0.1:8188/"),
        help="ComfyUI API base URL",
    )
    parser.add_argument("--force", "-f", action="store_true", help="Regenerate all meshes (ignore completed)")
    parser.add_argument(
        "--force-start",
        action="store_true",
        help="Ignore existing checkpoint and start fresh (resumable state cleared)",
    )
    parser.add_argument("--list-completed", "-l", action="store_true", help="List completed mesh stems and exit")
    args = parser.parse_args()

    gen = Image2MeshGenerator(
        comfyui_url=args.comfyui_url,
        workflow_path=args.workflow,
        output_dir=args.output_dir,
    )

    resumable_state = None
    if ENABLE_RESUMABLE_MODE:
        checkpoint_dir = os.path.normpath(os.path.join(base_dir, "output", "tracking"))
        script_name = Path(__file__).stem
        resumable_state = ResumableState(checkpoint_dir, script_name, args.force_start)
        print(f"Resumable mode enabled - checkpoint: {checkpoint_dir}")
        if resumable_state.state_file.exists():
            print(f"Found checkpoint: {resumable_state.state_file}")
            print(resumable_state.get_progress_summary())
        else:
            print("No checkpoint found - starting fresh")

    if args.list_completed:
        if resumable_state and resumable_state.state["meshes"]["completed"]:
            print("Completed stems:", sorted(resumable_state.state["meshes"]["completed"]))
        else:
            print("No completed meshes in checkpoint.")
        return 0

    results = gen.process_all(
        args.input_dir,
        resumable_state=resumable_state,
        force_regenerate=args.force,
    )
    if results:
        print(f"\nGenerated {len(results)} mesh(es):")
        for stem, path in results.items():
            print(f"  {stem}: {path}")
        if resumable_state:
            print("Final progress:", resumable_state.get_progress_summary())
            resumable_state.cleanup()
        return 0
    print("No meshes generated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
