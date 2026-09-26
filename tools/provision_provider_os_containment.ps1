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
    [string]$SelfTestDigestSid,
    # Diagnostics only (no mutation): print the provisioning actions the plan function derives
    # from an observed-state JSON fixture (resume/idempotence/conflict tests).
    [string]$SelfTestPlanFixture,
    # Diagnostics only (no mutation): check this script's constants against the live
    # LocalAccounts cmdlet parameter limits (e.g. -Description <= 48 characters).
    [switch]$SelfTestParameterLimits,
    # Diagnostics only (no mutation): evaluate the post-provision verifier on a JSON fixture
    # {"sid": ..., "observed": ...} holding OS-native read-back representations.
    [string]$SelfTestVerifyFixture,
    # Read-only, no elevation needed: run the post-provision verifier against the live host.
    [switch]$VerifyOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$ContractVersion  = 'provider_windows_host_provisioning/v1'
$BackendId        = 'stocklookup-windows-os-enforcement'
$AccountName      = 'StockLookupProvider'
$AccountFullName  = 'StockLookup provider worker (contained)'
# New-LocalUser/Set-LocalUser -Description is limited to 48 characters (-Name to 20). This exact
# value also marks the account as ours: an account of this name with another description is a
# conflict and is never reused.
$AccountDescription = 'Contained StockLookup provider worker identity'
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

# --- preflight (read-only) -------------------------------------------------------------------------
function Get-AccountGroups([string]$Sid) {
    # SIDs of every local group whose member list holds the worker SID (compared by SID, never by
    # name). A group whose members cannot be read is reported as UNREADABLE:<group SID>, which the
    # plan and the verifier treat as a conflict (fail closed; never silently "not a member").
    # NOTE: returns ,$groups -- assign it (`$x = Get-AccountGroups $sid`); never wrap the call in
    # @(...), which nests the array and makes -contains always false (owner APPLY 2026-09-26).
    $groups = @()
    foreach ($group in Get-LocalGroup) {
        try { $members = @(Get-LocalGroupMember -Group $group -ErrorAction Stop) }
        catch { $groups += "UNREADABLE:$($group.SID.Value)"; continue }
        foreach ($member in $members) {
            if ($member.SID -and $member.SID.Value -eq $Sid) { $groups += [string]$group.SID.Value; break }
        }
    }
    return ,$groups
}

function Get-UsersMembershipAction($Groups) {
    # Pure. Exactly Users -> NOOP; no group -> ADD (once); anything else -> refuse.
    $hasUsers = $false
    $extra = @()
    foreach ($group in $Groups) {
        if ([string]$group -eq 'S-1-5-32-545') { $hasUsers = $true } else { $extra += [string]$group }
    }
    if ($extra.Count -gt 0) { Fail 'ACCOUNT_CONFLICT' "$AccountName is in groups other than Users: $($extra -join ',')" }
    if ($hasUsers) { return 'NOOP' }
    return 'ADD'
}

function Get-RuleObservation {
    $rule = Get-NetFirewallRule -Name $RuleName -ErrorAction SilentlyContinue
    if (-not $rule) { return [ordered]@{ exists = $false } }
    $address = $rule | Get-NetFirewallAddressFilter
    $port = $rule | Get-NetFirewallPortFilter
    $app = $rule | Get-NetFirewallApplicationFilter
    return [ordered]@{
        exists = $true; enabled = [string]$rule.Enabled; direction = [string]$rule.Direction; action = [string]$rule.Action
        profile = [string]$rule.Profile; group = [string]$rule.Group; protocol = [string]$port.Protocol
        remote_address = @($address.RemoteAddress | ForEach-Object { [string]$_ })
        local_address = @($address.LocalAddress | ForEach-Object { [string]$_ })
        program = [string]$app.Program; local_user = [string]($rule | Get-NetFirewallSecurityFilter).LocalUser
    }
}

function Test-WorkerSidShape([string]$Sid) {
    # A local-account SID and nothing else (e.g. never a string that captured pipeline log lines).
    return ($Sid -cmatch '^S-1-5-21-\d+-\d+-\d+-\d+$')
}

function Get-AceRecords([string]$Root) {
    # Native .NET read-back of the explicit + inherited ACEs, normalized to strings (read-only).
    $records = @()
    foreach ($ace in (Get-Acl -LiteralPath $Root).Access) {
        try { $aceSid = $ace.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value } catch { $aceSid = "UNTRANSLATABLE:$($ace.IdentityReference)" }
        $records += [ordered]@{ sid = $aceSid; type = [string]$ace.AccessControlType; rights = [string]$ace.FileSystemRights
            inheritance = [string]$ace.InheritanceFlags; propagation = [string]$ace.PropagationFlags; inherited = [bool]$ace.IsInherited }
    }
    return ,$records
}

function Resolve-DenyObservation([string]$Root, [bool]$Exists, $Aces, [string]$Sid) {
    # Pure. explicit_deny: our exact inheritable FullControl deny for the worker SID is present on the
    # root itself (not inherit-only). explicit_allow: any OTHER explicit ACE for the worker SID (allow,
    # or a narrower deny) -- a conflict.
    $observation = [ordered]@{ path = $Root; exists = $Exists; explicit_deny = $false; explicit_allow = $false }
    if (-not $Exists -or -not $Sid) { return $observation }
    foreach ($ace in @($Aces)) {
        if ($ace.inherited -or $ace.sid -ne $Sid) { continue }
        $exactDeny = $ace.type -eq 'Deny' -and $ace.rights -eq 'FullControl' `
            -and $ace.inheritance -eq 'ContainerInherit, ObjectInherit' -and $ace.propagation -eq 'None'
        if ($exactDeny) { $observation.explicit_deny = $true } else { $observation.explicit_allow = $true }
    }
    return $observation
}

function Get-DenyObservation([string]$Root, [string]$Sid) {
    $exists = Test-Path -LiteralPath $Root
    $aces = if ($exists -and $Sid) { Get-AceRecords $Root } else { @() }
    return (Resolve-DenyObservation $Root $exists $aces $Sid)
}

function Invoke-Preflight {
    $state = [ordered]@{}
    $state.elevated = Test-Elevated
    $state.current_sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $account = Get-WorkerAccount
    $state.account = [ordered]@{ exists = [bool]$account; sid = $null; description = $null; enabled = $null; groups = @() }
    if ($account) {
        $state.account.sid = $account.SID.Value
        $state.account.description = [string]$account.Description
        $state.account.enabled = [bool]$account.Enabled
        $state.account.groups = Get-AccountGroups $state.account.sid
    }
    $state.programdata_children = @()
    if (Test-Path -LiteralPath $ProgramDataStockLookup) {
        $state.programdata_children = @(Get-ChildItem -LiteralPath $ProgramDataStockLookup -Force | ForEach-Object { $_.Name })
    }
    $state.runtime_root_exists = Test-Path -LiteralPath $RuntimeRoot
    $state.blob_exists = Test-Path -LiteralPath $CredentialBlob
    $state.record = [ordered]@{ exists = (Test-Path -LiteralPath $RecordPath); worker_sid = $null }
    if ($state.record.exists) {
        try { $state.record.worker_sid = [string](Get-Content -LiteralPath $RecordPath -Raw | ConvertFrom-Json).worker_sid } catch { $state.record.worker_sid = 'UNREADABLE' }
    }
    $state.rule = Get-RuleObservation
    $state.group_rules = @(Get-NetFirewallRule -Group $RuleGroup -ErrorAction SilentlyContinue | ForEach-Object { $_.Name })
    $state.firewall_profiles = @(Get-NetFirewallProfile -PolicyStore ActiveStore | ForEach-Object {
        [ordered]@{ name = [string]$_.Name; enabled = [string]$_.Enabled; allow_local_firewall_rules = [string]$_.AllowLocalFirewallRules } })
    $state.deny_roots = @($DenyRoots | ForEach-Object { Get-DenyObservation $_ $state.account.sid })
    # CreateProcessWithLogonW needs the Secondary Logon service; it is checked, never changed.
    $state.seclogon_start_mode = [string](Get-CimInstance Win32_Service -Filter "Name='seclogon'" | Select-Object -ExpandProperty StartMode)
    return $state
}

# --- plan (pure: observed state -> actions, or a conflict) -----------------------------------------
function Test-RuleExact($Rule, [string]$Sid) {
    return ($Rule.enabled -eq 'True' -and $Rule.direction -eq 'Outbound' -and $Rule.action -eq 'Block' -and $Rule.profile -eq 'Any' `
        -and $Rule.group -eq $RuleGroup -and $Rule.protocol -eq 'Any' -and (@($Rule.remote_address) -join ',') -eq 'Any' `
        -and (@($Rule.local_address) -join ',') -eq 'Any' -and $Rule.program -eq 'Any' -and $Rule.local_user -eq "D:(A;;CC;;;$Sid)")
}

function Get-ProvisioningActions($State) {
    # Ordered actions for a resumable, idempotent APPLY. Throws PROVISIONING_REFUSED on any
    # conflicting state; it never plans the deletion of anything.
    $actions = [ordered]@{}
    $account = $State.account
    if ($account.exists) {
        if ($account.description -ne $AccountDescription) { Fail 'ACCOUNT_CONFLICT' "an account named $AccountName exists that this script did not create (description differs)" }
        $actions.users_membership = Get-UsersMembershipAction $account.groups
        $actions.account = 'REUSE_VERIFIED'
        # The logon secret is rotated only when it is unrecoverable (no blob); an existing blob is
        # validated against the account and kept, or the run fails closed.
        $actions.secret = if ($State.blob_exists) { 'KEEP_EXISTING_BLOB_AFTER_VALIDATION' } else { 'RESET_AND_STORE' }
    } else {
        if ($State.record.exists) { Fail 'RECORD_CONFLICT' 'a provisioning record exists but the worker account does not' }
        $actions.account = 'CREATE'
        $actions.users_membership = 'ENSURE_AFTER_CREATE'
        $actions.secret = 'GENERATE_AND_STORE'
    }
    $sid = $account.sid
    if ($State.record.exists -and $account.exists -and $State.record.worker_sid -ne $sid) { Fail 'RECORD_CONFLICT' 'the provisioning record names a different worker SID' }
    $unrelated = @($State.programdata_children | Where-Object { $_ -ne 'provider-runtime' })
    if ($unrelated.Count -gt 0) { Fail 'RUNTIME_ROOT_CONFLICT' "$ProgramDataStockLookup holds unrelated entries ($($unrelated -join ',')); its protected ACL would change them" }
    $actions.directories = if ($State.runtime_root_exists) { 'COMPLETE_AND_CONVERGE_ACLS' } else { 'CREATE_AND_APPLY_ACLS' }
    foreach ($name in @($State.group_rules)) {
        if ($name -ne $RuleName) { Fail 'FIREWALL_CONFLICT' "unexpected rule '$name' in group '$RuleGroup'" }
    }
    if ($State.rule.exists) {
        if (-not $sid -or -not (Test-RuleExact $State.rule $sid)) { Fail 'FIREWALL_CONFLICT' "rule '$RuleName' exists but is not the exact provisioned rule" }
        $actions.firewall = 'PRESENT_EXACT'
    } else { $actions.firewall = 'CREATE' }
    $deny = [ordered]@{}
    foreach ($root in @($State.deny_roots)) {
        if (-not $root.exists) { Fail 'DENY_ROOT_MISSING' "deny root $($root.path) does not exist" }
        if ($root.explicit_allow) { Fail 'ACL_CONFLICT' "$($root.path) carries another explicit ACE for the worker SID" }
        $deny[[string]$root.path] = if ($root.explicit_deny) { 'PRESENT' } else { 'ADD' }
    }
    $actions.deny_aces = $deny
    $actions.record = if ($State.record.exists) { 'SUPERSEDE_THEN_WRITE_LAST' } else { 'WRITE_LAST' }
    return $actions
}

function Assert-HostPrerequisites($State) {
    foreach ($profile in $State.firewall_profiles) {
        if ($profile.enabled -ne 'True') { Fail 'FIREWALL_PROFILE_DISABLED' "firewall profile $($profile.name) is not enabled" }
        if ($profile.allow_local_firewall_rules -eq 'False') { Fail 'FIREWALL_LOCAL_RULES_DISABLED' "profile $($profile.name) ignores local rules" }
    }
    if (-not $State.seclogon_start_mode -or $State.seclogon_start_mode -eq 'Disabled') {
        Fail 'SECONDARY_LOGON_UNAVAILABLE' "the Secondary Logon service (seclogon) is '$($State.seclogon_start_mode)'; the worker launch needs it (this script does not change services)"
    }
}

function Show-Plan($State, $Actions) {
    Write-Step "mode: $(if ($Apply) { 'APPLY' } else { 'PLAN (no mutation)' })"
    Write-Step "invoking identity SID: $($State.current_sid); elevated: $($State.elevated); seclogon: $($State.seclogon_start_mode)"
    Write-Step "worker account '$AccountName': $($Actions.account)$(if ($State.account.exists) { " ($($State.account.sid))" }) (standard user, Users group only, password never expires, hidden from sign-in)"
    Write-Step "Users (S-1-5-32-545) membership: $($Actions.users_membership)"
    Write-Step "logon secret: $($Actions.secret); stored ONLY as DPAPI(CurrentUser of $($State.current_sid)) blob $CredentialBlob"
    Write-Step "runtime root $RuntimeRoot (+ $($Subtrees.Values -join ', ')): $($Actions.directories)"
    Write-Step "  $ProgramDataStockLookup : SYSTEM F, Administrators F, owner RX (this folder only); no Users write"
    Write-Step "  runtime\ : SYSTEM F, Administrators F, owner M, worker RX"
    Write-Step "  state\   : SYSTEM F, Administrators F, owner M, worker M"
    Write-Step "  scratch\ : SYSTEM F, Administrators F, owner M, worker traverse only (per-launch ACLs are set by the backend)"
    Write-Step "  host\, gateway-ledger\, evidence\ : SYSTEM F, Administrators F, owner M; worker none"
    foreach ($path in $Actions.deny_aces.Keys) { Write-Step "deny ACE (OI)(CI) Full for worker SID on ${path}: $($Actions.deny_aces[$path]) (inheritance propagates; may take minutes)" }
    Write-Step "firewall rule '$RuleName' (group '$RuleGroup'): $($Actions.firewall) (Outbound, Block, Profile Any, Protocol Any, RemoteAddress Any, LocalUser = worker SID)"
    Write-Step "host record $RecordPath (non-secret completion marker): $($Actions.record)"
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
    # DACL only (protected): owner/group/SACL are left as they are. Re-applying the same DACL is a no-op.
    $acl = Get-Acl -LiteralPath $Path
    $acl.SetSecurityDescriptorSddlForm($Sddl, [Security.AccessControl.AccessControlSections]::Access)
    Set-Acl -LiteralPath $Path -AclObject $acl
}

function Write-FileAtomic([string]$Path, [byte[]]$Bytes, [string]$Sddl) {
    # Temp file in the same protected directory, its DACL set, then a rename into place.
    $temp = "$Path.tmp-$([guid]::NewGuid().ToString('N'))"
    [IO.File]::WriteAllBytes($temp, $Bytes)
    Set-ProtectedAcl $temp $Sddl
    Move-Item -LiteralPath $temp -Destination $Path -Force
}

function Protect-Secret([string]$SecretText) {
    $plain = [Text.Encoding]::UTF8.GetBytes($SecretText)
    try { return [Security.Cryptography.ProtectedData]::Protect($plain, $Entropy, [Security.Cryptography.DataProtectionScope]::CurrentUser) }
    finally { [Array]::Clear($plain, 0, $plain.Length) }
}

function Test-StoredSecret {
    # Decrypt the existing blob (owner DPAPI) and validate it against the account. The value never
    # leaves this function and is never printed.
    Add-Type -AssemblyName System.DirectoryServices.AccountManagement
    $plain = [Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes($CredentialBlob), $Entropy,
        [Security.Cryptography.DataProtectionScope]::CurrentUser)
    try {
        $context = New-Object System.DirectoryServices.AccountManagement.PrincipalContext([System.DirectoryServices.AccountManagement.ContextType]::Machine)
        try { return [bool]$context.ValidateCredentials($AccountName, [Text.Encoding]::UTF8.GetString($plain)) } finally { $context.Dispose() }
    } finally { [Array]::Clear($plain, 0, $plain.Length) }
}

function Invoke-Apply($State, $Actions) {
    if (-not $State.elevated) { Fail 'NOT_ELEVATED' 'run -Apply from an elevated (Administrator) PowerShell' }
    if (-not $OwnerSid) { Fail 'OWNER_SID_REQUIRED' 'pass -OwnerSid <owner SID> (the non-elevated Producer identity)' }
    if ($OwnerSid -ne $State.current_sid) { Fail 'OWNER_MISMATCH' "elevated identity $($State.current_sid) is not the owner $OwnerSid (DPAPI must bind to the owner)" }
    Add-Type -AssemblyName System.Security
    $o = $OwnerSid

    # 0. The completion record is moved aside first: a run that fails from here on never looks provisioned.
    if ($Actions.record -eq 'SUPERSEDE_THEN_WRITE_LAST') {
        $superseded = "$RecordPath.superseded-$((Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ'))"
        Write-Step "moving the existing completion record aside to $superseded"
        Move-Item -LiteralPath $RecordPath -Destination $superseded
    }

    # 1. directories + owner-only ACLs (the host dir is protected before any secret is stored) --------
    foreach ($dir in @($ProgramDataStockLookup, $RuntimeRoot) + @($Subtrees.Values | ForEach-Object { Join-Path $RuntimeRoot $_ })) {
        if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
    }
    Set-ProtectedAcl $ProgramDataStockLookup "D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;;0x1200a9;;;$o)"
    Set-ProtectedAcl $RuntimeRoot "D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;;0x1200a9;;;$o)"
    foreach ($private in @('host', 'gateway-ledger', 'evidence')) {
        Set-ProtectedAcl (Join-Path $RuntimeRoot $private) "D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;0x1301bf;;;$o)"
    }

    # 2. account + secret (a created/reset secret is stored at once, so it is never lost) --------------
    $blobSddl = "D:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;FA;;;$o)"
    if ($Actions.account -eq 'CREATE') {
        $secretText = New-LogonSecret
        Write-Step "creating local account $AccountName"
        New-LocalUser -Name $AccountName -Password (ConvertTo-SecureString -String $secretText -AsPlainText -Force) `
            -FullName $AccountFullName -Description $AccountDescription `
            -PasswordNeverExpires -UserMayNotChangePassword -AccountNeverExpires | Out-Null
        Write-FileAtomic $CredentialBlob (Protect-Secret $secretText) $blobSddl
        $secretText = $null
    } elseif ($Actions.secret -eq 'RESET_AND_STORE') {
        $secretText = New-LogonSecret
        Write-Step "the logon secret of $AccountName is unrecoverable (no blob): resetting it once"
        Set-LocalUser -Name $AccountName -Password (ConvertTo-SecureString -String $secretText -AsPlainText -Force)
        Write-FileAtomic $CredentialBlob (Protect-Secret $secretText) $blobSddl
        $secretText = $null
    } else {
        if (-not (Test-StoredSecret)) { Fail 'CREDENTIAL_BLOB_MISMATCH' "the stored logon secret does not validate for $AccountName (not rotated automatically; owner decision required)" }
        Write-Step "reusing $AccountName and its stored logon secret (validated)"
    }
    $account = Get-WorkerAccount
    $sid = $account.SID.Value
    if ($State.account.exists -and $sid -ne $State.account.sid) { Fail 'ACCOUNT_CONFLICT' 'the worker SID changed during provisioning' }
    Set-LocalUser -Name $AccountName -Description $AccountDescription -PasswordNeverExpires $true -UserMayChangePassword $false
    if (-not $account.Enabled) { Enable-LocalUser -Name $AccountName }
    # Membership re-read by SID after create/reuse: exactly Users -> no-op; none -> add once; other -> refuse.
    $groups = Get-AccountGroups $sid
    if ((Get-UsersMembershipAction $groups) -eq 'ADD') {
        Write-Step "adding $AccountName to Users (S-1-5-32-545)"
        Add-LocalGroupMember -SID 'S-1-5-32-545' -Member $AccountName
    }
    $userList = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\SpecialAccounts\UserList'
    if (-not (Test-Path $userList)) { New-Item -Path $userList -Force | Out-Null }
    New-ItemProperty -Path $userList -Name $AccountName -PropertyType DWord -Value 0 -Force | Out-Null

    # 3. worker-specific ACLs ---------------------------------------------------------------------------
    $w = $sid
    Set-ProtectedAcl $ProgramDataStockLookup "D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;;0x1200a9;;;$o)(A;;0x100020;;;$w)"
    Set-ProtectedAcl $RuntimeRoot "D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;;0x1200a9;;;$o)(A;;0x100020;;;$w)"
    Set-ProtectedAcl (Join-Path $RuntimeRoot 'runtime')  "D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;0x1301bf;;;$o)(A;OICI;0x1200a9;;;$w)"
    Set-ProtectedAcl (Join-Path $RuntimeRoot 'state')    "D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;0x1301bf;;;$o)(A;OICI;0x1301bf;;;$w)"
    Set-ProtectedAcl (Join-Path $RuntimeRoot 'scratch')  "D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;0x1301bf;;;$o)(A;;0x100020;;;$w)"

    # 4. deny ACEs on owner-data roots (added once; never duplicated) -----------------------------------
    foreach ($root in $DenyRoots) {
        $observed = Get-DenyObservation $root $sid
        if ($observed.explicit_allow) { Fail 'ACL_CONFLICT' "$root carries another explicit ACE for the worker SID" }
        if (-not $observed.explicit_deny) {
            Write-Step "adding worker deny ACE on $root (propagating)"
            $acl = Get-Acl -LiteralPath $root
            $identity = New-Object Security.Principal.SecurityIdentifier($sid)
            $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($identity, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Deny')))
            Set-Acl -LiteralPath $root -AclObject $acl
        }
    }

    # 5. firewall rule (created once; an existing rule must already be exact) --------------------------
    $rule = Get-RuleObservation
    if (-not $rule.exists) {
        New-NetFirewallRule -Name $RuleName -DisplayName 'StockLookup provider worker: deny all direct outbound' -Group $RuleGroup `
            -Description 'The contained provider worker identity has no direct network egress; its only path is the local named-pipe egress gateway.' `
            -Direction Outbound -Action Block -Profile Any -Protocol Any -RemoteAddress Any -LocalAddress Any -Program Any `
            -LocalUser "D:(A;;CC;;;$sid)" -Enabled True | Out-Null
    } elseif (-not (Test-RuleExact $rule $sid)) { Fail 'FIREWALL_CONFLICT' "rule '$RuleName' is not the exact provisioned rule" }
    # No return value: every Write-Step above is pipeline output, so a returned SID would arrive
    # concatenated with the step lines (owner APPLY 2026-09-26). The caller re-reads the SID.
}

function Resolve-ProvisionedWorkerSid($State) {
    # The worker SID read back from the OS after APPLY -- never taken from a function's pipeline output.
    $account = Get-WorkerAccount
    if (-not $account) { Fail 'ACCOUNT_MISSING' "$AccountName does not exist after APPLY" }
    $sid = [string]$account.SID.Value
    if (-not (Test-WorkerSidShape $sid)) { Fail 'WORKER_SID_MALFORMED' "unexpected worker SID form '$sid'" }
    if ($State.account.exists -and $sid -ne $State.account.sid) { Fail 'ACCOUNT_CONFLICT' 'the worker SID changed during provisioning' }
    return $sid
}

function Get-VerificationObservation {
    # Read-only snapshot of every provisioned invariant, in the OS's own normalized representation.
    $account = Get-WorkerAccount
    $observed = [ordered]@{ account = [ordered]@{ exists = [bool]$account; sid = $null; enabled = $null; description = $null; groups = @() } }
    if ($account) {
        $observed.account.sid = [string]$account.SID.Value
        $observed.account.enabled = [bool]$account.Enabled
        $observed.account.description = [string]$account.Description
        $observed.account.groups = Get-AccountGroups $observed.account.sid
    }
    $observed.dirs = @(foreach ($dir in @($RuntimeRoot) + @($Subtrees.Values | ForEach-Object { Join-Path $RuntimeRoot $_ })) {
        $exists = Test-Path -LiteralPath $dir
        [ordered]@{ path = $dir; exists = $exists; protected = ($exists -and (Get-Acl -LiteralPath $dir).AreAccessRulesProtected -eq $true) }
    })
    $observed.blob_exists = Test-Path -LiteralPath $CredentialBlob
    $observed.rule = Get-RuleObservation
    $observed.group_rule_count = @(Get-NetFirewallRule -Group $RuleGroup -ErrorAction SilentlyContinue).Count
    $observed.deny_roots = @(foreach ($root in $DenyRoots) {
        $exists = Test-Path -LiteralPath $root
        [ordered]@{ path = $root; exists = $exists; aces = $(if ($exists) { Get-AceRecords $root } else { @() }) }
    })
    return $observed
}

function Get-VerificationFailures($Observed, [string]$Sid) {
    # Pure: observation + expected worker SID -> failure codes. Every invariant except the
    # completion record itself (written only after this passes).
    $failures = @()
    if (-not (Test-WorkerSidShape $Sid)) { return ,@('WORKER_SID_MALFORMED') }
    $account = $Observed.account
    if (-not $account.exists -or $account.sid -ne $Sid -or $account.enabled -ne $true -or $account.description -ne $AccountDescription) { $failures += 'ACCOUNT' }
    foreach ($group in @($account.groups)) { if ($group -ne 'S-1-5-32-545') { $failures += "GROUP:$group" } }
    foreach ($dir in @($Observed.dirs)) {
        if (-not $dir.exists) { $failures += "DIR:$($dir.path)" } elseif ($dir.protected -ne $true) { $failures += "ACL_NOT_PROTECTED:$($dir.path)" }
    }
    if (-not $Observed.blob_exists) { $failures += 'CREDENTIAL_BLOB' }
    if (-not $Observed.rule.exists -or -not (Test-RuleExact $Observed.rule $Sid)) { $failures += 'FIREWALL_RULE' }
    if ($Observed.group_rule_count -ne 1) { $failures += 'FIREWALL_GROUP' }
    foreach ($root in @($Observed.deny_roots)) {
        $deny = Resolve-DenyObservation ([string]$root.path) ([bool]$root.exists) $root.aces $Sid
        if (-not $deny.explicit_deny -or $deny.explicit_allow) { $failures += "DENY_ACE:$($root.path)" }
    }
    return ,$failures
}

function Test-Provisioned([string]$Sid) { return ,(Get-VerificationFailures (Get-VerificationObservation) $Sid) }

function Write-CompletionRecord([string]$Sid) {
    if (-not (Test-WorkerSidShape $Sid)) { Fail 'WORKER_SID_MALFORMED' 'refusing to write a completion record for a malformed worker SID' }
    $record = [ordered]@{
        contract_version = $ContractVersion; backend_id = $BackendId; worker_account = $AccountName; worker_sid = $Sid
        owner_sid = $OwnerSid; runtime_root = $RuntimeRoot; subtrees = $Subtrees
        firewall_rule_name = $RuleName; firewall_policy_sha256 = (Get-Sha256Hex (ConvertTo-CanonicalJson (Get-FirewallPolicy $Sid)))
        credential_blob = $CredentialBlob; denied_roots_provisioned = @($DenyRoots)
        provisioned_at_utc = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
        provisioner_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $bytes = (New-Object Text.UTF8Encoding($false)).GetBytes(($record | ConvertTo-Json -Depth 5))
    Write-FileAtomic $RecordPath $bytes "D:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;0x1200a9;;;$OwnerSid)"
}

# --- main --------------------------------------------------------------------------------------------
if ($SelfTestDigestSid) {
    Write-Output (Get-Sha256Hex (ConvertTo-CanonicalJson (Get-FirewallPolicy $SelfTestDigestSid)))
    exit 0
}
if ($SelfTestParameterLimits) {
    $limits = [ordered]@{}
    foreach ($pair in @(@('New-LocalUser', 'Name', $AccountName), @('New-LocalUser', 'Description', $AccountDescription),
                        @('Set-LocalUser', 'Description', $AccountDescription), @('New-LocalUser', 'FullName', $AccountFullName))) {
        $attribute = (Get-Command $pair[0]).Parameters[$pair[1]].Attributes | Where-Object { $_ -is [System.Management.Automation.ValidateLengthAttribute] }
        $max = if ($attribute) { [int]$attribute.MaxLength } else { $null }
        $limits["$($pair[0]) -$($pair[1])"] = [ordered]@{ length = $pair[2].Length; max = $max; ok = ($null -eq $max -or $pair[2].Length -le $max) }
    }
    Write-Output ($limits | ConvertTo-Json -Depth 4 -Compress)
    exit 0
}
if ($SelfTestPlanFixture) {
    $fixture = Get-Content -LiteralPath $SelfTestPlanFixture -Raw | ConvertFrom-Json
    try { Write-Output ([ordered]@{ ok = $true; actions = (Get-ProvisioningActions $fixture) } | ConvertTo-Json -Depth 5 -Compress) }
    catch { Write-Output ([ordered]@{ ok = $false; refused = [string]$_.Exception.Message } | ConvertTo-Json -Compress) }
    exit 0
}
if ($SelfTestVerifyFixture) {
    $fixture = Get-Content -LiteralPath $SelfTestVerifyFixture -Raw | ConvertFrom-Json
    Write-Output ([ordered]@{ failures = (Get-VerificationFailures $fixture.observed ([string]$fixture.sid)) } | ConvertTo-Json -Depth 5 -Compress)
    exit 0
}
if ($VerifyOnly) {
    # Read-only, non-elevated: the post-provision verifier against the live host, SID read from the OS.
    $account = Get-WorkerAccount
    $liveSid = if ($account) { [string]$account.SID.Value } else { '' }
    $failures = Get-VerificationFailures (Get-VerificationObservation) $liveSid
    Write-Output ([ordered]@{ worker_sid = $liveSid; record_exists = (Test-Path -LiteralPath $RecordPath); failures = $failures } | ConvertTo-Json -Depth 4 -Compress)
    if ($failures.Count -gt 0) { exit 2 }
    exit 0
}
if ($Plan -and $Apply) { Fail 'MODE' 'choose -Plan or -Apply' }
$state = Invoke-Preflight
Assert-HostPrerequisites $state
$actions = Get-ProvisioningActions $state
Show-Plan $state $actions
if (-not $Apply) {
    Write-Step 'PLAN ONLY: nothing was changed. Re-run elevated with -Apply -OwnerSid <owner SID> to provision.'
    exit 0
}
Invoke-Apply $state $actions
$sid = Resolve-ProvisionedWorkerSid $state
$failures = Test-Provisioned $sid
if ($failures.Count -gt 0) {
    Write-Step "POST-PROVISION VERIFICATION FAILED (no completion record written; re-running -Apply resumes): $($failures -join '; ')"
    exit 2
}
Write-CompletionRecord $sid
if (-not (Test-Path -LiteralPath $RecordPath)) { Write-Step 'COMPLETION RECORD NOT WRITTEN'; exit 2 }
Write-Step "PROVISIONED: worker $AccountName $sid; runtime root $RuntimeRoot; firewall rule $RuleName; record $RecordPath"
Write-Step 'Next (non-elevated owner shell): python tools\run_provider_os_containment_qualification.py'
exit 0
