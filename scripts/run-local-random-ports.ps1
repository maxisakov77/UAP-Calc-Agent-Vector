$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Get-FreeTcpPort {
    param(
        [int[]]$ExcludedPorts = @()
    )

    while ($true) {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
        try {
            $listener.Start()
            $port = ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
        } finally {
            $listener.Stop()
        }

        if ($ExcludedPorts -notcontains $port) {
            return $port
        }
    }
}

function Start-ProcessWithEnvironment {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory,
        [hashtable]$Environment,
        [string]$StandardOutputPath,
        [string]$StandardErrorPath
    )

    $previousEnvironment = @{}

    foreach ($name in $Environment.Keys) {
        $envPath = "Env:$name"
        if (Test-Path $envPath) {
            $previousEnvironment[$name] = (Get-Item $envPath).Value
        } else {
            $previousEnvironment[$name] = $null
        }
        Set-Item -Path $envPath -Value ([string]$Environment[$name])
    }

    try {
        return Start-Process `
            -FilePath $FilePath `
            -ArgumentList $ArgumentList `
            -WorkingDirectory $WorkingDirectory `
            -RedirectStandardOutput $StandardOutputPath `
            -RedirectStandardError $StandardErrorPath `
            -PassThru
    } finally {
        foreach ($name in $Environment.Keys) {
            $envPath = "Env:$name"
            if ($null -eq $previousEnvironment[$name]) {
                Remove-Item -Path $envPath -ErrorAction SilentlyContinue
            } else {
                Set-Item -Path $envPath -Value $previousEnvironment[$name]
            }
        }
    }
}

function Wait-ForHttpReady {
    param(
        [string]$Url,
        [int]$TimeoutSeconds,
        [string]$ExpectedContent = ""
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $response = Invoke-WebRequest -Uri $Url -TimeoutSec 5 -UseBasicParsing
            if ([int]$response.StatusCode -eq 200) {
                if (-not $ExpectedContent -or $response.Content -match [regex]::Escape($ExpectedContent)) {
                    return $response
                }
            }
        } catch {
        }

        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    throw "Timed out waiting for $Url"
}

function Get-LogTail {
    param(
        [string]$Path,
        [int]$Lines = 40
    )

    if (-not (Test-Path $Path)) {
        return ""
    }

    return (Get-Content -Path $Path -Tail $Lines) -join [Environment]::NewLine
}

function Stop-ProcessIfRunning {
    param(
        [System.Diagnostics.Process]$Process
    )

    if ($null -eq $Process) {
        return
    }

    try {
        if (-not $Process.HasExited) {
            Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        }
    } catch {
    }
}

function Copy-FrontendWorkspace {
    param(
        [string]$SourceDirectory,
        [string]$DestinationDirectory
    )

    if (Test-Path $DestinationDirectory) {
        Remove-Item -Path $DestinationDirectory -Recurse -Force
    }

    New-Item -ItemType Directory -Path $DestinationDirectory -Force | Out-Null

    $null = robocopy $SourceDirectory $DestinationDirectory /E /XD node_modules .next
    if ($LASTEXITCODE -gt 7) {
        throw "Failed to stage frontend workspace with robocopy (exit code $LASTEXITCODE)"
    }

    New-Item `
        -ItemType Junction `
        -Path (Join-Path $DestinationDirectory "node_modules") `
        -Target (Join-Path $SourceDirectory "node_modules") | Out-Null
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$backendDir = Join-Path $repoRoot "backend"
$webDir = Join-Path $repoRoot "web"
$backendPython = Join-Path $backendDir "venv\Scripts\python.exe"
$nextBin = Join-Path $webDir "node_modules\next\dist\bin\next"
$nodePath = (Get-Command node -ErrorAction Stop).Source

if (-not (Test-Path $backendPython)) {
    throw "Backend virtualenv Python not found at $backendPython"
}

if (-not (Test-Path $nextBin)) {
    throw "Next.js CLI not found at $nextBin"
}

$excludedPorts = @(3000, 3001, 8000)
$backendPort = Get-FreeTcpPort -ExcludedPorts $excludedPorts
$frontendPort = Get-FreeTcpPort -ExcludedPorts ($excludedPorts + $backendPort)

if (($excludedPorts -contains $backendPort) -or ($excludedPorts -contains $frontendPort) -or ($backendPort -eq $frontendPort)) {
    throw "Random port selection failed: frontend=$frontendPort backend=$backendPort"
}

$backendUrl = "http://localhost:$backendPort"
$frontendUrl = "http://localhost:$frontendPort"
$settingsUrl = "$backendUrl/api/settings"

$logDir = Join-Path $env:TEMP "UAP-Calc-Agent-Vector"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$sessionWorkDir = Join-Path $logDir "session-$stamp"
$frontendWorkDir = Join-Path $sessionWorkDir "web"
$backendOutLog = Join-Path $logDir "backend-$stamp.out.log"
$backendErrLog = Join-Path $logDir "backend-$stamp.err.log"
$frontendOutLog = Join-Path $logDir "frontend-$stamp.out.log"
$frontendErrLog = Join-Path $logDir "frontend-$stamp.err.log"
$sessionPath = Join-Path $logDir "session.json"

$backendProcess = $null
$frontendProcess = $null

try {
    Copy-FrontendWorkspace -SourceDirectory $webDir -DestinationDirectory $frontendWorkDir
    $stagedNextBin = Join-Path $frontendWorkDir "node_modules\next\dist\bin\next"

    $backendProcess = Start-ProcessWithEnvironment `
        -FilePath $backendPython `
        -ArgumentList @("-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", $backendPort.ToString()) `
        -WorkingDirectory $backendDir `
        -Environment @{
            BACKEND_HOST = "127.0.0.1"
            BACKEND_PORT = $backendPort.ToString()
            CORS_ALLOW_ORIGINS = $frontendUrl
        } `
        -StandardOutputPath $backendOutLog `
        -StandardErrorPath $backendErrLog

    Wait-ForHttpReady -Url $settingsUrl -TimeoutSeconds 90 | Out-Null

    $frontendProcess = Start-ProcessWithEnvironment `
        -FilePath $nodePath `
        -ArgumentList @(
            $stagedNextBin,
            "dev",
            "--webpack",
            "--hostname",
            "127.0.0.1",
            "--port",
            $frontendPort.ToString()
        ) `
        -WorkingDirectory $frontendWorkDir `
        -Environment @{
            NEXT_PUBLIC_API_URL = $backendUrl
        } `
        -StandardOutputPath $frontendOutLog `
        -StandardErrorPath $frontendErrLog

    Wait-ForHttpReady -Url $frontendUrl -TimeoutSeconds 120 -ExpectedContent "UAP 485-x NYC Development Expert" | Out-Null

    $corsResponse = Invoke-WebRequest -Uri $settingsUrl -Headers @{ Origin = $frontendUrl } -TimeoutSec 5 -UseBasicParsing
    $allowedOrigin = $corsResponse.Headers["Access-Control-Allow-Origin"]
    if ($allowedOrigin -ne $frontendUrl) {
        throw "CORS verification failed. Expected '$frontendUrl' but received '$allowedOrigin'"
    }

    $session = [ordered]@{
        started_at = (Get-Date).ToString("o")
        repo_root = $repoRoot
        frontend = [ordered]@{
            url = $frontendUrl
            port = $frontendPort
            pid = $frontendProcess.Id
            work_dir = $frontendWorkDir
            stdout_log = $frontendOutLog
            stderr_log = $frontendErrLog
        }
        backend = [ordered]@{
            url = $backendUrl
            port = $backendPort
            settings_url = $settingsUrl
            pid = $backendProcess.Id
            stdout_log = $backendOutLog
            stderr_log = $backendErrLog
        }
    }

    $session | ConvertTo-Json -Depth 5 | Set-Content -Path $sessionPath -Encoding ASCII

    Write-Output "Frontend URL: $frontendUrl"
    Write-Output "Backend URL: $backendUrl"
    Write-Output "Backend Settings URL: $settingsUrl"
    Write-Output "Frontend PID: $($frontendProcess.Id)"
    Write-Output "Backend PID: $($backendProcess.Id)"
    Write-Output "Frontend Logs: $frontendOutLog ; $frontendErrLog"
    Write-Output "Backend Logs: $backendOutLog ; $backendErrLog"
    Write-Output "Session File: $sessionPath"
} catch {
    $backendErrTail = Get-LogTail -Path $backendErrLog
    $backendOutTail = Get-LogTail -Path $backendOutLog
    $frontendErrTail = Get-LogTail -Path $frontendErrLog
    $frontendOutTail = Get-LogTail -Path $frontendOutLog

    Stop-ProcessIfRunning -Process $frontendProcess
    Stop-ProcessIfRunning -Process $backendProcess

    if ($backendErrTail) {
        Write-Output "Backend stderr tail:"
        Write-Output $backendErrTail
    }
    if ($backendOutTail) {
        Write-Output "Backend stdout tail:"
        Write-Output $backendOutTail
    }
    if ($frontendErrTail) {
        Write-Output "Frontend stderr tail:"
        Write-Output $frontendErrTail
    }
    if ($frontendOutTail) {
        Write-Output "Frontend stdout tail:"
        Write-Output $frontendOutTail
    }

    throw
}
