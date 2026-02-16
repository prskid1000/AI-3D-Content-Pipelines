@Echo off&&cd /D %~dp0
set "CEI_Title=..comfyui.3d by ivo v2.04.1"
Title %CEI_Title%
call :set_colors

set "VENV_PY=%~dp0.venv\Scripts\python.exe"
if not exist "%~dp0.venv\Scripts\python.exe" (
	echo %green%Creating .venv...%reset%
	py -3.12 -m venv "%~dp0.venv" 2>nul
	if errorlevel 1 py -m venv "%~dp0.venv" 2>nul
)
if not exist "%~dp0.venv\Scripts\python.exe" (
	echo %warning%.venv not found. Install Python 3.12 and run again.%reset%
	pause&exit /b 1
)

set GIT_LFS_SKIP_SMUDGE=1
set "PIPargs=--no-cache-dir --no-warn-script-location --timeout=1000 --retries 10"
set "UVargs=--no-cache --link-mode=copy"

for /f "delims=" %%G in ('cmd /c "where.exe git.exe 2>nul"') do set "GIT_PATH=%%~dpG"
set "path=%GIT_PATH%"
if exist "%windir%\System32" set "path=%PATH%;%windir%\System32"
if exist "%windir%\System32\WindowsPowerShell\v1.0" set "path=%PATH%;%windir%\System32\WindowsPowerShell\v1.0"
if exist "%localappdata%\Microsoft\WindowsApps" set "path=%PATH%;%localappdata%\Microsoft\WindowsApps"

rem ComfyUI may already exist; clone step will be skipped in :install_comfyui

set "SCRIPT_ROOT=%~dp0"
set "SITE_PACKAGES=%SCRIPT_ROOT%.venv\Lib\site-packages"

for /f "delims=" %%i in ('powershell -command "Get-Date -Format yyyy-MM-dd_HH:mm:ss"') do set start=%%i
echo %green%..comfyui.3d%reset%
echo.

call :install_git
for /F "tokens=*" %%g in ('git --version') do set gitversion=%%g
Echo %gitversion% | findstr /C:"version">nul || (
	echo %warning%git is NOT installed. Install from https://git-scm.com and run again.%reset%
	pause&exit /b 1
)
echo %bold%git%reset% %yellow%OK%reset%
echo.

call :install_comfyui

echo %green%Pre-install modules%reset%
"%VENV_PY%" -I -m pip install scikit-build-core %PIPargs%
"%VENV_PY%" -I -m pip install onnxruntime-gpu onnx %PIPargs%
"%VENV_PY%" -I -m uv pip install flet %UVargs%
"%VENV_PY%" -I -m pip install https://github.com/JamePeng/llama-cpp-python/releases/download/v0.3.24-cu128-Basic-win-20260208/llama_cpp_python-0.3.24+cu128.basic-cp312-cp312-win_amd64.whl %PIPargs%
"%VENV_PY%" -I -m uv pip install stringzilla==3.12.6 transformers==4.57.6 %UVargs%
echo %green%accelerate (>=0.17.0 for enable_model_cpu_offload, torch 2.8 compatible)%reset%
"%VENV_PY%" -I -m pip install "accelerate>=0.17.0" %PIPargs%
echo.

call :get_node https://github.com/Comfy-Org/ComfyUI-Manager comfyui-manager
call :get_node https://github.com/city96/ComfyUI-GGUF ComfyUI-GGUF
call :get_node https://github.com/1038lab/ComfyUI-RMBG comfyui-rmbg
call :get_node https://github.com/kijai/ComfyUI-KJNodes comfyui-kjnodes

if not exist ".\ComfyUI\custom_nodes\.disabled" mkdir ".\ComfyUI\custom_nodes\.disabled"

call :install_flash_attention
call :install_cubvh
call :install_trellis2
call :download_trellis_microsoft_ckpts
call :install_ultrashape

for /f "delims=" %%i in ('powershell -command "Get-Date -Format yyyy-MM-dd_HH:mm:ss"') do set end=%%i
for /f "delims=" %%i in ('powershell -command "$s=[datetime]::ParseExact('%start%','yyyy-MM-dd_HH:mm:ss',$null); $e=[datetime]::ParseExact('%end%','yyyy-MM-dd_HH:mm:ss',$null); if($e -lt $s){$e=$e.AddDays(1)}; ($e-$s).TotalSeconds"') do set diff=%%i
echo %green%Done. Time: %diff%s%reset%
pause
exit

:set_colors
for /F "delims=" %%a in ('powershell -nop -c "[char]27"') do set "ESC=%%a"
set "warning=%ESC%[33m"
set "red=%ESC%[91m"
set "green=%ESC%[92m"
set "yellow=%ESC%[93m"
set "bold=%ESC%[1m"
set "reset=%ESC%[0m"
goto :eof

:install_flash_attention
echo %green%FlashAttention%reset%
"%VENV_PY%" -I -m pip uninstall flash-attn -y 2>nul
"%VENV_PY%" -I -m pip install --upgrade --force-reinstall triton-windows==3.4.0.post20 %PIPargs%
"%VENV_PY%" -I -m pip install https://github.com/kingbri1/flash-attention/releases/download/v2.8.3/flash_attn-2.8.3+cu128torch2.8.0cxx11abiFALSE-cp312-cp312-win_amd64.whl %PIPargs% --use-pep517
goto :eof

:erase_folder
if exist "%~1" rmdir /s /q "%~1"
goto :eof

:install_cubvh
echo %green%cubvh%reset%
if not exist "%~dp0cubvh" (
	git clone --recursive https://github.com/ashawkey/cubvh "%~dp0cubvh"
)
if exist "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" (
	call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
)
pushd "%~dp0cubvh"
"%VENV_PY%" -m pip install . --no-build-isolation %PIPargs%
popd
goto :eof

:install_trellis2
set "model_folder=ComfyUI\models\facebook\dinov3-vitl16-pretrain-lvd1689m"
set "model_url=https://huggingface.co/PIA-SPACE-LAB/dinov3-vitl-pretrain-lvd1689m/resolve/main/model.safetensors"
set "config_url=https://huggingface.co/PIA-SPACE-LAB/dinov3-vitl-pretrain-lvd1689m/resolve/main/config.json"
set "pre_config_url=https://huggingface.co/PIA-SPACE-LAB/dinov3-vitl-pretrain-lvd1689m/resolve/main/preprocessor_config.json"
powershell -Command "[System.Net.ServicePointManager]::CheckCertificateRevocationList = $false"
if not exist "%model_folder%" mkdir "%model_folder%"
setlocal enabledelayedexpansion
if exist "%model_folder%\model.safetensors" (
	powershell -Command "(Get-Item '%model_folder%\model.safetensors').Length" > "%TEMP%\cei_tmp_size.txt"
	for /f %%S in ("%TEMP%\cei_tmp_size.txt") do set "fsize=%%S"
	if !fsize! LSS 1212559800 del "%model_folder%\model.safetensors"
	del "%TEMP%\cei_tmp_size.txt" 2>nul
)
endlocal
echo %green%DINOv3 model%reset%
powershell -Command "Start-BitsTransfer -Source '%model_url%' -Destination '%model_folder%\model.safetensors'" 2>nul
powershell -Command "Start-BitsTransfer -Source '%config_url%' -Destination '%model_folder%\config.json'" 2>nul
powershell -Command "Start-BitsTransfer -Source '%pre_config_url%' -Destination '%model_folder%\preprocessor_config.json'" 2>nul
if exist "%SITE_PACKAGES%\~*" powershell -Command "Get-ChildItem '%SITE_PACKAGES%' -Directory -ErrorAction SilentlyContinue | Where-Object {$_.Name -like '~*'} | Remove-Item -Recurse -Force"
call :erase_folder "%SITE_PACKAGES%\o_voxel"
call :erase_folder "%SITE_PACKAGES%\o_voxel-0.0.1.dist-info"
call :erase_folder "%SITE_PACKAGES%\cumesh"
call :erase_folder "%SITE_PACKAGES%\cumesh-0.0.1.dist-info"
call :erase_folder "%SITE_PACKAGES%\nvdiffrast"
call :erase_folder "%SITE_PACKAGES%\nvdiffrast-0.4.0.dist-info"
call :erase_folder "%SITE_PACKAGES%\nvdiffrec_render"
call :erase_folder "%SITE_PACKAGES%\nvdiffrec_render-0.0.0.dist-info"
call :erase_folder "%SITE_PACKAGES%\flex_gemm"
call :erase_folder "%SITE_PACKAGES%\flex_gemm-0.0.1.dist-info"
echo %green%ComfyUI-Trellis2%reset%
if not exist "ComfyUI\custom_nodes\ComfyUI-Trellis2" (
	git.exe clone https://github.com/visualbruno/ComfyUI-Trellis2 ComfyUI\custom_nodes\ComfyUI-Trellis2
)
if exist "ComfyUI\custom_nodes\ComfyUI-Trellis2" (
	if exist "ComfyUI\custom_nodes\ComfyUI-Trellis2\requirements.txt" (
		call "%VENV_PY%" -I -m pip install -r ComfyUI\custom_nodes\ComfyUI-Trellis2\requirements.txt --no-deps %PIPargs%
	)
	call "%VENV_PY%" -I -m pip install --upgrade open3d %PIPargs%
	call "%VENV_PY%" -I -m pip install ComfyUI\custom_nodes\ComfyUI-Trellis2\wheels\Windows\Torch280\cumesh-0.0.1-cp312-cp312-win_amd64.whl ComfyUI\custom_nodes\ComfyUI-Trellis2\wheels\Windows\Torch280\nvdiffrast-0.4.0-cp312-cp312-win_amd64.whl ComfyUI\custom_nodes\ComfyUI-Trellis2\wheels\Windows\Torch280\nvdiffrec_render-0.0.0-cp312-cp312-win_amd64.whl ComfyUI\custom_nodes\ComfyUI-Trellis2\wheels\Windows\Torch280\flex_gemm-0.0.1-cp312-cp312-win_amd64.whl ComfyUI\custom_nodes\ComfyUI-Trellis2\wheels\Windows\Torch280\o_voxel-0.0.1-cp312-cp312-win_amd64.whl %PIPargs%
	powershell -Command "Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/visualbruno/CuMesh/main/cumesh/remeshing.py' -OutFile '%SITE_PACKAGES%\cumesh\remeshing.py'" 2>nul
	call "%VENV_PY%" -I -m pip install --force-reinstall numpy==1.26.4 --no-deps %PIPargs%
)
goto :eof

:download_trellis_microsoft_ckpts
echo %green%TRELLIS microsoft ckpts (missing only)%reset%
powershell -Command "[System.Net.ServicePointManager]::CheckCertificateRevocationList = $false"
set "base_hf=https://huggingface.co/microsoft"
set "dir_24b=ComfyUI\models\microsoft\TRELLIS.2-4B\ckpts"
set "dir_large=ComfyUI\models\microsoft\TRELLIS-image-large\ckpts"
if not exist "%dir_24b%" mkdir "%dir_24b%"
if not exist "%dir_large%" mkdir "%dir_large%"
for %%F in (shape_dec_next_dc_f16c32_fp16.json shape_dec_next_dc_f16c32_fp16.safetensors shape_enc_next_dc_f16c32_fp16.json shape_enc_next_dc_f16c32_fp16.safetensors slat_flow_img2shape_dit_1_3B_1024_bf16.json slat_flow_img2shape_dit_1_3B_1024_bf16.safetensors slat_flow_img2shape_dit_1_3B_512_bf16.json slat_flow_img2shape_dit_1_3B_512_bf16.safetensors slat_flow_imgshape2tex_dit_1_3B_1024_bf16.json slat_flow_imgshape2tex_dit_1_3B_1024_bf16.safetensors slat_flow_imgshape2tex_dit_1_3B_512_bf16.json slat_flow_imgshape2tex_dit_1_3B_512_bf16.safetensors ss_flow_img_dit_1_3B_64_bf16.json ss_flow_img_dit_1_3B_64_bf16.safetensors tex_dec_next_dc_f16c32_fp16.json tex_dec_next_dc_f16c32_fp16.safetensors tex_enc_next_dc_f16c32_fp16.json tex_enc_next_dc_f16c32_fp16.safetensors) do (
  if not exist "%dir_24b%\%%F" (
    echo Downloading TRELLIS.2-4B\ckpts\%%F
    powershell -Command "Start-BitsTransfer -Source '%base_hf%/TRELLIS.2-4B/resolve/main/ckpts/%%F' -Destination '%dir_24b%\%%F'" 2>nul
  )
)
for %%F in (slat_dec_gs_swin8_B_64l8gs32_fp16.json slat_dec_gs_swin8_B_64l8gs32_fp16.safetensors slat_dec_mesh_swin8_B_64l8m256c_fp16.json slat_dec_mesh_swin8_B_64l8m256c_fp16.safetensors slat_dec_rf_swin8_B_64l8r16_fp16.json slat_dec_rf_swin8_B_64l8r16_fp16.safetensors slat_enc_swin8_B_64l8_fp16.json slat_enc_swin8_B_64l8_fp16.safetensors slat_flow_img_dit_L_64l8p2_fp16.json slat_flow_img_dit_L_64l8p2_fp16.safetensors ss_dec_conv3d_16l8_fp16.json ss_dec_conv3d_16l8_fp16.safetensors ss_enc_conv3d_16l8_fp16.json ss_enc_conv3d_16l8_fp16.safetensors ss_flow_img_dit_L_16l8_fp16.json ss_flow_img_dit_L_16l8_fp16.safetensors) do (
  if not exist "%dir_large%\%%F" (
    echo Downloading TRELLIS-image-large\ckpts\%%F
    powershell -Command "Start-BitsTransfer -Source '%base_hf%/TRELLIS-image-large/resolve/main/ckpts/%%F' -Destination '%dir_large%\%%F'" 2>nul
  )
)
goto :eof

:install_ultrashape
set "model_folder=ComfyUI\models\ultrashape"
set "model_url=https://huggingface.co/infinith/UltraShape/resolve/main/ultrashape_v1.pt"
set "model_name=ultrashape_v1.pt"
powershell -Command "[System.Net.ServicePointManager]::CheckCertificateRevocationList = $false"
if not exist "%model_folder%" mkdir "%model_folder%"
echo %green%UltraShape model%reset%
powershell -Command "Start-BitsTransfer -Source '%model_url%' -Destination '%model_folder%\%model_name%'" 2>nul
echo %green%ComfyUI-UltraShape%reset%
if not exist "ComfyUI\custom_nodes\ComfyUI-UltraShape" (
	git.exe clone https://github.com/Rizzlord/ComfyUI-UltraShape ComfyUI\custom_nodes\ComfyUI-UltraShape
)
if exist "ComfyUI\custom_nodes\ComfyUI-UltraShape" (
	"%VENV_PY%" -I -m pip install "accelerate>=0.17.0" trimesh omegaconf einops pymeshlab rembg pytorch-lightning %PIPargs%
)
goto :eof

:install_git
echo %green%Git%reset%
winget.exe install --id Git.Git -e --source winget 2>nul
set "path=%PATH%;%ProgramFiles%\Git\cmd"
goto :eof

:install_comfyui
echo %green%ComfyUI%reset%
if not exist "ComfyUI" (
	git.exe clone https://github.com/Comfy-Org/ComfyUI ComfyUI
)
powershell -Command "[System.Net.ServicePointManager]::CheckCertificateRevocationList = $false"
"%VENV_PY%" -I -m pip install uv==0.9.7 %PIPargs%
"%VENV_PY%" -I -m pip install torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128 %PIPargs%
"%VENV_PY%" -I -m uv pip install pygit2 %UVargs%
cd ComfyUI
"%VENV_PY%" -I -m uv pip install av==16.0.1 %UVargs%
"%VENV_PY%" -I -m uv pip install -r requirements.txt %UVargs%
cd ..\
goto :eof

:get_node
set "git_url=%~1"
set "git_folder=%~2"
echo %green%%git_folder%%reset%
if not exist "ComfyUI\custom_nodes\%git_folder%" (
	git.exe clone %git_url% ComfyUI/custom_nodes/%git_folder%
)
setlocal enabledelayedexpansion
if exist ".\ComfyUI\custom_nodes\%git_folder%\requirements.txt" (
	for %%F in (".\ComfyUI\custom_nodes\%git_folder%\requirements.txt") do set "sz=%%~zF"
	if not !sz! equ 0 call "%VENV_PY%" -I -m uv pip install -r ".\ComfyUI\custom_nodes\%git_folder%\requirements.txt" %UVargs%
)
if exist ".\ComfyUI\custom_nodes\%git_folder%\install.py" (
	for %%F in (".\ComfyUI\custom_nodes\%git_folder%\install.py") do set "sz=%%~zF"
	if not !sz! equ 0 call "%VENV_PY%" -I ".\ComfyUI\custom_nodes\%git_folder%\install.py"
)
endlocal
goto :eof
