[CmdletBinding()]
param([string]$ReplayCompletedSession)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$runtime = 'C:\Projects\StockLookup\dashboard-runtime'
$logDir = 'C:\Projects\StockLookup\run-logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$log = Join-Path $logDir "stock_lookup_daily_$stamp.log"
$result = Join-Path $logDir "stock_lookup_daily_$stamp.result.json"
$python = 'C:\Program Files\Python313\python.exe'
if (-not (Test-Path $python)) { $python = 'python' }

Write-Host '================================================'
Write-Host ' STOCK LOOKUP DAILY'
Write-Host (" Date: " + (Get-Date -Format 'yyyy-MM-dd'))
Write-Host '================================================'
Write-Host '[1/7] Repository preflight'
Write-Host '[2/7] Canonical Daily'
Write-Host '[3/7] Daily completion verification'
Write-Host '[4/7] Producer state publication'
Write-Host '[5/7] AI handoff build'
Write-Host '[6/7] GitHub publication'
Write-Host '[7/7] Verification'

$arguments = @('-u', (Join-Path $PSScriptRoot 'run_owner_daily.py'), '--runtime-root', $runtime, '--result-path', $result)
if ($ReplayCompletedSession) { $arguments += @('--replay-completed-session', $ReplayCompletedSession) }
& $python @arguments 2>&1 | Tee-Object -FilePath $log
$exitCode = $LASTEXITCODE

if (Test-Path $result) {
    $summary = Get-Content -Raw $result | ConvertFrom-Json
    if ($summary.status -eq 'PASS') {
        Write-Host ''
        Write-Host 'FINAL STATUS: PASS' -ForegroundColor Green
        Write-Host ("SESSION: " + $summary.session)
        Write-Host ("DAILY: " + $summary.daily_status)
        Write-Host ("PRODUCER SHA: " + $summary.producer_state.sha)
        Write-Host ("AI HANDOFF SHA: " + $summary.ai_handoff.remote.remote_sha)
        Write-Host 'AI_GITHUB_STATUS = READY_FOR_AI'
        Write-Host ("AI_LATEST_SESSION = " + $summary.ai_handoff.remote.latest_session)
        Write-Host ("AI_LATEST_POINTER = " + $summary.ai_handoff.remote.latest_pointer)
        Write-Host ("AI_REMOTE_SHA = " + $summary.ai_handoff.remote.remote_sha)
    } else {
        Write-Host ''
        Write-Host 'FINAL STATUS: FAILED' -ForegroundColor Red
        Write-Host ("FAILED STEP: " + $summary.failed_step)
        Write-Host ("REASON: " + $summary.reason)
        if ($summary.hint) { Write-Host ("HINT: " + $summary.hint) }
    }
}
Write-Host ("LOG: " + $log)
if ($exitCode -ne 0) { Read-Host 'Press Enter to close'; exit $exitCode }
Read-Host 'Press Enter to close'
