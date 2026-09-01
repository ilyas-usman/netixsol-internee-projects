# Week 7 Day 3 launcher
$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
& .\.venv\Scripts\Activate.ps1

pip install -r requirements-day3.txt

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example. Add your API keys before starting."
}

python -m uvicorn app_day3:app --reload --port 8000
