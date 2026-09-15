$ErrorActionPreference = 'Stop'
python scripts/prepare_msix.py
if ($LASTEXITCODE -ne 0) { throw 'MSIX staging failed' }
$makeappx = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\makeappx.exe" | Sort-Object FullName -Descending | Select-Object -First 1
if (!$makeappx) { throw 'Windows SDK MakeAppx is required' }
New-Item -ItemType Directory -Force Output/store | Out-Null
& $makeappx.FullName pack /d build/msix-stage /p Output/store/Verisade.msix /o
if ($LASTEXITCODE -ne 0) { throw 'MakeAppx validation/packaging failed' }
# Round-trip to verify the actual package, not just the staging directory.
& $makeappx.FullName unpack /p Output/store/Verisade.msix /d build/msix-inspect /o
if ($LASTEXITCODE -ne 0) { throw 'MSIX round-trip failed' }
python scripts/verify_msix.py
if ($LASTEXITCODE -ne 0) { throw 'MSIX payload verification failed' }
