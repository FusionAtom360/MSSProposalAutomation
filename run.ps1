$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$application = Join-Path $PSScriptRoot "src\main.py"

& $python $application
exit $LASTEXITCODE
