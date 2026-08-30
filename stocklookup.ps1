param([Parameter(Position=0,Mandatory=$true)][ValidateSet('daily','roadmap')][string]$Command,[Parameter(ValueFromRemainingArguments=$true)][string[]]$Args)
$py = 'C:\Program Files\Python313\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }
& $py (Join-Path $PSScriptRoot 'stocklookup.py') $Command @Args
exit $LASTEXITCODE
