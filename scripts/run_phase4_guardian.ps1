param([int]$WaitForPid = 0)

$ErrorActionPreference = 'Stop'
$projectDirectory = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectDirectory
$env:PYTHONPATH = Join-Path $projectDirectory 'src'
$marketPython = Join-Path $projectDirectory '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $marketPython)) {
    throw 'The pinned market environment is missing; do not install a different environment automatically.'
}
New-Item -ItemType Directory -Path (Join-Path $projectDirectory 'logs') -Force | Out-Null
$guardianArguments = @('-u', '-m', 'stock_picker.sync_guardian')
if ($WaitForPid -gt 0) {
    $guardianArguments += @('--wait-for-pid', "$WaitForPid")
}
& $marketPython @guardianArguments *>> (Join-Path $projectDirectory 'logs/phase4_guardian.task.log')
exit $LASTEXITCODE
