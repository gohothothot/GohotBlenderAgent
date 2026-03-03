param(
  [string]$PythonPath = "",
  [string]$TestModule = "tests.test_backend_agent2_basics"
)

$ErrorActionPreference = "Stop"

function Resolve-Python {
  param([string]$Hint)

  function Test-PythonUsable {
    param([string]$ExePath)
    if (-not $ExePath) { return $false }
    try {
      & $ExePath -V *> $null
      return ($LASTEXITCODE -eq 0)
    } catch {
      return $false
    }
  }

  if ($Hint -and (Test-Path $Hint) -and (Test-PythonUsable $Hint)) {
    return $Hint
  }

  if ($env:BLENDER_PYTHON -and (Test-Path $env:BLENDER_PYTHON) -and (Test-PythonUsable $env:BLENDER_PYTHON)) {
    return $env:BLENDER_PYTHON
  }

  $candidates = @(
    "python",
    "python3",
    "py"
  )

  foreach ($c in $candidates) {
    try {
      $cmd = Get-Command $c -ErrorAction Stop
      if ($cmd -and $cmd.Source) {
        if (Test-PythonUsable $cmd.Source) {
          return $cmd.Source
        }
      }
    } catch {
      # continue probing
    }
  }

  # common project-local venv path
  $localVenv = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
  $localVenv = (Resolve-Path $localVenv -ErrorAction SilentlyContinue)
  if ($localVenv -and (Test-PythonUsable $localVenv.Path)) {
    return $localVenv.Path
  }

  return $null
}

$py = Resolve-Python -Hint $PythonPath
if (-not $py) {
  Write-Host "[run_backend_tests] No Python interpreter found." -ForegroundColor Yellow
  Write-Host "Choose one option and retry:" -ForegroundColor Yellow
  Write-Host "1) Add python to PATH" -ForegroundColor Yellow
  Write-Host "2) Set BLENDER_PYTHON env var to blender python.exe" -ForegroundColor Yellow
  Write-Host "3) Pass -PythonPath explicitly" -ForegroundColor Yellow
  exit 2
}

Write-Host "[run_backend_tests] using: $py"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $repoRoot
try {
  & $py -m unittest $TestModule
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }
  Write-Host "[run_backend_tests] tests passed." -ForegroundColor Green
} finally {
  Pop-Location
}
