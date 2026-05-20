# Kill processes holding port 8000 (Windows-only, supports PowerShell 5.1+)
#
# Purpose:
#   On Windows, uvicorn reloader spawns workers via multiprocessing.spawn.
#   When Ctrl+C is forwarded by concurrently/pnpm, the reloader exits but
#   worker children may survive and keep listening on 8000, causing the
#   new backend to share the port with stale routes. This script kills
#   the whole tree before pnpm dev starts.
#
# Usage:
#   pwsh scripts/kill-port-8000.ps1             default: kill python tree on 8000
#   pwsh scripts/kill-port-8000.ps1 -DryRun     list targets only
#   pwsh scripts/kill-port-8000.ps1 -Quiet      only print when killing
#
# NOTE: This file is intentionally ASCII-only (no Chinese, no emoji) so that
# both Windows PowerShell 5.1 (default OEM/GBK console) and PowerShell 7 (UTF-8)
# can parse it without character-encoding parser errors.

[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$Quiet
)

$ErrorActionPreference = 'SilentlyContinue'

function Write-Info($msg) {
    if (-not $Quiet) { Write-Host $msg }
}

# 1. Find PIDs listening on 8000
$listenLines = netstat -ano | Select-String ":8000\s.*LISTENING"
if (-not $listenLines) {
    Write-Info "[kill-port-8000] port 8000 is free, nothing to do"
    exit 0
}

$pidsOnPort = @()
foreach ($line in $listenLines) {
    $tokens = ($line.Line -split '\s+') | Where-Object { $_ }
    $pidsOnPort += [int]$tokens[-1]
}
$pidsOnPort = $pidsOnPort | Sort-Object -Unique

# 2. Walk the parent/child chain for python.exe (covers spawn workers)
$allPython = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'")
$pythonPids = @{}
foreach ($p in $allPython) {
    $pythonPids[[int]$p.ProcessId] = $p
}

$relevant = New-Object System.Collections.Generic.HashSet[int]
$queue = New-Object System.Collections.Queue
$nonPythonPids = @()

foreach ($p in $pidsOnPort) {
    if ($pythonPids.ContainsKey($p)) {
        [void]$relevant.Add($p)
        $queue.Enqueue($p)
    } else {
        $nonPythonPids += $p
    }
}

while ($queue.Count -gt 0) {
    $currentPid = [int]$queue.Dequeue()
    foreach ($p in $allPython) {
        $childPid = [int]$p.ProcessId
        if ([int]$p.ParentProcessId -eq $currentPid -and -not $relevant.Contains($childPid)) {
            [void]$relevant.Add($childPid)
            $queue.Enqueue($childPid)
        }
    }
    $self = $pythonPids[$currentPid]
    if ($self) {
        $parentPid = [int]$self.ParentProcessId
        if ($parentPid -gt 0 -and $pythonPids.ContainsKey($parentPid) -and -not $relevant.Contains($parentPid)) {
            [void]$relevant.Add($parentPid)
            $queue.Enqueue($parentPid)
        }
    }
}

# 3. Report
if ($relevant.Count -gt 0) {
    Write-Info "[kill-port-8000] python processes holding 8000:"
    foreach ($targetPid in $relevant) {
        $proc = $pythonPids[$targetPid]
        if ($proc) {
            if ($proc.CommandLine) {
                $cmdLine = $proc.CommandLine -replace '\s+', ' '
            } else {
                $cmdLine = '<no cmdline>'
            }
            $cmdShort = $cmdLine.Substring(0, [Math]::Min(100, $cmdLine.Length))
            Write-Info ("  PID={0}  parent={1}  cmd={2}" -f $targetPid, $proc.ParentProcessId, $cmdShort)
        }
    }
}

if ($nonPythonPids.Count -gt 0) {
    Write-Info "[kill-port-8000] non-python processes on 8000 (fallback hard kill):"
    foreach ($targetPid in $nonPythonPids) {
        $info = Get-CimInstance Win32_Process -Filter "ProcessId=$targetPid"
        if ($info) {
            $name = $info.Name
        } else {
            $name = '<unknown>'
        }
        Write-Info ("  PID={0}  name={1}" -f $targetPid, $name)
    }
}

if ($DryRun) {
    Write-Info "[kill-port-8000] DryRun: no process actually killed"
    exit 0
}

# 4. Kill (python tree first, then non-python fallback)
foreach ($targetPid in $relevant) {
    & taskkill /F /T /PID $targetPid 2>&1 | Out-Null
}
foreach ($targetPid in $nonPythonPids) {
    & taskkill /F /PID $targetPid 2>&1 | Out-Null
}

# 5. Wait for port to be released (up to 5s)
$waited = 0
while ($waited -lt 50) {
    $stillListen = netstat -ano | Select-String ":8000\s.*LISTENING"
    if (-not $stillListen) { break }
    Start-Sleep -Milliseconds 100
    $waited++
}

if ($waited -ge 50) {
    Write-Host "[kill-port-8000] WARN: port still occupied, continuing anyway" -ForegroundColor Yellow
    netstat -ano | Select-String ":8000\s.*LISTENING"
    # exit 0 on purpose: do not block pnpm dev; uvicorn will raise a clear EADDRINUSE
    exit 0
}

Write-Info ("[kill-port-8000] OK port 8000 released in {0} ms" -f ($waited * 100))
exit 0
