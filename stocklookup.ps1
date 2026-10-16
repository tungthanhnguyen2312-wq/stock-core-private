param([Parameter(Position=0,Mandatory=$true)][ValidateSet('daily','roadmap','portfolio','research')][string]$Command,[Parameter(ValueFromRemainingArguments=$true)][string[]]$Args)
# Apply the same persistent routing to Daily CLI flags as to the Desktop route.
if ($Command -eq 'daily') {
    $activeBinding = Join-Path $env:USERPROFILE '.stocklookup/active_workspace.json'
    if (Test-Path -LiteralPath $activeBinding) {
        $binding = Get-Content -LiteralPath $activeBinding -Raw | ConvertFrom-Json
        $activeProfile = [string]$binding.profile_path
        $activeBytes = [IO.File]::ReadAllBytes($activeProfile)
        $activeHasher = [Security.Cryptography.SHA256]::Create()
        try { $activeHash = [BitConverter]::ToString($activeHasher.ComputeHash($activeBytes)).Replace('-', '').ToLowerInvariant() }
        finally { $activeHasher.Dispose() }
        if ($binding.schema -ne 'stocklookup_active_workspace/v1' -or
            -not [IO.Path]::IsPathRooted($activeProfile) -or
            $activeHash -ne $binding.profile_sha256) {
            throw 'Active workspace profile identity invalid'
        }
        $activeRoles = ([Text.Encoding]::UTF8.GetString($activeBytes) | ConvertFrom-Json).roles
        if ([IO.Path]::GetFullPath($PSScriptRoot) -ne [IO.Path]::GetFullPath($activeRoles.producer)) {
            throw 'Checkout is not the active production writer'
        }
        if ($env:STOCK_LOOKUP_WORKSPACE_PROFILE -and
            [IO.Path]::GetFullPath($env:STOCK_LOOKUP_WORKSPACE_PROFILE) -ne [IO.Path]::GetFullPath($activeProfile)) {
            throw 'Stale workspace profile environment'
        }
        $activePython = [string]$binding.python_path
        if (-not [IO.Path]::IsPathRooted($activePython) -or -not (Test-Path -LiteralPath $activePython -PathType Leaf)) {
            throw 'Active Python unavailable'
        }
        if ($env:STOCK_LOOKUP_PYTHON -and [IO.Path]::GetFullPath($env:STOCK_LOOKUP_PYTHON) -ne [IO.Path]::GetFullPath($activePython)) {
            throw 'Stale Python environment'
        }
        $env:STOCK_LOOKUP_WORKSPACE_PROFILE = $activeProfile
        $env:STOCK_LOOKUP_PYTHON = $activePython
    }
}
# The normal owner route shares the Desktop launcher presentation; diagnostic CLI flags
# continue through the existing Python CLI.
if ($Command -eq 'daily' -and $Args.Count -eq 0) {
    & (Join-Path $PSScriptRoot 'tools/run_owner_daily.ps1') -NoPause
    exit $LASTEXITCODE
}
$py = 'C:\Program Files\Python313\python.exe'
if ($env:STOCK_LOOKUP_PYTHON) {
    if (-not (Test-Path -LiteralPath $env:STOCK_LOOKUP_PYTHON -PathType Leaf)) { throw 'Configured Python unavailable' }
    $py = $env:STOCK_LOOKUP_PYTHON
}
if (-not (Test-Path $py)) { $py = 'python' }
& $py (Join-Path $PSScriptRoot 'stocklookup.py') $Command @Args
exit $LASTEXITCODE
