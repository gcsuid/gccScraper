param(
    [switch]$Smoke
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$logDir = Join-Path $projectRoot "logs"

if (-not (Test-Path -LiteralPath $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $logDir "run_$timestamp.log"

function Write-Log {
    param([string]$Message)

    $Message | Tee-Object -FilePath $logFile -Append
}

Set-Location $projectRoot

Write-Log "Project root: $projectRoot"
Write-Log "Log file: $logFile"
if (-not $env:OLLAMA_API_KEY) {
    throw "OLLAMA_API_KEY is required. Add it to the project's .env file for direct Ollama Cloud access."
}
Write-Log "Using direct Ollama Cloud API; no local Ollama server or local model is required."

$pythonArgs = @("-u", "main.py")
if ($Smoke) {
    $pythonArgs += "--smoke"
    Write-Log "Running pipeline in smoke mode."
}
else {
    Write-Log "Running full pipeline."
}

& python @pythonArgs *>&1 | Tee-Object -FilePath $logFile -Append
