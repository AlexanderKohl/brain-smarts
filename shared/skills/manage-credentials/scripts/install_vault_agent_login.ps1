# Install auto-start for the Vault tray agent (no console window).
# Prefer a current-user Startup-folder shortcut (no admin). Optionally also
# register a Scheduled Task AtLogOn when permitted.
#
#   cd <brain root>   (the folder holding CONTRACT.md)
#   powershell -NoProfile -File shared/skills/manage-credentials/scripts/install_vault_agent_login.ps1
#
#   -Uninstall   Remove Startup shortcut and logon task

param(
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")).Path
$taskName = "PortableAIBrainVaultAgent"
$startup = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startup "PortableAIBrainVaultAgent.lnk"

$pythonCmd = Get-Command python -ErrorAction Stop
$pythonDir = Split-Path -Parent $pythonCmd.Source
$pythonw = Join-Path $pythonDir "pythonw.exe"
if (-not (Test-Path $pythonw)) {
    $pythonw = $pythonCmd.Source
}
$tray = Join-Path $repoRoot "shared\skills\manage-credentials\scripts\vault_tray.py"

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    if (Test-Path $shortcutPath) {
        Remove-Item $shortcutPath -Force
    }
    Write-Host "Removed Startup shortcut and logon task (if they existed)."
    exit 0
}

if (-not (Test-Path $tray)) {
    throw "Tray script not found: $tray"
}

$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = "`"$tray`""
$shortcut.WorkingDirectory = $repoRoot
$shortcut.WindowStyle = 7
$shortcut.Description = "Portable AI Brain Vault tray agent"
$shortcut.Save()
Write-Host "Created Startup shortcut: $shortcutPath"

try {
    $action = New-ScheduledTaskAction `
        -Execute $pythonw `
        -Argument "`"$tray`"" `
        -WorkingDirectory $repoRoot
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit ([TimeSpan]::Zero)
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    Write-Host "Also registered logon task '$taskName'."
} catch {
    Write-Host "Scheduled Task not registered (permission denied is OK)."
    Write-Host "Startup-folder shortcut alone will start the tray after login."
}

Write-Host ""
Write-Host "After reboot/login: tray starts, asks to unlock, grey=locked / red=unlocked."
Write-Host "Start now without reboot:"
Write-Host "  cd $repoRoot"
Write-Host "  pythonw shared\skills\manage-credentials\scripts\vault_tray.py"
