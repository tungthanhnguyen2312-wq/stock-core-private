[CmdletBinding()]
param(
    [string]$ReplayCompletedSession,
    # Isolated-regression seams only. The Desktop "Stock Lookup Daily.cmd" passes none of them, so the
    # owner route is unchanged: canonical run_owner_daily.py, canonical run-logs, pause before closing.
    [string]$EntryScript,
    [string]$LogDirectory,
    [switch]$NoPause
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$runtime = 'C:\Projects\StockLookup\dashboard-runtime'
$logDir = 'C:\Projects\StockLookup\run-logs'
if ($LogDirectory) { $logDir = $LogDirectory }
$entry = Join-Path $PSScriptRoot 'run_owner_daily.py'
if ($EntryScript) { $entry = $EntryScript }
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
Write-Host '[1/9] Repository preflight'
Write-Host '[2/9] Canonical Daily'
Write-Host '[3/9] Daily completion verification'
Write-Host '[4/9] Producer state publication'
Write-Host '[5/9] AI handoff build'
Write-Host '[6/9] GitHub publication'
Write-Host '[7/9] Remote verification'
Write-Host '[8/9] Personal Action Center'
Write-Host '[9/9] Open owner view'

$arguments = @('-u', $entry, '--runtime-root', $runtime, '--result-path', $result)
if ($ReplayCompletedSession) { $arguments += @('--replay-completed-session', $ReplayCompletedSession) }
# M1_LIVE_ACCEPTANCE_CORRECTIVE_V1: under Windows PowerShell 5.1, `2>&1` wraps every native stderr
# line in an ErrorRecord, and with the script-wide 'Stop' preference the FIRST such line became a
# terminating NativeCommandError that killed run_owner_daily.py before it could record its own
# outcome (no result.json, no journal FAILED, no FINAL STATUS -- every Desktop Daily that wrote to
# stderr since 2026-09-17, including the 2026-09-24 acquisition failure). Stderr is expected native
# output, not a PowerShell failure: 'Continue' is scoped to this one call, each stderr record is
# rendered back to its own text so both streams stay visible and logged, and the native exit code
# alone decides the outcome.
$exitCode = $null
$scriptPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    & $python @arguments 2>&1 | ForEach-Object {
        if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.ToString() } else { $_ }
    } | Tee-Object -FilePath $log
    $exitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $scriptPreference
}

function Get-LastLoggedStep([string]$LogPath) {
    if (-not (Test-Path $LogPath)) { return $null }
    $lastStep = Get-Content -Path $LogPath -Tail 400 | Where-Object { $_ -like '-->*' } | Select-Object -Last 1
    if ($lastStep) { return $lastStep }
    return (Get-Content -Path $LogPath -Tail 1)
}

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
        Write-Host ("ACTION_CENTER_STATUS: " + $summary.action_center.status)
        Write-Host ("ACTION_CENTER_JSON: " + $summary.action_center.json_path)
        Write-Host ("ACTION_CENTER_VIEW: " + $summary.action_center.view_path)
        if ($summary.action_center.view_open.status -eq 'READY_VIEW_OPEN_FAILED') {
            Write-Host ("ACTION_CENTER_VIEW_NOTE: " + $summary.action_center.view_open.reason) -ForegroundColor Yellow
        }
    } elseif ($summary.status -eq 'PARTIAL') {
        Write-Host ''
        Write-Host 'FINAL STATUS: PARTIAL' -ForegroundColor Yellow
        Write-Host ("SESSION: " + $summary.session)
        Write-Host 'AI_GITHUB_STATUS: READY_FOR_AI'
        Write-Host ("ACTION_CENTER_STATUS: " + $summary.action_center.status)
        Write-Host ("REASON: " + $summary.action_center.reason)
    } elseif ($summary.status -eq 'INTERRUPTED') {
        Write-Host ''
        Write-Host 'FINAL STATUS: INTERRUPTED' -ForegroundColor Yellow
        Write-Host ("REASON: " + $summary.reason)
        if ($summary.hint) { Write-Host ("HINT: " + $summary.hint) }
        Write-Host ("CURRENT LOG: " + $log)
        Write-Host ("LAST LOGGED STEP: " + (Get-LastLoggedStep $log))
    } else {
        Write-Host ''
        Write-Host 'FINAL STATUS: FAILED' -ForegroundColor Red
        Write-Host ("FAILED STEP: " + $summary.failed_step)
        Write-Host ("REASON: " + $summary.reason)
        if ($summary.hint) { Write-Host ("HINT: " + $summary.hint) }
    }
} else {
    # The python process (or this wrapper's own process tree) was torn down before it could
    # write its own result.json -- e.g. the console window was closed, or the machine slept.
    # Never let that look like nothing happened: say so explicitly, with what we can recover.
    Write-Host ''
    Write-Host 'FINAL STATUS: INTERRUPTED' -ForegroundColor Yellow
    Write-Host 'REASON: NO_RESULT_FILE_WRITTEN'
    Write-Host 'HINT: The run ended before it could record its own outcome (closed window, sleep, or a kill outside this script''s control). This is NOT the same as the failure recorded in any older result file in this folder -- only this run''s own log below is current.'
    Write-Host ("CURRENT LOG: " + $log)
    Write-Host ("LAST LOGGED STEP: " + (Get-LastLoggedStep $log))
}
Write-Host ("LOG: " + $log)
# A non-zero native exit code is always preserved; a zero exit without the run's own result file
# is still not success.
$finalExitCode = 0
if ($null -ne $exitCode -and $exitCode -ne 0) { $finalExitCode = $exitCode }
elseif (-not (Test-Path $result)) { $finalExitCode = 1 }
if (-not $NoPause) { Read-Host 'Press Enter to close' }
exit $finalExitCode
