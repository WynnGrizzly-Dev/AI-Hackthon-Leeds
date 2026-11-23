# Builds the Windows app (needs: pip install -r requirements.txt pyinstaller)
param([string]$Python = "python", [string]$Out = "dist")
& $Python -m PyInstaller --noconfirm --windowed --name EyeGuard --collect-data mediapipe --collect-binaries mediapipe --exclude-module jax --exclude-module jaxlib --distpath $Out --workpath "$Out\work" --specpath "$Out\work" "$PSScriptRoot\eye_guard.py"
