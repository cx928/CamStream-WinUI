param([string]$Version='1.0.0')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$stage=Join-Path $root 'artifacts\stage'
$artifacts=Join-Path $root 'artifacts'
$wix=Join-Path $env:USERPROFILE '.dotnet\tools\wix.exe'
if(-not(Test-Path $wix)){throw 'WiX CLI not found.'}
if(-not(Test-Path (Join-Path $stage 'CamStream.WinUI.exe'))){throw 'Build publish stage first.'}
New-Item -ItemType Directory -Force $artifacts | Out-Null
$msi=Join-Path $artifacts "CamStream-$Version-x64.msi"
& $wix build --acceptEula true -arch x64 -d StageDir=$stage (Join-Path $PSScriptRoot 'CamStream.wxs') -o $msi
if($LASTEXITCODE -ne 0){throw 'MSI build failed.'}
Get-Item $msi | Select-Object FullName,Length
