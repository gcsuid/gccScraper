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

function Test-OllamaApi {
    try {
        Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 3 | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

function Ensure-OllamaReady {
    $ollamaCommand = Get-Command ollama -ErrorAction SilentlyContinue
    if (-not $ollamaCommand) {
        throw "Ollama is not installed or not available on PATH."
    }

    if (-not (Test-OllamaApi)) {
        Write-Log "Ollama API is not responding. Starting local Ollama server..."
        Start-Process -FilePath $ollamaCommand.Source -ArgumentList "serve" -WindowStyle Hidden | Out-Null

        $maxAttempts = 15
        for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
            Start-Sleep -Seconds 2
            if (Test-OllamaApi) {
                Write-Log "Ollama API is ready."
                break
            }

            if ($attempt -eq $maxAttempts) {
                throw "Ollama API did not become ready in time."
            }
        }
    }
    else {
        Write-Log "Ollama API is already running."
    }

    $modelsOutput = (& $ollamaCommand.Source list | Out-String)
    $modelsOutput | Tee-Object -FilePath $logFile -Append | Out-Null

    if ($modelsOutput -notmatch "(?m)^\s*qwen2\.5:3b\s") {
        throw "Required Ollama model qwen2.5:3b is not installed."
    }
}

Set-Location $projectRoot

Write-Log "Project root: $projectRoot"
Write-Log "Log file: $logFile"
Ensure-OllamaReady

$pythonArgs = @("-u", "main.py")
if ($Smoke) {
    $pythonArgs += "--smoke"
    Write-Log "Running pipeline in smoke mode."
}
else {
    Write-Log "Running full pipeline."
}

& python @pythonArgs *>&1 | Tee-Object -FilePath $logFile -Append
