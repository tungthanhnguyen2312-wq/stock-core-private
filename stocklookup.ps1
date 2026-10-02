param([Parameter(Position=0,Mandatory=$true)][ValidateSet('daily','roadmap','portfolio')][string]$Command,[Parameter(ValueFromRemainingArguments=$true)][string[]]$Args)
# The normal owner route shares the Desktop launcher presentation; diagnostic CLI flags
# continue through the existing Python CLI.
if ($Command -eq 'daily' -and $Args.Count -eq 0) {
    & (Join-Path $PSScriptRoot 'tools/run_owner_daily.ps1') -NoPause
    exit $LASTEXITCODE
}
$py = 'C:\Program Files\Python313\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }
& $py (Join-Path $PSScriptRoot 'stocklookup.py') $Command @Args
exit $LASTEXITCODE
