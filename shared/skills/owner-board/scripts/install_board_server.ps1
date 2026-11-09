# Install the board server as a scheduled task that starts at log-on (personal CRM design 04,
# increment 5): serve_boards.py on 127.0.0.1 only, port 8765, from this checkout, with no console
# window. One mechanism: no Startup-folder shortcut. The task runs as the current user, not elevated.
#
#   cd <brain root>   (the shared checkout, the folder holding CONTRACT.md)
#   powershell -NoProfile -File shared/skills/owner-board/scripts/install_board_server.ps1
#
#   -Uninstall   Remove the log-on task (the server keeps running until it is stopped or you log off)
#
# This script does not start the server. To start it now without logging off:
#   Start-ScheduledTask -TaskName BrainBoardServer
# and check:  http://localhost:8765/_board-server.json  answers with a token.
#
# Run it from the shared checkout, never from a session copy (a linked worktree): the server saves
# decisions into /memory/inbox/ of the checkout it runs from, and a session copy is deleted.

param(
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$taskName = "BrainBoardServer"
$bindAddress = "127.0.0.1"
$port = 8765

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed the log-on task '$taskName' (if it existed)."
    exit 0
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")).Path
if (-not (Test-Path (Join-Path $repoRoot "CONTRACT.md"))) {
    throw "CONTRACT.md not found in $repoRoot - run this script from the brain's shared checkout."
}
if (-not (Test-Path -PathType Container (Join-Path $repoRoot ".git"))) {
    throw "$repoRoot is not the shared checkout (its .git is not a folder): a session copy must not run the server."
}
$server = Join-Path $repoRoot "shared\skills\owner-board\scripts\serve_boards.py"
if (-not (Test-Path $server)) {
    throw "Board server not found: $server"
}

$pythonCmd = Get-Command python -ErrorAction Stop
$pythonw = Join-Path (Split-Path -Parent $pythonCmd.Source) "pythonw.exe"
if (-not (Test-Path $pythonw)) {
    $pythonw = $pythonCmd.Source
}

$arguments = "`"$server`" --port $port --bind $bindAddress --root `"$repoRoot`""
$action = New-ScheduledTaskAction -Execute $pythonw -Argument $arguments -WorkingDirectory $repoRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null

Write-Host "Registered the log-on task '$taskName':"
Write-Host "  $pythonw $arguments"
Write-Host "It binds $bindAddress only, port $port. After the next log-on:"
Write-Host "  http://localhost:$port/_board-server.json  answers with a token."
Write-Host "Start it now without logging off:  Start-ScheduledTask -TaskName $taskName"
Write-Host "Remove it:  powershell -NoProfile -File shared/skills/owner-board/scripts/install_board_server.ps1 -Uninstall"
