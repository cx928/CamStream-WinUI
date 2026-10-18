param([string]$Configuration='Release',[string]$Version='1.0.0')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$publish=Join-Path $root 'publish\win-x64'
$stage=Join-Path $root 'artifacts\stage'
$artifacts=Join-Path $root 'artifacts'
$installer=Join-Path $root 'installer'
$tools=Join-Path $root 'tools'
$ffmpegSource=Join-Path $tools 'ffmpeg'
$mediaMtxSource=Join-Path $tools 'mediamtx'
$runtimeInstaller=Join-Path $tools 'WindowsAppRuntimeInstall-x64.exe'
$msbuild=Join-Path ${env:ProgramFiles} 'Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe'
if(-not(Test-Path $msbuild)){throw 'Visual Studio 2022 MSBuild not found.'}

& dotnet restore (Join-Path $root 'CamStream.WinUI.csproj') --runtime win-x64
if($LASTEXITCODE -ne 0){throw 'win-x64 restore failed.'}
foreach($p in @((Join-Path $ffmpegSource 'ffmpeg.exe'),(Join-Path $mediaMtxSource 'mediamtx.exe'),$runtimeInstaller)){if(-not(Test-Path $p)){throw "Required release file missing: $p"}}

& $msbuild (Join-Path $root 'CamStream.WinUI.csproj') /t:Publish "/p:Configuration=$Configuration" /p:Platform=x64 /p:RuntimeIdentifier=win-x64 /p:WindowsAppSDKSelfContained=true /p:SelfContained=true "/p:PublishDir=$publish\" /p:PublishTrimmed=false /v:minimal
if($LASTEXITCODE -ne 0){throw 'WinUI publish failed.'}

if(Test-Path $stage){Remove-Item $stage -Recurse -Force}
New-Item -ItemType Directory -Force $stage | Out-Null
Copy-Item (Join-Path $publish '*') $stage -Recurse -Force
Remove-Item (Join-Path $stage '*.pdb') -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force (Join-Path $stage 'tools\ffmpeg'),(Join-Path $stage 'tools\mediamtx') | Out-Null
Copy-Item (Join-Path $ffmpegSource 'ffmpeg.exe') (Join-Path $stage 'tools\ffmpeg') -Force
Copy-Item (Join-Path $ffmpegSource '*.dll') (Join-Path $stage 'tools\ffmpeg') -Force -ErrorAction SilentlyContinue
Copy-Item (Join-Path $mediaMtxSource '*') (Join-Path $stage 'tools\mediamtx') -Recurse -Force
Copy-Item $runtimeInstaller,(Join-Path $root 'LICENSE') $stage -Force
Copy-Item (Join-Path $PSScriptRoot 'Start-CamStream.ps1'),(Join-Path $PSScriptRoot 'setup.ps1') $stage -Force
Set-Content (Join-Path $stage 'Start-CamStream.cmd') '@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-CamStream.ps1"' -Encoding ascii
Set-Content (Join-Path $stage 'setup.cmd') '@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"' -Encoding ascii
Set-Content (Join-Path $stage 'Uninstall-CamStream.cmd') '@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" -Uninstall' -Encoding ascii

$zip=Join-Path $artifacts "CamStream-Portable-$Version.zip"
if(Test-Path $zip){Remove-Item $zip -Force}
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zip -CompressionLevel Optimal

node (Join-Path $installer 'gen-msi.mjs') $root $stage $Version (Join-Path $installer 'CamStream.wxs')
if($LASTEXITCODE -ne 0){throw 'WiX source generation failed.'}
$msi=Join-Path $artifacts "CamStream-$Version-x64.msi"
wix build -arch x64 -o $msi (Join-Path $installer 'CamStream.wxs')
if($LASTEXITCODE -ne 0){throw 'MSI build failed.'}

$bundleWxs=Join-Path $installer 'CamStream.Bundle.wxs'
$template=Get-Content $bundleWxs -Raw
$template=$template -replace 'Version="1\.0\.0"', "Version=`"$Version`""
$bundleTemp=Join-Path $installer 'CamStream.Bundle.generated.wxs'
$template=$template.Replace('__RUNTIME_INSTALLER__', (Join-Path $stage 'WindowsAppRuntimeInstall-x64.exe'))
$template=$template.Replace('__APP_MSI__', $msi)
Set-Content $bundleTemp $template -Encoding utf8
$bal="$env:USERPROFILE\.wix\extensions\WixToolset.Bal.wixext\7.0.0\wixext7\WixToolset.BootstrapperApplications.wixext.dll"
$util="$env:USERPROFILE\.wix\extensions\WixToolset.Util.wixext\7.0.0\wixext7\WixToolset.Util.wixext.dll"
wix build -arch x64 -ext $bal -ext $util -o (Join-Path $artifacts "CamStream-Setup-$Version-x64.exe") $bundleTemp
if($LASTEXITCODE -ne 0){throw 'Installer EXE build failed.'}

Write-Host "Portable: $zip"
Write-Host "MSI: $msi"
Write-Host "Setup EXE: $(Join-Path $artifacts "CamStream-Setup-$Version-x64.exe")"
