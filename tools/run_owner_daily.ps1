[CmdletBinding()]
param(
    [string]$ReplayCompletedSession,
    [string]$EntryScript,
    [string]$LogDirectory,
    [switch]$NoPause,
    [switch]$Diagnostic
)
$ErrorActionPreference = 'Stop'
$utf8 = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $utf8
[Console]::InputEncoding = $utf8
$OutputEncoding = $utf8
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$runtime = 'C:\Projects\StockLookup\dashboard-runtime'
$logDir = 'C:\Projects\StockLookup\run-logs'
if ($LogDirectory) { $logDir = $LogDirectory }
$entry = Join-Path $PSScriptRoot 'run_owner_daily.py'
if ($EntryScript) { $entry = $EntryScript }
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$log = Join-Path $logDir "stock_lookup_daily_$stamp.log"
$result = Join-Path $logDir "stock_lookup_daily_$stamp.result.json"
$progress = Join-Path $logDir "stock_lookup_daily_$stamp.progress.jsonl"
$python = 'C:\Program Files\Python313\python.exe'
if (-not (Test-Path $python)) { $python = 'python' }
$labels = @('Kiểm tra kho mã & môi trường', 'Chạy Daily chuẩn', 'Xác minh hoàn tất Daily',
    'Công bố trạng thái Producer', 'Công bố Dashboard', 'Tạo gói bàn giao AI', 'Xác minh từ xa',
    'Trung tâm Hành động Cá nhân', 'Mở màn hình dành cho chủ sở hữu')
$interactive = -not [Console]::IsOutputRedirected -and -not $Diagnostic
$viewReady = $false
$rowTop = 0
$currentPhase = 1
$rows = @()
$logWriter = [System.IO.StreamWriter]::new($log, $false, $utf8)
$logWriter.AutoFlush = $true
function Write-Owner([string]$Text) {
    [Console]::WriteLine($Text)
    $logWriter.WriteLine($Text)
}
function Format-Duration($Seconds) {
    if ($null -eq $Seconds) { return 'đang ước tính' }
    $n = [Math]::Max(0, [Math]::Round([double]$Seconds))
    return '{0:00}:{1:00}:{2:00}' -f [Math]::Floor($n / 3600), [Math]::Floor(($n % 3600) / 60), ($n % 60)
}
function Set-OwnerRow([int]$Index, [string]$Text) {
    if ($interactive -and $viewReady) {
        try {
            $width = [Math]::Max(20, [Console]::WindowWidth - 1)
            $display = if ($Text.Length -gt $width) { $Text.Substring(0, $width) } else { $Text }
            [Console]::SetCursorPosition(0, $rowTop + $Index)
            [Console]::Write($display.PadRight($width))
            [Console]::SetCursorPosition(0, $rowTop + 14)
            return
        } catch { $script:interactive = $false }
    }
    [Console]::WriteLine($Text)
}
Write-Owner ('=' * 60)
Write-Owner ' STOCK LOOKUP DAILY'
Write-Owner (' Ngày: ' + (Get-Date -Format 'yyyy-MM-dd'))
Write-Owner ('=' * 60)
$arguments = @('-u', $entry, '--runtime-root', $runtime, '--result-path', $result, '--progress-path', $progress)
if ($ReplayCompletedSession) { $arguments += @('--replay-completed-session', $ReplayCompletedSession) }
$priorStructured = $env:STOCK_LOOKUP_OWNER_STRUCTURED_CONSOLE
$env:STOCK_LOOKUP_OWNER_STRUCTURED_CONSOLE = '1'
$exitCode = $null
$scriptPreference = $ErrorActionPreference
# Native stderr is data under Windows PowerShell 5.1; preserve its text and native exit code.
$ErrorActionPreference = 'Continue'
try {
    & $python @arguments 2>&1 | ForEach-Object {
        $text = if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.ToString() } else { [string]$_ }
        $logWriter.WriteLine($text)
        if ($text.StartsWith('OWNER_DAILY_PRESENTATION=')) {
            $presentation = $text.Substring('OWNER_DAILY_PRESENTATION='.Length) | ConvertFrom-Json
            if ($interactive) {
                try { $rowTop = [Console]::CursorTop } catch { $interactive = $false }
            }
            foreach ($phase in 1..9) {
                $estimate = $presentation.phase_estimates.([string]$phase)
                $etaText = if ($null -eq $estimate) { 'đang ước tính' } else { '~' + (Format-Duration $estimate) }
                $rows += ('[{0}/9] {1} | CHỜ | ETA: {2}' -f $phase, $labels[$phase - 1], $etaText)
                [Console]::WriteLine($rows[-1])
            }
            if ($interactive) { foreach ($unused in 1..5) { [Console]::WriteLine('') } }
            $viewReady = $true
        } elseif ($text.StartsWith('OWNER_DAILY_PROGRESS=')) {
            $event = $text.Substring('OWNER_DAILY_PROGRESS='.Length) | ConvertFrom-Json
            $currentPhase = [int]$event.phase_index
            if ($interactive -and $viewReady) {
                $parts = $event.owner_line -split ' \| '
                Set-OwnerRow ($currentPhase - 1) (($parts | Select-Object -First 3) -join ' | ')
                if (-not $event.owner_phase) {
                    $details = @($parts | Select-Object -Skip 3)
                    foreach ($index in 0..4) {
                        $detail = if ($index -lt $details.Count) { '      ' + $details[$index] } else { '' }
                        Set-OwnerRow (9 + $index) $detail
                    }
                }
            } else { [Console]::WriteLine($event.owner_line) }
        } elseif ($Diagnostic) { [Console]::WriteLine($text) }
    }
    $exitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $scriptPreference
    $env:STOCK_LOOKUP_OWNER_STRUCTURED_CONSOLE = $priorStructured
}
if ($interactive -and $viewReady) {
    try { [Console]::SetCursorPosition(0, $rowTop + 14) } catch {}
}
$summary = $null
if (Test-Path -LiteralPath $result) { $summary = Get-Content -LiteralPath $result -Raw -Encoding UTF8 | ConvertFrom-Json }
Write-Owner ('=' * 60)
if ($summary -and $summary.status -eq 'PASS' -and $exitCode -eq 0) {
    Write-Owner ' HOÀN TẤT DAILY'
    Write-Owner (' Phiên: ' + $summary.session)
    Write-Owner (' Tổng thời gian: ' + (Format-Duration $summary.telemetry.elapsed_seconds))
    Write-Owner ('-' * 60)
    foreach ($label in @('Daily', 'Dashboard', 'Bàn giao AI', 'Xác minh từ xa', 'Trung tâm Hành động')) {
        Write-Owner (' ' + $label + ': XONG')
    }
    Write-Owner ' Trạng thái: PASS'
    if ($summary.action_center.view_open.status -eq 'READY_VIEW_OPEN_FAILED') {
        Write-Owner ' CẢNH BÁO: chưa mở được màn hình, xem log chi tiết.'
    }
} else {
    Write-Owner ' DAILY CHƯA HOÀN TẤT'
    Write-Owner (' Bước lỗi: [{0}/9] {1}' -f $currentPhase, $labels[$currentPhase - 1])
    $explanation = if ($currentPhase -eq 6) { 'Không thể xác minh gói bàn giao AI của phiên đã hoàn tất.' } else { 'Bước xử lý chưa vượt qua kiểm tra bắt buộc. Xem log chi tiết.' }
    Write-Owner (' Lý do: ' + $explanation)
    $reason = if ($summary) { $summary.reason } else { 'NO_RESULT_FILE_WRITTEN' }
    Write-Owner (' Mã lỗi: ' + $reason)
    $resume = if ($summary.resume_completed_session) { 'CÓ' } else { 'KHÔNG' }
    Write-Owner (' Có thể tiếp tục từ phiên đã hoàn tất: ' + $resume)
    Write-Owner (' Log chi tiết: ' + $log)
    Write-Owner (' Trạng thái: ' + $(if ($summary) { $summary.status } else { 'INTERRUPTED' }))
}
Write-Owner ('=' * 60)
if ($Diagnostic) { Write-Owner (' Log chi tiết: ' + $log) }
$logWriter.Dispose()
$finalExitCode = 0
if ($null -ne $exitCode -and $exitCode -ne 0) { $finalExitCode = $exitCode }
elseif (-not $summary -or $summary.status -ne 'PASS') { $finalExitCode = 1 }
if (-not $NoPause) { Read-Host 'Nhấn Enter để đóng' }
exit $finalExitCode
