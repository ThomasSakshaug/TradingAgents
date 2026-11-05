<#
.SYNOPSIS
Starter, stopper eller viser status for TradingAgents-tjenestene (Streamlit-web og lokal Ollama).

.EXAMPLE
.\Manage-TradingAgents.ps1 -Action Start
.\Manage-TradingAgents.ps1 -Action Stop -Service Web
.\Manage-TradingAgents.ps1 -Action Status
#>
[CmdletBinding()]
param(
    [ValidateSet('Start', 'Stop', 'Status')]
    [string]$Action = 'Start',

    [ValidateSet('All', 'Web', 'Ollama')]
    [string]$Service = 'All',

    [int]$Port = 8501
)

$ErrorActionPreference = 'Stop'

$root        = $PSScriptRoot
$python      = Join-Path $root '.venv\Scripts\python.exe'
$app         = Join-Path $root 'web_app.py'
$runDir      = Join-Path $root '.run'
$webPidFile  = Join-Path $runDir 'web.pid'
$webUrl      = "http://127.0.0.1:$Port"
$ollamaUrl   = 'http://127.0.0.1:11434/api/version'

New-Item -ItemType Directory -Force -Path $runDir | Out-Null

function Test-Url([string]$Url) {
    try { Invoke-RestMethod -Uri $Url -TimeoutSec 2 | Out-Null; return $true } catch { return $false }
}

function Get-WebPid {
    if (-not (Test-Path $webPidFile)) { return $null }
    $id = [int](Get-Content $webPidFile)
    if (Get-Process -Id $id -ErrorAction SilentlyContinue) { return $id }
    Remove-Item $webPidFile -Force
    return $null
}

function Start-Web {
    $existing = Get-WebPid
    if ($existing) { Write-Host "Web: kjører allerede (PID $existing) på $webUrl"; return }
    if (-not (Test-Path $python)) { throw "Fant ikke $python. Opprett .venv og installer avhengigheter først." }

    $args = @('-m', 'streamlit', 'run', $app, '--server.address', '127.0.0.1', '--server.port', $Port, '--server.headless', 'true')
    $proc = Start-Process -FilePath $python -ArgumentList $args -WorkingDirectory $root -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $runDir 'web.log') -RedirectStandardError (Join-Path $runDir 'web.err.log') -PassThru
    $proc.Id | Set-Content $webPidFile
    Write-Host "Web: startet (PID $($proc.Id)) - $webUrl"
}

function Stop-Web {
    $id = Get-WebPid
    if (-not $id) { Write-Host 'Web: kjører ikke (startet av dette skriptet)'; return }
    Stop-Process -Id $id -Force
    Remove-Item $webPidFile -Force
    Write-Host "Web: stoppet (PID $id)"
}

function Start-Ollama {
    if (Test-Url $ollamaUrl) { Write-Host 'Ollama: kjører allerede'; return }
    $cmd = Get-Command ollama -ErrorAction SilentlyContinue
    if (-not $cmd) { Write-Warning 'Ollama er ikke installert eller finnes ikke i PATH. Hopper over.'; return }

    Start-Process -FilePath $cmd.Source -ArgumentList 'serve' -WindowStyle Hidden | Out-Null
    for ($i = 0; $i -lt 20 -and -not (Test-Url $ollamaUrl); $i++) { Start-Sleep -Milliseconds 500 }
    if (Test-Url $ollamaUrl) { Write-Host 'Ollama: startet' } else { Write-Warning 'Ollama svarer ikke etter oppstart.' }
}

function Stop-Ollama {
    $procs = Get-Process -Name ollama -ErrorAction SilentlyContinue
    if (-not $procs) { Write-Host 'Ollama: kjører ikke'; return }
    $procs | Stop-Process -Force
    Write-Host 'Ollama: stoppet (alle ollama-prosesser)'
}

function Show-Status {
    $id = Get-WebPid
    $webState = if ($id) { "kjører (PID $id)" } else { 'kjører ikke' }
    $healthy  = if ($id -and (Test-Url "$webUrl/_stcore/health")) { ', svarer' } else { '' }
    Write-Host "Web:    $webState$healthy - $webUrl"
    Write-Host ("Ollama: " + $(if (Test-Url $ollamaUrl) { 'kjører' } else { 'kjører ikke' }))
}

$useWeb    = $Service -in 'All', 'Web'
$useOllama = $Service -in 'All', 'Ollama'

switch ($Action) {
    'Start'  { if ($useOllama) { Start-Ollama }; if ($useWeb) { Start-Web } }
    'Stop'   { if ($useWeb) { Stop-Web }; if ($useOllama) { Stop-Ollama } }
    'Status' { Show-Status }
}
