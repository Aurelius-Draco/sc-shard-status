# Builds the Microsoft Store package (MSIX) from the app folder PyInstaller made, then installs a test-signed copy,
# starts it the way Windows does (so it runs with its package identity), checks the dashboard comes up and that the
# app knows it's the Store version, and removes it again.
#
#   installer\msix\build.ps1 -Ver 1.5.1
#
# Leaves dist\VerseShards-<ver>.msix, unsigned: that's the file uploaded to Partner Center, and the Store signs it.
param(
  [Parameter(Mandatory = $true)][string]$Ver,
  [string]$AppDir = "dist\SC Shard Status",
  [switch]$NoTest
)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$kits = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\makeappx.exe" | Sort-Object FullName | Select-Object -Last 1
if (-not $kits) { throw "makeappx.exe not found (Windows SDK)" }
$bin = $kits.DirectoryName
Write-Host "Windows SDK tools: $bin"

if ($Ver -notmatch '^\d+\.\d+\.\d+$') { throw "Version $Ver isn't x.y.z" }
$layout = Join-Path ($env:RUNNER_TEMP ?? $env:TEMP) "msix-layout"
if (Test-Path $layout) { Remove-Item -Recurse -Force $layout }
New-Item -ItemType Directory $layout | Out-Null
Copy-Item -Recurse "$AppDir\*" $layout
Copy-Item -Recurse "$here\Assets" "$layout\Assets"
(Get-Content -Raw "$here\AppxManifest.xml").Replace("{VERSION}", $Ver) | Set-Content -Encoding utf8 "$layout\AppxManifest.xml"

$msix = "dist\VerseShards-$Ver.msix"
& "$bin\makeappx.exe" pack /d $layout /p $msix /o /h SHA256
if ($LASTEXITCODE -ne 0) { throw "makeappx failed" }
Get-Item $msix | Select-Object Name, Length
if ($NoTest) { return }

# ---- test install: sign a copy with a throwaway certificate whose subject is the Store publisher ----
$publisher = ([xml](Get-Content "$layout\AppxManifest.xml")).Package.Identity.Publisher
$cert = New-SelfSignedCertificate -Type Custom -Subject $publisher -KeyUsage DigitalSignature -FriendlyName "Verse Shards test" `
  -CertStoreLocation "Cert:\CurrentUser\My" -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3", "2.5.29.19={text}")
$pwd = ConvertTo-SecureString -String "test" -Force -AsPlainText
$pfx = Join-Path ($env:RUNNER_TEMP ?? $env:TEMP) "msix-test.pfx"
Export-PfxCertificate -Cert $cert -FilePath $pfx -Password $pwd | Out-Null
$cer = Join-Path ($env:RUNNER_TEMP ?? $env:TEMP) "msix-test.cer"
Export-Certificate -Cert $cert -FilePath $cer | Out-Null
Import-Certificate -FilePath $cer -CertStoreLocation "Cert:\LocalMachine\TrustedPeople" | Out-Null
$test = "dist\VerseShards-$Ver-test.msix"
Copy-Item $msix $test
& "$bin\signtool.exe" sign /fd SHA256 /f $pfx /p test $test
if ($LASTEXITCODE -ne 0) { throw "signtool failed" }

Add-AppxPackage -Path $test
$pkg = Get-AppxPackage -Name "VerseShards.VerseShardsforPC"
if (-not $pkg) { throw "the package didn't install" }
Write-Host "Installed $($pkg.PackageFullName)"
try {
  Start-Process "shell:AppsFolder\$($pkg.PackageFamilyName)!VerseShards"
  $ok = $false
  foreach ($i in 1..60) {
    Start-Sleep 2
    try { $r = Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8775/ -TimeoutSec 5; if ($r.Content -match 'const TOKEN = "') { $ok = $true; break } } catch {}
  }
  $log = Join-Path $env:LOCALAPPDATA "SC Shard Status\status.log"
  if (-not $ok) { Get-Content $log -ErrorAction SilentlyContinue | Select-Object -Last 30; throw "the Store version's dashboard didn't come up" }
  Write-Host "Dashboard came up."
  # It must know it's the Store version (so it never runs its own updater), and write to the real data folder
  $line = Select-String -Path $log -Pattern "\(Microsoft Store\)" | Select-Object -Last 1
  if (-not $line) { Get-Content $log | Select-Object -Last 30; throw "the app didn't see it runs as the Store version" }
  Write-Host $line.Line
}
finally {
  Get-Process "SC Shard Status" -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep 2
  Remove-AppxPackage -Package $pkg.PackageFullName
  Remove-Item $test -ErrorAction SilentlyContinue
}
Write-Host "Store package installed, ran as the Store version and was removed cleanly."
