# TradingAgents Installation Script for Windows
# This script sets up the TradingAgents project with Python virtual environment and dependencies

param(
    [switch]$SkipPythonCheck = $false
)

$ErrorActionPreference = "Stop"

Write-Host "=================================" -ForegroundColor Cyan
Write-Host "TradingAgents Installation Script" -ForegroundColor Cyan
Write-Host "=================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check Python Installation
Write-Host "[1/5] Checking Python installation..." -ForegroundColor Yellow

if (-not $SkipPythonCheck) {
    try {
        $pythonVersion = python --version 2>&1
        Write-Host "✓ Python found: $pythonVersion" -ForegroundColor Green
    }
    catch {
        Write-Host "✗ Python is not installed or not in PATH" -ForegroundColor Red
        Write-Host ""
        Write-Host "Please install Python 3.11 or later:" -ForegroundColor Yellow
        Write-Host "  1. Visit: https://www.python.org/downloads/" -ForegroundColor White
        Write-Host "  2. Download Python 3.13 (or 3.11+)" -ForegroundColor White
        Write-Host "  3. During installation, CHECK 'Add Python to PATH'" -ForegroundColor White
        Write-Host "  4. Run this script again" -ForegroundColor White
        Write-Host ""
        Write-Host "Or use winget: winget install Python.Python.3.13" -ForegroundColor White
        Write-Host ""
        exit 1
    }
} else {
    Write-Host "⊘ Python check skipped" -ForegroundColor Yellow
}

# 2. Create Virtual Environment
Write-Host "[2/5] Creating virtual environment..." -ForegroundColor Yellow

$venvPath = ".\.venv"
if (Test-Path $venvPath) {
    Write-Host "⊘ Virtual environment already exists" -ForegroundColor Cyan
} else {
    Write-Host "Creating .venv..."
    python -m venv $venvPath
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Virtual environment created" -ForegroundColor Green
    } else {
        Write-Host "✗ Failed to create virtual environment" -ForegroundColor Red
        exit 1
    }
}

# 3. Activate Virtual Environment
Write-Host "[3/5] Activating virtual environment..." -ForegroundColor Yellow

$activateScript = "$venvPath\Scripts\Activate.ps1"
if (Test-Path $activateScript) {
    & $activateScript
    Write-Host "✓ Virtual environment activated" -ForegroundColor Green
} else {
    Write-Host "✗ Could not find activation script" -ForegroundColor Red
    exit 1
}

# 4. Install Dependencies
Write-Host "[4/5] Installing dependencies..." -ForegroundColor Yellow
Write-Host "(This may take 2-5 minutes)" -ForegroundColor Cyan

pip install --upgrade pip setuptools wheel 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠ Warning: pip upgrade had issues, continuing anyway..." -ForegroundColor Yellow
}

pip install .
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Dependencies installed successfully" -ForegroundColor Green
} else {
    Write-Host "✗ Failed to install dependencies" -ForegroundColor Red
    exit 1
}

# 5. Setup .env File
Write-Host "[5/5] Setting up environment configuration..." -ForegroundColor Yellow

$envFile = ".env"
$envExample = ".env.example"

if (Test-Path $envFile) {
    Write-Host "⊘ .env file already exists (keeping existing configuration)" -ForegroundColor Cyan
} elseif (Test-Path $envExample) {
    Copy-Item $envExample $envFile
    Write-Host "✓ Created .env from .env.example" -ForegroundColor Green
    Write-Host "⚠ IMPORTANT: Edit .env and add your API key(s):" -ForegroundColor Yellow
    Write-Host "  - OpenAI: OPENAI_API_KEY" -ForegroundColor White
    Write-Host "  - Google: GOOGLE_API_KEY" -ForegroundColor White
    Write-Host "  - Anthropic: ANTHROPIC_API_KEY" -ForegroundColor White
    Write-Host "  - xAI (Grok): XAI_API_KEY" -ForegroundColor White
    Write-Host "  - And others as needed..." -ForegroundColor White
} else {
    Write-Host "⚠ .env.example not found, skipping .env setup" -ForegroundColor Yellow
}

# 6. Verify Installation
Write-Host ""
Write-Host "Testing installation..." -ForegroundColor Yellow

$testOutput = tradingagents --help 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Installation verified successfully!" -ForegroundColor Green
} else {
    Write-Host "⚠ Warning: Could not verify tradingagents command" -ForegroundColor Yellow
    Write-Host "  This might be normal - try opening a new terminal" -ForegroundColor Cyan
}

# Summary
Write-Host ""
Write-Host "=================================" -ForegroundColor Cyan
Write-Host "Installation Complete!" -ForegroundColor Green
Write-Host "=================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Edit .env and add your LLM API key(s)" -ForegroundColor White
Write-Host "  2. Run: tradingagents --help" -ForegroundColor White
Write-Host "  3. Run: tradingagents" -ForegroundColor White
Write-Host ""
Write-Host "Virtual environment is active. To deactivate later, run: deactivate" -ForegroundColor Cyan
Write-Host ""
