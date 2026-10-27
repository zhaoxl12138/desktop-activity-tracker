param(
    [Parameter(Mandatory=$true)][string]$Root,
    [Parameter(Mandatory=$true)][string]$PlanPath,
    [switch]$Execute,
    [string]$BackupRoot
)
$ErrorActionPreference = 'Stop'

function Get-ReportHash([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-','') }
    finally { $stream.Dispose(); $algorithm.Dispose() }
}

function Assert-Unlinked([string]$Path) {
    $cursor = [IO.Path]::GetFullPath($Path)
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Linked paths are not allowed: $cursor"
            }
        }
        $parent = [IO.Directory]::GetParent($cursor)
        $cursor = if ($parent) { $parent.FullName } else { $null }
    }
}

$scope = (Get-Item -LiteralPath $Root -Force).FullName.TrimEnd('\')
if ((Split-Path $scope -Leaf) -notmatch '^\d{4}$') { throw 'Root must be an explicitly named year folder' }
Assert-Unlinked $scope
$scopeYear = Split-Path $scope -Leaf

function Assert-InScope([string]$Path) {
    $absolute = [IO.Path]::GetFullPath($Path)
    if (-not $absolute.StartsWith($scope+'\',[StringComparison]::OrdinalIgnoreCase)) {
        throw "Outside named year directory: $absolute"
    }
    Assert-Unlinked $absolute
}

function Get-Period([string]$Name) {
    try {
        if ($Name -match '^(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})_weekly\.md$') {
            $start = [datetime]::ParseExact($Matches[1], 'yyyy-MM-dd', [cultureinfo]::InvariantCulture)
            $day = [datetime]::ParseExact($Matches[2], 'yyyy-MM-dd', [cultureinfo]::InvariantCulture)
            if (($day-$start).Days -lt 0 -or ($day-$start).Days -gt 6) { return $null }
        } elseif ($Name -match '^(\d{4}-\d{2})_monthly\.md$') {
            $day = [datetime]::ParseExact($Matches[1]+'-01', 'yyyy-MM-dd', [cultureinfo]::InvariantCulture)
        } elseif ($Name -match '^(\d{4}-\d{2}-\d{2})\.md$') {
            $day = [datetime]::ParseExact($Matches[1], 'yyyy-MM-dd', [cultureinfo]::InvariantCulture)
        } else { return $null }
        if ($day.ToString('yyyy') -ne $scopeYear) { return $null }
        return $day.ToString('yyyy-MM')
    } catch { return $null }
}

function Get-Inventory {
    $files = @(Get-ChildItem -LiteralPath $scope -File -Force)
    foreach ($directory in Get-ChildItem -LiteralPath $scope -Directory -Force) {
        Assert-Unlinked $directory.FullName
        if ($directory.Name -match ('^'+$scopeYear+'-\d{2}$')) {
            $files += @(Get-ChildItem -LiteralPath $directory.FullName -File -Force)
        }
    }
    $rows = @()
    foreach ($file in $files) {
        $period = Get-Period $file.Name
        if (-not $period) { continue }
        Assert-InScope $file.FullName
        $destination = Join-Path (Join-Path $scope $period) $file.Name
        Assert-InScope $destination
        $rows += [pscustomobject]@{
            Source=$file.FullName; Relative=$file.FullName.Substring($scope.Length+1)
            Name=$file.Name; Destination=$destination; Length=$file.Length
            ModifiedTicks=$file.LastWriteTimeUtc.Ticks
            Hash=(Get-ReportHash $file.FullName)
        }
    }
    return @($rows | Sort-Object Source)
}

function Save-Json($Value,[string]$Path) {
    $parent = Split-Path -Parent ([IO.Path]::GetFullPath($Path))
    [IO.Directory]::CreateDirectory($parent) | Out-Null
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 10), [Text.UTF8Encoding]::new($false))
}

function Get-Groups($Items) {
    $groups = @()
    foreach ($group in ($Items | Group-Object Name)) {
        # Newest modification wins; on ties prefer the already canonical path.
        $ranked = @($group.Group | Sort-Object @{Expression='ModifiedTicks';Descending=$true},
            @{Expression={ $_.Source -eq $_.Destination };Descending=$true}, Source)
        $groups += [pscustomobject]@{ Keeper=$ranked[0]; Losers=@($ranked | Select-Object -Skip 1) }
    }
    return $groups
}

$inventory = @(Get-Inventory)
$groups = @(Get-Groups $inventory)
if (-not $Execute) {
    $plan = [pscustomobject]@{
        Version=1; Root=$scope; Files=$inventory; Groups=$groups
        Summary=[pscustomobject]@{
            Files=$inventory.Count; Reports=$groups.Count
            Duplicates=@($groups | ForEach-Object { $_.Losers }).Count
            Moves=@($groups | Where-Object { $_.Keeper.Source -ne $_.Keeper.Destination }).Count
        }
    }
    Save-Json $plan ([IO.Path]::GetFullPath($PlanPath))
    $plan.Summary | ConvertTo-Json -Compress
    exit 0
}

$plan = Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($plan.Version -ne 1 -or $plan.Root -ne $scope) { throw 'Plan/root mismatch' }
if (($inventory | ConvertTo-Json -Depth 8 -Compress) -ne ($plan.Files | ConvertTo-Json -Depth 8 -Compress)) {
    throw 'Files changed since preview; create a new plan before execution'
}
if (($groups | ConvertTo-Json -Depth 10 -Compress) -ne ($plan.Groups | ConvertTo-Json -Depth 10 -Compress)) {
    throw 'Plan decisions changed; create a fresh preview'
}
if (-not $BackupRoot) { throw 'BackupRoot is mandatory for execution' }
$backup = [IO.Path]::GetFullPath($BackupRoot)
if ($backup.StartsWith($scope+'\',[StringComparison]::OrdinalIgnoreCase) -or $backup -eq $scope) {
    throw 'Backup must be outside the year directory'
}
Assert-Unlinked $backup
if (Test-Path -LiteralPath $backup) { throw 'Backup directory already exists' }
[IO.Directory]::CreateDirectory($backup) | Out-Null
Save-Json $plan (Join-Path $backup 'plan.json')
# Back up and verify ALL source versions before the first move or recycle.
foreach ($file in $plan.Files) {
    Assert-InScope $file.Source
    $copy = Join-Path (Join-Path $backup 'files') $file.Relative
    [IO.Directory]::CreateDirectory((Split-Path -Parent $copy)) | Out-Null
    Copy-Item -LiteralPath $file.Source -Destination $copy -ErrorAction Stop
    if ((Get-ReportHash $copy) -ne $file.Hash) { throw 'Backup verification failed' }
}
Add-Type -AssemblyName Microsoft.VisualBasic
$result = [pscustomobject]@{ Status='in_progress'; Moved=@(); Recycled=@(); Root=$scope; Error=$null }
$resultPath = Join-Path $backup 'result.json'
Save-Json $result $resultPath
try {
    foreach ($group in $plan.Groups) {
        foreach ($loser in $group.Losers) {
            Assert-InScope $loser.Source
            if ((Get-ReportHash $loser.Source) -ne $loser.Hash) { throw 'Duplicate changed during execution' }
            [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile($loser.Source,
                [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,
                [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin)
            $result.Recycled += $loser.Source
            Save-Json $result $resultPath
        }
        $keeper = $group.Keeper
        Assert-InScope $keeper.Source
        Assert-InScope $keeper.Destination
        if ((Get-ReportHash $keeper.Source) -ne $keeper.Hash) { throw 'Keeper changed during execution' }
        if ($keeper.Source -ne $keeper.Destination) {
            if (Test-Path -LiteralPath $keeper.Destination) { throw 'Destination occupied; no overwrite permitted' }
            [IO.Directory]::CreateDirectory((Split-Path -Parent $keeper.Destination)) | Out-Null
            Move-Item -LiteralPath $keeper.Source -Destination $keeper.Destination -ErrorAction Stop
            $result.Moved += [pscustomobject]@{ Source=$keeper.Source; Destination=$keeper.Destination }
            Save-Json $result $resultPath
        }
        if ((Get-ReportHash $keeper.Destination) -ne $keeper.Hash) { throw 'Destination verification failed' }
    }
    $final = @(Get-Inventory)
    if ($final.Count -ne @($plan.Groups).Count) { throw 'Final inventory count mismatch' }
    if (@($final | Where-Object { $_.Source -ne $_.Destination }).Count -ne 0) { throw 'Unorganized reports remain' }
    $result.Status='completed'
} catch {
    $result.Status='failed'; $result.Error=$_.Exception.Message
    throw
} finally {
    Save-Json $result $resultPath
}
[pscustomobject]@{Status=$result.Status; Moved=$result.Moved.Count; Recycled=$result.Recycled.Count; Backup=$backup} | ConvertTo-Json -Compress
