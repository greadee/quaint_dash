param(
    [Parameter(Position = 0)]
    [ValidateSet(
        "help",
        "setup",
        "api",
        "web",
        "launch",
        "test",
        "test-api",
        "lint",
        "verify-py",
        "verify-web",
        "verify",
        "build-web",
        "perf-signals-backend",
        "perf-signals-browser",
        "health",
        "smoke",
        "status"
    )]
    [string] $Command = "help",

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $ArgsForCommand
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$WebRoot = Join-Path $Root "web"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$Python = if (Test-Path $VenvPython) { $VenvPython } else { "python" }
$LockFile = Join-Path $Root "requirements.lock"
$PipVersion = "26.2.1"

function Invoke-InRoot {
    param([scriptblock] $Block)
    Push-Location $Root
    try {
        & $Block
    } finally {
        Pop-Location
    }
}

function Invoke-InWeb {
    param([scriptblock] $Block)
    Push-Location $WebRoot
    try {
        & $Block
    } finally {
        Pop-Location
    }
}

function Invoke-Step {
    param(
        [string] $Name,
        [scriptblock] $Block
    )
    Write-Host ""
    Write-Host "==> $Name"
    & $Block
}

function Invoke-Native {
    param(
        [string] $File,
        [string[]] $NativeArgs
    )
    & $File @NativeArgs
    $exitCode = $LASTEXITCODE
    if ($null -ne $exitCode -and $exitCode -ne 0) {
        throw "Command failed with exit code ${exitCode}: $File $($NativeArgs -join ' ')"
    }
}

function Show-Help {
    @"
quaint_dash workflow commands

Usage:
  .\scripts\qd.ps1 <command> [args]
  .\scripts\qd.cmd <command> [args]

Setup and launch:
  setup       install Python dev deps and web npm deps
  api         run FastAPI on http://127.0.0.1:8000
  web         run Vite on http://127.0.0.1:5173
  launch      open API and Vite in separate PowerShell windows

Verification:
  test        run the full pytest suite
  test-api    run API pytest files
  lint        run Python ruff and web eslint
  verify-py   run ruff and pytest
  verify-web  run web eslint, TypeScript, and Vite build
  verify      run Python and web verification
  build-web   build the React app
  perf-signals-backend
              profile backend /api/v1/signals service and SQL latency
  perf-signals-browser
              profile browser /signals load and per-request latency

Runtime checks:
  health      call http://127.0.0.1:8000/api/v1/health
  smoke       check API health and Vite root
  status      show git status and short branch

Extra args after the command are passed to pytest for test/test-api.
"@
}

function Start-DevWindow {
    param(
        [string] $Title,
        [string] $WorkingDirectory,
        [string] $RunCommand
    )
    $powershell = (Get-Process -Id $PID).Path
    $escapedTitle = $Title.Replace("'", "''")
    $escapedDirectory = $WorkingDirectory.Replace("'", "''")
    $escapedCommand = $RunCommand.Replace("'", "''")
    $commandLine = "& { `$Host.UI.RawUI.WindowTitle = '$escapedTitle'; Set-Location '$escapedDirectory'; $escapedCommand }"
    Start-Process -FilePath $powershell -ArgumentList @("-NoExit", "-Command", $commandLine) | Out-Null
}

switch ($Command) {
    "help" {
        Show-Help
    }
    "setup" {
        Invoke-Step "install Python dev dependencies" {
            Invoke-InRoot {
                Invoke-Native $Python @("-m", "pip", "install", "--upgrade", "pip==$PipVersion")
                Invoke-Native $Python @("-m", "pip", "install", "--require-hashes", "-r", $LockFile)
                Invoke-Native $Python @(
                    "-m", "pip", "install", "--no-build-isolation", "--no-deps", "-e", "."
                )
                Invoke-Native $Python @("-m", "pip", "check")
            }
        }
        Invoke-Step "install web dependencies" {
            Invoke-InWeb { Invoke-Native "npm.cmd" @("ci") }
        }
    }
    "api" {
        Invoke-InRoot { Invoke-Native $Python @("-m", "dashboard.api.app") }
    }
    "web" {
        Invoke-InWeb { Invoke-Native "npm.cmd" @("run", "dev") }
    }
    "launch" {
        Start-DevWindow "quaint_dash api" $Root "& '$Python' -m dashboard.api.app"
        Start-DevWindow "quaint_dash web" $WebRoot "npm.cmd run dev"
        Write-Host "API: http://127.0.0.1:8000"
        Write-Host "Web: http://127.0.0.1:5173"
    }
    "test" {
        Invoke-InRoot { Invoke-Native $Python (@("-m", "pytest") + $ArgsForCommand) }
    }
    "test-api" {
        Invoke-InRoot { Invoke-Native $Python (@("-m", "pytest", "tests/api") + $ArgsForCommand) }
    }
    "lint" {
        Invoke-Step "ruff" {
            Invoke-InRoot { Invoke-Native $Python @("-m", "ruff", "check") }
        }
        Invoke-Step "eslint" {
            Invoke-InWeb { Invoke-Native "npm.cmd" @("run", "lint") }
        }
    }
    "verify-py" {
        Invoke-Step "ruff" {
            Invoke-InRoot { Invoke-Native $Python @("-m", "ruff", "check") }
        }
        Invoke-Step "pytest" {
            Invoke-InRoot { Invoke-Native $Python @("-m", "pytest") }
        }
    }
    "verify-web" {
        Invoke-Step "eslint" {
            Invoke-InWeb { Invoke-Native "npm.cmd" @("run", "lint") }
        }
        Invoke-Step "TypeScript" {
            Invoke-InWeb { Invoke-Native "npm.cmd" @("exec", "--", "tsc", "-b") }
        }
        Invoke-Step "Vite build" {
            Invoke-InWeb { Invoke-Native "npm.cmd" @("run", "build") }
        }
    }
    "verify" {
        Invoke-Step "ruff" {
            Invoke-InRoot { Invoke-Native $Python @("-m", "ruff", "check") }
        }
        Invoke-Step "pytest" {
            Invoke-InRoot { Invoke-Native $Python @("-m", "pytest") }
        }
        Invoke-Step "eslint" {
            Invoke-InWeb { Invoke-Native "npm.cmd" @("run", "lint") }
        }
        Invoke-Step "TypeScript" {
            Invoke-InWeb { Invoke-Native "npm.cmd" @("exec", "--", "tsc", "-b") }
        }
        Invoke-Step "Vite build" {
            Invoke-InWeb { Invoke-Native "npm.cmd" @("run", "build") }
        }
    }
    "build-web" {
        Invoke-InWeb { Invoke-Native "npm.cmd" @("run", "build") }
    }
    "perf-signals-backend" {
        Invoke-InRoot { Invoke-Native $Python (@("tools\profile_signals_backend.py") + $ArgsForCommand) }
    }
    "perf-signals-browser" {
        Invoke-InWeb { Invoke-Native "npm.cmd" (@("run", "perf:signals", "--") + $ArgsForCommand) }
    }
    "health" {
        $response = Invoke-RestMethod "http://127.0.0.1:8000/api/v1/health"
        $response | ConvertTo-Json -Depth 5
    }
    "smoke" {
        Invoke-Step "API health" {
            $response = Invoke-RestMethod "http://127.0.0.1:8000/api/v1/health"
            $response | ConvertTo-Json -Depth 5
        }
        Invoke-Step "Vite root" {
            $response = Invoke-WebRequest "http://127.0.0.1:5173" -UseBasicParsing
            Write-Host "Vite HTTP status: $($response.StatusCode)"
        }
    }
    "status" {
        Invoke-InRoot { Invoke-Native "git" @("status", "--short", "--branch") }
    }
}
