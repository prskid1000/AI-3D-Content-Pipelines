@echo off
cd /d %~dp0
python ComfyUI\main.py --listen --async-offload 16 --use-flash-attention
pause
