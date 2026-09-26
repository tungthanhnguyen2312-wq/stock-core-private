<#
.SYNOPSIS
  Bounded, idempotent Windows provisioning for the provider worker OS containment
  (WINDOWS_PROVIDER_RUNTIME_OS_CONTAINMENT_AND_ATTESTATION_V1).

.DESCRIPTION
  Handles ONLY:
    1. the dedicated standard local worker account (StockLookupProvider; never a Codex/sandbox/
       service account; not a member of any group but Users; hidden from the sign-in screen);
       its random logon secret is generated in memory, set on the account, and stored only as a
       DPAPI blob (current-user scope of the invoking owner, fixed entropy) in the protected host
       directory -- it is never printed, logged or written anywhere else;
    2. the provider runtime root C:\ProgramData\StockLookup\provider-runtime and its subtrees with
       explicit protected ACLs;
    3. an explicit deny ACE for the worker SID on each owner-data root the worker would otherwise
       reach (a new standard account inherits Authenticated Users/Users access there);
    4. one Windows Defender Firewall rule blocking ALL outbound traffic (every protocol, IPv4 and
       IPv6, every remote address) for the worker SID;
    5. the non-secret host provisioning record the Producer's backend reads.
  It changes nothing else: no service, no scheduled task, no security-policy/UAC/Defender change,
  no firewall default change, no other account or rule. Unrelated state is preserved.

  Default mode is -Plan: preflight + the planned non-secret changes, no mutation. -Apply requires
  an elevated (Administrator) PowerShell of the OWNER account (the DPAPI blob is bound to it), and
  verifies every provisioned invariant afterwards. Conflicting identities/rules fail closed.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File tools\provision_provider_os_containment.ps1 -Plan
  powershell -NoProfile -ExecutionPolicy Bypass -File tools\provision_provider_os_containment.ps1 -Apply -OwnerSid S-1-5-21-...-1001
#>
[CmdletBinding()]
param(
    [switch]$Plan,
    [switch]$Apply,
    # The owner (Producer) identity. Required with -Apply so an elevation under a different admin
    # account cannot silently bind the DPAPI blob and ACLs to the wrong identity.
    [string]$OwnerSid,
    # Owner-data roots the worker must never reach (worker-SID deny ACE, inheritable).
    [string[]]$DenyRoots = @('C:\Projects\StockLookup'),
    # Diagnostics only (no mutation, no elevation): print the firewall policy digest for a SID so
    # it can be compared with provider_windows_os_backend.firewall_policy_sha256.
    [string]$SelfTestDigestSid
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$ContractVersion  = 'provider_windows_host_provisioning/v1'
$BackendId        = 'stocklookup-windows-os-enforcement'
$AccountName      = 'StockLookupProvider'
$AccountFullName  = 'StockLookup provider worker (contained)'
$RuntimeRoot      = 'C:\ProgramData\StockLookup\provider-runtime'
$ProgramDataStockLookup = 'C:\ProgramData\StockLookup'
$Subtrees         = [ordered]@{ host = 'host'; runtime = 'runtime'; state = 'state'; scratch = 'scratch'; ledger = 'gateway-ledger'; evidence = 'evidence' }
$RuleName         = 'StockLookup-ProviderWorker-DenyAllOutbound'
$RuleGroup        = 'StockLookup Provider Runtime'
$Entropy          = [Text.Encoding]::UTF8.GetBytes('StockLookupProviderWorkerLogon/v1')
$CredentialBlob   = Join-Path (Join-Path $RuntimeRoot 'host') 'worker-logon.dpapi'
$RecordPath       = Join-Path (Join-Path $RuntimeRoot 'host') 'provisioning_record.json'

function Write-Step([string]$Text) { Write-Output "[provision] $Text" }
function Fail([string]$Code, [string]$Text) { throw "PROVISIONING_REFUSED:${Code}: $Text" }

function Test-Elevated {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-WorkerAccount { Get-LocalUser -Name $AccountName -ErrorAction SilentlyContinue }

function Get-Sddl([string]$Path) { (Get-Acl -LiteralPath $Path).Sddl }

# --- canonical JSON + SHA-256 identical to provider_build_manifest.canonical_sha256 -----------------
function ConvertTo-CanonicalJson($Value) {
    if ($null -eq $Value) { return 'null' }
    if ($Value -is [bool]) { if ($Value) { return 'true' } else { return 'false' } }
    if ($Value -is [int] -or $Value -is [long]) { return [string]$Value }
    if ($Value -is [string]) {
        $sb = New-Object Text.StringBuilder
        [void]$sb.Append('"')
        foreach ($ch in $Value.ToCharArray()) {
            switch ($ch) {
                '"'  { [void]$sb.Append('\"') }
                '\'  { [void]$sb.Append('\\') }
                "`n" { [void]$sb.Append('\n') }
                "`r" { [void]$sb.Append('\r') }
                "`t" { [void]$sb.Append('\t') }
                "`b" { [void]$sb.Append('\b') }
                "`f" { [void]$sb.Append('\f') }
                default {
                    if ([int]$ch -lt 0x20) { [void]$sb.Append(('\u{0:x4}' -f [int]$ch)) } else { [void]$sb.Append($ch) }
                }
            }
        }
        [void]$sb.Append('"')
        return $sb.ToString()
    }
    if ($Value -is [System.Collections.IDictionary]) {
        $keys = @($Value.Keys | ForEach-Object { [string]$_ })
        [Array]::Sort($keys, [StringComparer]::Ordinal)
        $parts = foreach ($key in $keys) { (ConvertTo-CanonicalJson $key) + ':' + (ConvertTo-CanonicalJson $Value[$key]) }
        return '{' + ($parts -join ',') + '}'
    }
    if ($Value -is [System.Collections.IEnumerable]) {
        $parts = foreach ($item in $Value) { ConvertTo-CanonicalJson $item }
        return '[' + ($parts -join ',') + ']'
    }
    return (ConvertTo-CanonicalJson ([string]$Value))
}

function Get-Sha256Hex([string]$Text) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return (($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text)) | ForEach-Object { $_.ToString('x2') }) -join '') }
    finally { $sha.Dispose() }
}

function Get-FirewallPolicy([string]$Sid) {
    [ordered]@{
        contract_version = 'provider_windows_firewall_policy/v1'; rule_name = $RuleName; group = $RuleGroup
        direction = 'Outbound'; action = 'Block'; profile = 'Any'; protocol = 'Any'; remote_address = @('Any')
        local_address = @('Any'); program = 'Any'; local_user_sddl = "D:(A;;CC;;;$Sid)"; enabled = 'True'
    }
}

# --- preflight -------------------------------------------------------------------------------------
function Invoke-Preflight {
    $state = [ordered]@{}
    $state.elevated = Test-Elevated
    $state.current_sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $state.os = (Get-CimInstance Win32_OperatingSystem | Select-Object -ExpandProperty Caption)
    $account = Get-WorkerAccount
    $state.account_exists = [bool]$account
    $state.account_sid = if ($account) { $account.SID.Value } else { $null }
    if ($account) {
        $groups = @()
        foreach ($group in Get-LocalGroup) {
            try {
                if (Get-LocalGroupMember -Group $group -Member $AccountName -ErrorAction Stop) { $groups += $group.SID.Value }
            } catch { }
        }
        $state.account_groups = $groups
    }
    $state.runtime_root_exists = Test-Path -LiteralPath $RuntimeRoot
    $state.record_exists = Test-Path -LiteralPath $RecordPath
    $rules = @(Get-NetFirewallRule -Name $RuleName -ErrorAction SilentlyContinue)
    $state.rule_exists = $rules.Count -gt 0
    $state.group_rules = @(Get-NetFirewallRule -Group $RuleGroup -ErrorAction SilentlyContinue | ForEach-Object { $_.Name })
    $state.firewall_profiles = @(Get-NetFirewallProfile -PolicyStore ActiveStore | ForEach-Object {
        [ordered]@{ name = [string]$_.Name; enabled = [string]$_.Enabled; allow_local_firewall_rules = [string]$_.AllowLocalFirewallRules } })
    $state.deny_roots = @($DenyRoots | ForEach-Object { [ordered]@{ path = $_; exists = (Test-Path -LiteralPath $_) } })
    # CreateProcessWithLogonW needs the Secondary Logon service; it is checked, never changed.
    $state.seclogon_start_mode = [string](Get-CimInstance Win32_Service -Filter "Name='seclogon'" | Select-Object -ExpandProperty StartMode)
    return $state
}

function Assert-NoConflict($State) {
    if ($State.account_exists) {
        $extra = @($State.account_groups | Where-Object { $_ -ne 'S-1-5-32-545' })
        if ($extra.Count -gt 0) { Fail 'ACCOUNT_CONFLICT' "existing $AccountName is in groups other than Users: $($extra -join ',')" }
        if ($State.record_exists) {
            $record = Get-Content -LiteralPath $RecordPath -Raw | ConvertFrom-Json
            if ($record.worker_sid -ne $State.account_sid) { Fail 'ACCOUNT_CONFLICT' 'host record names a different worker SID' }
        }
    }
    foreach ($name in $State.group_rules) {
        if ($name -ne $RuleName) { Fail 'FIREWALL_CONFLICT' "unexpected rule '$name' in group '$RuleGroup'" }
    }
    foreach ($profile in $State.firewall_profiles) {
        if ($profile.enabled -ne 'True') { Fail 'FIREWALL_PROFILE_DISABLED' "firewall profile $($profile.name) is not enabled" }
        if ($profile.allow_local_firewall_rules -eq 'False') { Fail 'FIREWALL_LOCAL_RULES_DISABLED' "profile $($profile.name) ignores local rules" }
    }
    foreach ($root in $State.deny_roots) {
        if (-not $root.exists) { Fail 'DENY_ROOT_MISSING' "deny root $($root.path) does not exist" }
    }
    if (-not $State.seclogon_start_mode -or $State.seclogon_start_mode -eq 'Disabled') {
        Fail 'SECONDARY_LOGON_UNAVAILABLE' "the Secondary Logon service (seclogon) is '$($State.seclogon_start_mode)'; the worker launch needs it (this script does not change services)"
    }
}

function Show-Plan($State) {
    Write-Step "mode: $(if ($Apply) { 'APPLY' } else { 'PLAN (no mutation)' })"
    Write-Step "invoking identity SID: $($State.current_sid); elevated: $($State.elevated); seclogon: $($State.seclogon_start_mode)"
    Write-Step "worker account '$AccountName': $(if ($State.account_exists) { "exists ($($State.account_sid)) -> reuse, reset logon secret" } else { 'create (standard user, Users group only, password never expires, hidden from sign-in)' })"
    Write-Step "logon secret: random 48-character, set on the account, stored ONLY as DPAPI(CurrentUser of $($State.current_sid)) blob $CredentialBlob"
    Write-Step "runtime root $RuntimeRoot (+ $($Subtrees.Values -join ', ')): protected ACLs"
    Write-Step "  $ProgramDataStockLookup : SYSTEM F, Administrators F, owner RX (this folder only); no Users write"
    Write-Step "  runtime\ : SYSTEM F, Administrators F, owner M, worker RX"
    Write-Step "  state\   : SYSTEM F, Administrators F, owner M, worker M"
    Write-Step "  scratch\ : SYSTEM F, Administrators F, owner M, worker traverse only (per-launch ACLs are set by the backend)"
    Write-Step "  host\, gateway-ledger\, evidence\ : SYSTEM F, Administrators F, owner M; worker none"
    foreach ($root in $State.deny_roots) { Write-Step "deny ACE (OI)(CI) Full for worker SID on $($root.path) (inheritance propagates; may take minutes)" }
    Write-Step "firewall rule '$RuleName' (group '$RuleGroup'): Outbound, Block, Profile Any, Protocol Any, RemoteAddress Any, LocalUser = worker SID"
    Write-Step "host record $RecordPath (non-secret)"
}

# --- mutation --------------------------------------------------------------------------------------
function New-LogonSecret {
    $alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!#%+-=?@'
    $bytes = New-Object byte[] 48
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    $chars = foreach ($b in $bytes) { $alphabet[$b % $alphabet.Length] }
    # Guarantee complexity classes regardless of the random draw.
    return (-join $chars) + 'Aa7!'
}

function Set-ProtectedAcl([string]$Path, [string]$Sddl) {
    # DACL only (protected): owner/group/SACL are left as they are.
    $acl = Get-Acl -LiteralPath $Path
    $acl.SetSecurityDescriptorSddlForm($Sddl, [Security.AccessControl.AccessControlSections]::Access)
    Set-Acl -LiteralPath $Path -AclObject $acl
}

function Invoke-Apply($State) {
    if (-not $State.elevated) { Fail 'NOT_ELEVATED' 'run -Apply from an elevated (Administrator) PowerShell' }
    if (-not $OwnerSid) { Fail 'OWNER_SID_REQUIRED' 'pass -OwnerSid <owner SID> (the non-elevated Producer identity)' }
    if ($OwnerSid -ne $State.current_sid) { Fail 'OWNER_MISMATCH' "elevated identity $($State.current_sid) is not the owner $OwnerSid (DPAPI must bind to the owner)" }
    Add-Type -AssemblyName System.Security

    # 1. account + secret ----------------------------------------------------------------------------
    $secretText = New-LogonSecret
    $secure = ConvertTo-SecureString -String $secretText -AsPlainText -Force
    $account = Get-WorkerAccount
    if (-not $account) {
        Write-Step "creating local account $AccountName"
        $account = New-LocalUser -Name $AccountName -Password $secure -FullName $AccountFullName `
            -Description 'Dedicated contained provider worker identity (no interactive use).' `
            -PasswordNeverExpires -UserMayNotChangePassword -AccountNeverExpires
    } else {
        Write-Step "resetting logon secret of existing $AccountName"
        Set-LocalUser -Name $AccountName -Password $secure -PasswordNeverExpires $true -UserMayChangePassword $false
        Enable-LocalUser -Name $AccountName
    }
    $account = Get-WorkerAccount
    $sid = $account.SID.Value
    try { Add-LocalGroupMember -SID 'S-1-5-32-545' -Member $AccountName -ErrorAction Stop } catch { if ($_.Exception.Message -notmatch 'already a member') { throw } }
    $userList = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\SpecialAccounts\UserList'
    if (-not (Test-Path $userList)) { New-Item -Path $userList -Force | Out-Null }
    New-ItemProperty -Path $userList -Name $AccountName -PropertyType DWord -Value 0 -Force | Out-Null

    # 2. directories + ACLs ---------------------------------------------------------------------------
    foreach ($dir in @($ProgramDataStockLookup, $RuntimeRoot) + @($Subtrees.Values | ForEach-Object { Join-Path $RuntimeRoot $_ })) {
        if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
    }
    $o = $OwnerSid; $w = $sid
    Set-ProtectedAcl $ProgramDataStockLookup "D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;;0x1200a9;;;$o)(A;;0x100020;;;$w)"
    Set-ProtectedAcl $RuntimeRoot "D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;;0x1200a9;;;$o)(A;;0x100020;;;$w)"
    Set-ProtectedAcl (Join-Path $RuntimeRoot 'runtime')  "D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;0x1301bf;;;$o)(A;OICI;0x1200a9;;;$w)"
    Set-ProtectedAcl (Join-Path $RuntimeRoot 'state')    "D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;0x1301bf;;;$o)(A;OICI;0x1301bf;;;$w)"
    Set-ProtectedAcl (Join-Path $RuntimeRoot 'scratch')  "D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;0x1301bf;;;$o)(A;;0x100020;;;$w)"
    foreach ($private in @('host', 'gateway-ledger', 'evidence')) {
        Set-ProtectedAcl (Join-Path $RuntimeRoot $private) "D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;0x1301bf;;;$o)"
    }

    # 3. DPAPI blob (owner current-user scope) ---------------------------------------------------------
    $plain = [Text.Encoding]::UTF8.GetBytes($secretText)
    try {
        $blob = [Security.Cryptography.ProtectedData]::Protect($plain, $Entropy, [Security.Cryptography.DataProtectionScope]::CurrentUser)
    } finally { [Array]::Clear($plain, 0, $plain.Length) }
    [IO.File]::WriteAllBytes($CredentialBlob, $blob)
    Set-ProtectedAcl $CredentialBlob "D:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;FA;;;$o)"
    $secretText = $null; $secure = $null

    # 4. deny ACEs on owner-data roots ------------------------------------------------------------------
    $provisionedDeny = @()
    foreach ($root in $DenyRoots) {
        $acl = Get-Acl -LiteralPath $root
        $identity = New-Object Security.Principal.SecurityIdentifier($sid)
        $rule = New-Object Security.AccessControl.FileSystemAccessRule($identity, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Deny')
        $present = @($acl.Access | Where-Object { $_.AccessControlType -eq 'Deny' -and $_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -eq $sid -and -not $_.IsInherited })
        if ($present.Count -eq 0) {
            Write-Step "adding worker deny ACE on $root (propagating)"
            $acl.AddAccessRule($rule)
            Set-Acl -LiteralPath $root -AclObject $acl
        }
        $provisionedDeny += $root
    }

    # 5. firewall rule --------------------------------------------------------------------------------
    $existing = Get-NetFirewallRule -Name $RuleName -ErrorAction SilentlyContinue
    if ($existing) { Remove-NetFirewallRule -Name $RuleName }
    New-NetFirewallRule -Name $RuleName -DisplayName 'StockLookup provider worker: deny all direct outbound' -Group $RuleGroup `
        -Description 'The contained provider worker identity has no direct network egress; its only path is the local named-pipe egress gateway.' `
        -Direction Outbound -Action Block -Profile Any -Protocol Any -RemoteAddress Any -LocalAddress Any -Program Any `
        -LocalUser "D:(A;;CC;;;$sid)" -Enabled True | Out-Null

    # 6. host record ------------------------------------------------------------------------------------
    $record = [ordered]@{
        contract_version = $ContractVersion; backend_id = $BackendId; worker_account = $AccountName; worker_sid = $sid
        owner_sid = $OwnerSid; runtime_root = $RuntimeRoot; subtrees = $Subtrees
        firewall_rule_name = $RuleName; firewall_policy_sha256 = (Get-Sha256Hex (ConvertTo-CanonicalJson (Get-FirewallPolicy $sid)))
        credential_blob = $CredentialBlob; denied_roots_provisioned = @($provisionedDeny)
        provisioned_at_utc = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
        provisioner_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    [IO.File]::WriteAllText($RecordPath, ($record | ConvertTo-Json -Depth 5), (New-Object Text.UTF8Encoding($false)))
    Set-ProtectedAcl $RecordPath "D:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;0x1200a9;;;$o)"
    return $sid
}

function Test-Provisioned([string]$Sid) {
    $failures = @()
    $account = Get-WorkerAccount
    if (-not $account -or $account.SID.Value -ne $Sid -or -not $account.Enabled) { $failures += 'ACCOUNT' }
    foreach ($group in Get-LocalGroup) {
        if ($group.SID.Value -eq 'S-1-5-32-545') { continue }
        try { if (Get-LocalGroupMember -Group $group -Member $AccountName -ErrorAction Stop) { $failures += "GROUP:$($group.Name)" } } catch { }
    }
    foreach ($dir in @($RuntimeRoot) + @($Subtrees.Values | ForEach-Object { Join-Path $RuntimeRoot $_ })) {
        if (-not (Test-Path -LiteralPath $dir)) { $failures += "DIR:$dir" } elseif ((Get-Acl -LiteralPath $dir).AreAccessRulesProtected -ne $true) { $failures += "ACL_NOT_PROTECTED:$dir" }
    }
    if (-not (Test-Path -LiteralPath $CredentialBlob)) { $failures += 'CREDENTIAL_BLOB' }
    $rule = Get-NetFirewallRule -Name $RuleName -ErrorAction SilentlyContinue
    if (-not $rule -or [string]$rule.Action -ne 'Block' -or [string]$rule.Direction -ne 'Outbound' -or [string]$rule.Enabled -ne 'True') { $failures += 'FIREWALL_RULE' }
    elseif ([string]($rule | Get-NetFirewallSecurityFilter).LocalUser -ne "D:(A;;CC;;;$Sid)") { $failures += 'FIREWALL_LOCAL_USER' }
    foreach ($root in $DenyRoots) {
        $deny = @((Get-Acl -LiteralPath $root).Access | Where-Object { $_.AccessControlType -eq 'Deny' -and $_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -eq $Sid })
        if ($deny.Count -eq 0) { $failures += "DENY_ACE:$root" }
    }
    if (-not (Test-Path -LiteralPath $RecordPath)) { $failures += 'RECORD' }
    return ,$failures
}

# --- main --------------------------------------------------------------------------------------------
if ($SelfTestDigestSid) {
    Write-Output (Get-Sha256Hex (ConvertTo-CanonicalJson (Get-FirewallPolicy $SelfTestDigestSid)))
    exit 0
}
if ($Plan -and $Apply) { Fail 'MODE' 'choose -Plan or -Apply' }
$state = Invoke-Preflight
Assert-NoConflict $state
Show-Plan $state
if (-not $Apply) {
    Write-Step 'PLAN ONLY: nothing was changed. Re-run elevated with -Apply -OwnerSid <owner SID> to provision.'
    exit 0
}
$sid = Invoke-Apply $state
$failures = Test-Provisioned $sid
if ($failures.Count -gt 0) {
    Write-Step "POST-PROVISION VERIFICATION FAILED: $($failures -join '; ')"
    exit 2
}
Write-Step "PROVISIONED: worker $AccountName $sid; runtime root $RuntimeRoot; firewall rule $RuleName; record $RecordPath"
Write-Step 'Next (non-elevated owner shell): python tools\run_provider_os_containment_qualification.py'
exit 0
