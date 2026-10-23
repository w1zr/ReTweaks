"""Run only with user's explicit approval for the existing Gemini credential."""
from pathlib import Path
import subprocess
folder=Path(__file__).with_name('ai')
result=subprocess.run([str(folder/'CheckService.exe')],cwd=str(folder),capture_output=True,text=True,timeout=130,creationflags=0x08000000)
print(result.stdout.strip())
raise SystemExit(result.returncode)
