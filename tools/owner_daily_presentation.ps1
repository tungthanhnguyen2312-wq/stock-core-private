# Pure structured presentation shared by the interactive and redirected launcher.
function Format-OwnerPresentation($Event, $Checkpoint, $PhaseStarted, [int]$Width = 0) {
    $phase = [int]$Event.phase_index
    $label = $Event.phase_label
    $state = $Event.phase_state
    if (-not $state) {
        $state = if ($Event.status -eq 'FAILED') { 'LỖI' } elseif ($Event.owner_phase -and $Event.status -eq 'END') { 'XONG' } else { 'ĐANG CHẠY' }
    }
    $completed = $Checkpoint.checkpoint_completed
    $total = $Checkpoint.checkpoint_total
    $progressText = if ($total) { '{0}/{1} ({2:0}%)' -f $completed, $total, $Checkpoint.checkpoint_percent } else { '' }
    $task = if ($Event.task_label) { $Event.task_label } else { $Checkpoint.checkpoint_label }
    $parts = @('[{0}/9] {1}' -f $phase, $label) + @($state)
    if ($progressText) { $parts += 'Tiến độ ' + $progressText }
    if ($task -and $state -ne 'XONG') { $parts += 'Đang làm: ' + $task }
    $row = $parts -join ' | '
    if ($Width -gt 0 -and $row.Length -gt $Width) {
        # On small consoles the measured work count stays visible before the label.
        $row = ('[{0}/9] {1} | {2} | {3}' -f $phase, $progressText, $state, $task).TrimEnd(' ', '|')
        if ($row.Length -gt $Width) { $row = $row.Substring(0, [Math]::Max(1, $Width - 1)) + '…' }
    }
    $elapsed = $Event.phase_elapsed_seconds
    if ($null -ne $PhaseStarted -and $null -ne $Event.elapsed_seconds) {
        $elapsed = [Math]::Max(0, [double]$Event.elapsed_seconds - [double]$PhaseStarted)
    }
    $details = @()
    if ($null -ne $elapsed) {
        $prefix = if ($state -eq 'XONG') { 'Thời gian: ' } else { 'Đã chạy: ' }
        $details += $prefix + (Format-Duration $elapsed)
    }
    $details += 'ETA: ' + $(if ($null -ne $Event.owner_eta_seconds) { '~' + (Format-Duration $Event.owner_eta_seconds) } else { 'chưa đủ dữ liệu' })
    if ($Event.request_detail) { $details += $Event.request_detail }
    if ($Event.work_detail) { $details += $Event.work_detail }
    if ($Event.disk_warning) { $details += 'CẢNH BÁO: dung lượng đĩa thấp' }
    return @{ Row = $row; Details = $details }
}
