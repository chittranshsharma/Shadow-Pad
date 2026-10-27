$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}

& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& '.\.venv\Scripts\python.exe' download_model.py
if ($LASTEXITCODE -ne 0) { throw 'Model download failed.' }
& '.\.venv\Scripts\python.exe' download_model.py --variant hands
if ($LASTEXITCODE -ne 0) { throw 'Hand model download failed.' }
Write-Host 'Setup complete. Open Test Gestures.cmd to practice without sending game inputs.'
