# Makes the SC Shard Status shortcuts, with their icon.
# Setup.bat runs this. Run Setup.bat again if you move the folder.
#   -Extra   also add a Start menu folder and a desktop shortcut
param([switch]$Extra)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$icon = Join-Path $root 'scstatus\assets\status.ico'
$shell = New-Object -ComObject WScript.Shell
$items = @(
  @{ Name = 'SC Shard Status';                Bat = 'status.bat';            Desc = 'Shard health and what''s gone wrong, while you play' },
  @{ Name = 'SC Shard Status - check';        Bat = 'check.bat';             Desc = 'What''s gone wrong in the last 30 minutes' },
  @{ Name = 'SC Shard Status (log only)';     Bat = 'status-no-overlay.bat'; Desc = 'Without reading the game overlay off the screen' }
)

function New-Shortcut($dir, $it) {
  $lnk = $shell.CreateShortcut((Join-Path $dir ($it.Name + '.lnk')))
  # Point straight at the .bat: works with spaces and brackets in the folder name ("SC-Shard-Status (1)")
  $lnk.TargetPath = (Join-Path $root ('launchers\' + $it.Bat))
  $lnk.WorkingDirectory = $root
  $lnk.IconLocation = $icon + ',0'
  $lnk.Description = $it.Desc
  $lnk.Save()
}

foreach ($it in $items) { New-Shortcut $root $it }
Write-Host 'Shortcuts made in the SC Shard Status folder.'

if ($Extra) {
  $menu = Join-Path ([Environment]::GetFolderPath('Programs')) 'SC Shard Status'
  New-Item -ItemType Directory -Force -Path $menu | Out-Null
  foreach ($it in $items) { New-Shortcut $menu $it }
  New-Shortcut ([Environment]::GetFolderPath('Desktop')) $items[0]
  Write-Host 'Added a Start menu folder and a desktop shortcut.'
}
