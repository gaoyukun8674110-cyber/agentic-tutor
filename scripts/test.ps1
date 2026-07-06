$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
$Python = Join-Path $Backend '.venv\Scripts\python.exe'

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name,
        [Parameter(Mandatory = $true)]
        [scriptblock] $Command
    )

    Write-Host "==> $Name"
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

function Set-TestEnv {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name,
        [string] $Value
    )

    Set-Item -Path "Env:\$Name" -Value $Value
}

function Restore-TestEnv {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name,
        [AllowNull()]
        [string] $Value
    )

    if ($null -eq $Value) {
        Remove-Item "Env:\$Name" -ErrorAction SilentlyContinue
    }
    else {
        Set-Item -Path "Env:\$Name" -Value $Value
    }
}

function Wait-Http {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Url,
        [Parameter(Mandatory = $true)]
        [string] $Name
    )

    foreach ($Attempt in 1..60) {
        try {
            Invoke-WebRequest -UseBasicParsing $Url | Out-Null
            return
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }

    throw "$Name did not become ready at $Url"
}

if (-not (Test-Path -LiteralPath $Python)) {
    $Python = 'python'
}

Push-Location $Backend
try {
    Invoke-Checked 'Backend ruff' { & $Python -m ruff check app tests scripts start.py alembic }
    Invoke-Checked 'Backend black' { & $Python -m black --check app tests scripts start.py alembic }
    Invoke-Checked 'Backend mypy' { & $Python -m mypy app }
    Invoke-Checked 'Backend compileall' { & $Python -m compileall app tests }
    Invoke-Checked 'Backend app import' { & $Python -c "from app.main import app; print(app.title)" }

    $MigrationDb = New-TemporaryFile
    Remove-Item -LiteralPath $MigrationDb.FullName
    $PreviousDatabaseUrl = $env:DATABASE_URL
    try {
        $MigrationDbUrlPath = $MigrationDb.FullName.Replace('\', '/')
        $env:DATABASE_URL = "sqlite:///$MigrationDbUrlPath"
        Invoke-Checked 'Backend alembic upgrade head' { & $Python -m alembic upgrade head }
    }
    finally {
        if ($null -eq $PreviousDatabaseUrl) {
            Remove-Item Env:\DATABASE_URL -ErrorAction SilentlyContinue
        }
        else {
            $env:DATABASE_URL = $PreviousDatabaseUrl
        }
        if (Test-Path -LiteralPath $MigrationDb.FullName) {
            Remove-Item -LiteralPath $MigrationDb.FullName
        }
    }

    Invoke-Checked 'Backend tutor eval schema' { & $Python -m scripts.evaluate_tutor_behavior --cases evals\tutor_cases.jsonl --json }
    Invoke-Checked 'Backend pytest coverage' { & $Python -m pytest tests --cov=app --cov-report=term-missing --cov-fail-under=60 }
    Invoke-Checked 'Backend pip-audit' { & $Python -m pip_audit -r requirements.txt }
}
finally {
    Pop-Location
}

Push-Location $Frontend
try {
    Invoke-Checked 'Frontend prettier' { npm.cmd run format:check }
    Invoke-Checked 'Frontend lint' { npm.cmd run lint }
    Invoke-Checked 'Frontend vitest' { npm.cmd run test:run }
    Invoke-Checked 'Frontend type-check' { npm.cmd run type-check }
    Invoke-Checked 'Frontend build' { npm.cmd run build }
    Invoke-Checked 'Frontend npm audit' { npm.cmd run audit:prod }
}
finally {
    Pop-Location
}

$E2eDb = New-TemporaryFile
Remove-Item -LiteralPath $E2eDb.FullName
$BackendLog = Join-Path $Backend '.ci-e2e-backend.log'
$BackendErr = Join-Path $Backend '.ci-e2e-backend.err.log'
$FrontendLog = Join-Path $Frontend '.ci-e2e-frontend.log'
$FrontendErr = Join-Path $Frontend '.ci-e2e-frontend.err.log'
$TestResults = Join-Path $Frontend 'test-results'
$PreviousDatabaseUrl = $env:DATABASE_URL
$PreviousE2eMockLlm = $env:E2E_MOCK_LLM
$PreviousViteApiBaseUrl = $env:VITE_API_BASE_URL
$PreviousPlaywrightBaseUrl = $env:PLAYWRIGHT_BASE_URL
$PreviousPlaywrightChromiumExecutablePath = $env:PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
$BackendProcess = $null
$FrontendProcess = $null
$E2eSucceeded = $false

try {
    Set-TestEnv 'DATABASE_URL' "sqlite:///$($E2eDb.FullName.Replace('\', '/'))"
    Set-TestEnv 'E2E_MOCK_LLM' 'true'

    Push-Location $Backend
    try {
        Invoke-Checked 'E2E alembic upgrade head' { & $Python -m alembic upgrade head }
        $BackendProcess = Start-Process `
            -FilePath $Python `
            -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8001' `
            -WorkingDirectory $Backend `
            -WindowStyle Hidden `
            -RedirectStandardOutput $BackendLog `
            -RedirectStandardError $BackendErr `
            -PassThru
    }
    finally {
        Pop-Location
    }

    Set-TestEnv 'VITE_API_BASE_URL' 'http://127.0.0.1:8001'
    $FrontendProcess = Start-Process `
        -FilePath 'node' `
        -ArgumentList 'node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '4173' `
        -WorkingDirectory $Frontend `
        -WindowStyle Hidden `
        -RedirectStandardOutput $FrontendLog `
        -RedirectStandardError $FrontendErr `
        -PassThru

    Wait-Http 'http://127.0.0.1:8001/health' 'Backend'
    Wait-Http 'http://127.0.0.1:4173' 'Frontend'

    Set-TestEnv 'PLAYWRIGHT_BASE_URL' 'http://127.0.0.1:4173'
    $ChromePath = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
    if (-not $env:PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH -and (Test-Path -LiteralPath $ChromePath)) {
        Set-TestEnv 'PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH' $ChromePath
    }

    Push-Location $Frontend
    try {
        Invoke-Checked 'Cross-stack Playwright e2e' { npm.cmd run e2e }
        $E2eSucceeded = $true
    }
    finally {
        Pop-Location
    }
}
finally {
    if ($BackendProcess -and -not $BackendProcess.HasExited) {
        Stop-Process -Id $BackendProcess.Id -Force
    }
    if ($FrontendProcess -and -not $FrontendProcess.HasExited) {
        Stop-Process -Id $FrontendProcess.Id -Force
    }

    Restore-TestEnv 'DATABASE_URL' $PreviousDatabaseUrl
    Restore-TestEnv 'E2E_MOCK_LLM' $PreviousE2eMockLlm
    Restore-TestEnv 'VITE_API_BASE_URL' $PreviousViteApiBaseUrl
    Restore-TestEnv 'PLAYWRIGHT_BASE_URL' $PreviousPlaywrightBaseUrl
    Restore-TestEnv 'PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH' $PreviousPlaywrightChromiumExecutablePath

    if (Test-Path -LiteralPath $E2eDb.FullName) {
        Remove-Item -LiteralPath $E2eDb.FullName
    }
    if ($E2eSucceeded) {
        foreach ($Path in @($BackendLog, $BackendErr, $FrontendLog, $FrontendErr, $TestResults)) {
            if (Test-Path -LiteralPath $Path) {
                Remove-Item -LiteralPath $Path -Recurse -Force
            }
        }
    }
}
