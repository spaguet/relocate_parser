# Cross-platform development helpers (PowerShell)
param(
    [Parameter(Position = 0)]
    [ValidateSet("install", "install-dev", "lint", "format", "typecheck", "test", "up", "down", "logs")]
    [string]$Task = "install-dev"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path) | Out-Null
Set-Location ..

switch ($Task) {
    "install" { pip install -e . }
    "install-dev" { pip install -e ".[dev]" }
    "lint" { ruff check src tests }
    "format" {
        ruff format src tests
        ruff check --fix src tests
    }
    "typecheck" { mypy src/relocate_helper }
    "test" { pytest tests -v }
    "up" { docker compose up --build -d }
    "down" { docker compose down }
    "logs" { docker compose logs -f app worker }
}
