param(
    [Parameter(Position = 0)]
    [ValidateSet(
        "help",
        "setup",
        "api",
        "web",
        "launch",
        "desktop",
        "install-desktop",
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
$DesktopUrl = "http://127.0.0.1:8000/"
$DesktopHealthUrl = "http://127.0.0.1:8000/api/v1/health"

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
  desktop     start/reuse the built local app and open it in the browser
  install-desktop
              add a one-click Quaint Dash shortcut to this user's desktop

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
        [string] $RunCommand,
        [switch] $Minimized
    )
    $powershell = (Get-Process -Id $PID).Path
    $escapedTitle = $Title.Replace("'", "''")
    $escapedDirectory = $WorkingDirectory.Replace("'", "''")
    $commandLine = "& { `$Host.UI.RawUI.WindowTitle = '$escapedTitle'; Set-Location '$escapedDirectory'; $RunCommand }"
    $startArguments = @{
        FilePath = $powershell
        ArgumentList = @("-NoExit", "-NoProfile", "-Command", $commandLine)
    }
    if ($Minimized) {
        $startArguments["WindowStyle"] = "Minimized"
    }
    Start-Process @startArguments | Out-Null
}

function Test-DesktopApi {
    try {
        $response = Invoke-RestMethod $DesktopHealthUrl -TimeoutSec 2
        return $response.status -eq "ok" -and
            $response.database -eq "connected" -and
            -not [string]::IsNullOrWhiteSpace($response.api_version)
    } catch {
        return $false
    }
}

function Wait-ForDesktopApi {
    param([int] $TimeoutSeconds = 45)

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-DesktopApi) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Ensure-DesktopWebBuild {
    $indexPath = Join-Path $WebRoot "dist\index.html"
    $buildRequired = -not (Test-Path -LiteralPath $indexPath)
    if (-not $buildRequired) {
        $builtAt = (Get-Item -LiteralPath $indexPath).LastWriteTimeUtc
        $buildInputs = @()
        foreach ($relativePath in @("src", "public", "vendor")) {
            $inputRoot = Join-Path $WebRoot $relativePath
            if (Test-Path -LiteralPath $inputRoot) {
                $buildInputs += Get-ChildItem -LiteralPath $inputRoot -Recurse -File
            }
        }
        foreach ($fileName in @(
            "index.html",
            "package.json",
            "package-lock.json",
            "tsconfig.json",
            "tsconfig.app.json",
            "tsconfig.node.json",
            "vite.config.ts"
        )) {
            $inputPath = Join-Path $WebRoot $fileName
            if (Test-Path -LiteralPath $inputPath) {
                $buildInputs += Get-Item -LiteralPath $inputPath
            }
        }
        $buildRequired = $null -ne ($buildInputs | Where-Object {
            $_.LastWriteTimeUtc -gt $builtAt
        } | Select-Object -First 1)
    }

    if (-not $buildRequired) {
        return
    }

    $nodeModules = Join-Path $WebRoot "node_modules"
    if (-not (Test-Path -LiteralPath $nodeModules)) {
        throw "Web dependencies are missing. Run scripts\qd.cmd setup once, then try again."
    }

    Invoke-Step "build desktop web application" {
        Invoke-InWeb { Invoke-Native "npm.cmd" @("run", "build") }
    }

    if (-not (Test-Path -LiteralPath $indexPath)) {
        throw "The web build completed without creating web\dist\index.html."
    }
}

function Open-DesktopApplication {
    $launchMutex = [System.Threading.Mutex]::new(
        $false,
        "Local\QuaintDashDesktopLauncher"
    )
    $mutexHeld = $false
    try {
        try {
            $mutexHeld = $launchMutex.WaitOne([TimeSpan]::FromSeconds(50))
        } catch [System.Threading.AbandonedMutexException] {
            $mutexHeld = $true
        }
        if (-not $mutexHeld) {
            throw "Another Quaint Dash launcher is still starting. Try the shortcut again shortly."
        }

        Ensure-DesktopWebBuild

        if (-not (Test-DesktopApi)) {
            if (-not (Test-Path -LiteralPath $VenvPython)) {
                throw "The Python environment is missing. Run scripts\qd.cmd setup once, then try again."
            }

            Write-Host "Starting Quaint Dash in a minimized service window..."
            Write-Host "Restore that window and press Ctrl+C when you want to stop the service."
            Start-DevWindow `
                "Quaint Dash service - Ctrl+C to stop" `
                $Root `
                "& '$VenvPython' -m dashboard.api.app" `
                -Minimized

            if (-not (Wait-ForDesktopApi)) {
                throw "Quaint Dash did not become ready at $DesktopHealthUrl within 45 seconds. Check the minimized service window for the startup error."
            }
        } else {
            Write-Host "Quaint Dash is already running; reusing the existing service."
        }
    } finally {
        if ($mutexHeld) {
            $launchMutex.ReleaseMutex()
        }
        $launchMutex.Dispose()
    }

    Start-Process $DesktopUrl | Out-Null
    Write-Host "Opened $DesktopUrl"
}

function Install-DesktopShortcut {
    $desktopDirectory = [Environment]::GetFolderPath("DesktopDirectory")
    if ([string]::IsNullOrWhiteSpace($desktopDirectory)) {
        throw "Windows did not return a desktop directory for the current user."
    }

    $shortcutPath = Join-Path $desktopDirectory "Quaint Dash.lnk"
    $launcherPath = Join-Path $Root "scripts\qd.cmd"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $launcherPath
    $shortcut.Arguments = "desktop"
    $shortcut.WorkingDirectory = $Root
    $shortcut.Description = "Start Quaint Dash and open the local dashboard"
    $shortcut.IconLocation = "$env:SystemRoot\System32\imageres.dll,15"
    $shortcut.WindowStyle = 7
    $shortcut.Save()

    Write-Host "Installed desktop shortcut: $shortcutPath"
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
    "desktop" {
        Open-DesktopApplication
    }
    "install-desktop" {
        Install-DesktopShortcut
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
