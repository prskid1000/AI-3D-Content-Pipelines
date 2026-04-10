@echo off
cd /d %~dp0
python ComfyUI\main.py --listen --async-offload 16 --cache-none --disable-smart-memory --reserve-vram 0.3 --port 8189
pause
