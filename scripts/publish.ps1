param([string]$Configuration='Release',[string]$Version='1.0.0')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$publish=Join-Path $root 'publish\win-x64'
$stage=Join-Path $root 'artifacts\stage'
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
New-Item -ItemType Directory -Force (Join-Path $stage 'tools\ffmpeg'),(Join-Path $stage 'tools\mediamtx') | Out-Null
Copy-Item (Join-Path $ffmpegSource '*') (Join-Path $stage 'tools\ffmpeg') -Recurse -Force
Copy-Item (Join-Path $mediaMtxSource '*') (Join-Path $stage 'tools\mediamtx') -Recurse -Force
Copy-Item $runtimeInstaller,(Join-Path $root 'LICENSE') $stage -Force
$portableLauncher=Join-Path $stage 'Start-CamStream.cmd'
Set-Content $portableLauncher '@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-CamStream.ps1"' -Encoding ascii
Copy-Item (Join-Path $PSScriptRoot 'Start-CamStream.ps1') $stage -Force
$uninstall=Join-Path $stage 'Uninstall-CamStream.cmd'
Set-Content $uninstall '@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" -Uninstall' -Encoding ascii
Copy-Item (Join-Path $PSScriptRoot 'setup.ps1') $stage -Force
$artifacts=Join-Path $root 'artifacts'
New-Item -ItemType Directory -Force $artifacts | Out-Null
$zip=Join-Path $artifacts "CamStream-Portable-$Version.zip"
if(Test-Path $zip){Remove-Item $zip -Force}
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zip -CompressionLevel Optimal
$source=Join-Path $artifacts 'installer-source'
if(Test-Path $source){Remove-Item $source -Recurse -Force}
New-Item -ItemType Directory -Force $source | Out-Null
Copy-Item (Join-Path $stage '*') $source -Recurse -Force
$setup=Join-Path $source 'setup.cmd'
Set-Content $setup '@echo off`r`nset "PAYLOAD=%~dp0CamStreamPayload.zip"`r`nset "TEMP_DIR=%TEMP%\CamStreamSetup-%RANDOM%"`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath ''%PAYLOAD%'' -DestinationPath ''%TEMP_DIR%'' -Force; & ''%TEMP_DIR%\setup.ps1''"' -Encoding ascii
$sed=Join-Path $artifacts 'CamStream-Setup.sed'
$lines=@('[Version]','Class=IEXPRESS','SEDVersion=3','[Options]','PackagePurpose=InstallApp','ShowInstallProgramWindow=0','HideExtractAnimation=1','UseLongFileName=1','InsideCompressed=1','CAB_FixedSize=0','CAB_ResvCodeSigning=0','RebootMode=N','InstallPrompt=','DisplayLicense=','FinishMessage=','TargetName=CamStream-Setup-'+$Version+'.exe','FriendlyName=CamStream Setup','AppLaunched=setup.cmd','PostInstallCmd=<None>','SourceFiles=SourceFiles','[SourceFiles]','SourceFiles0='+$source,'[SourceFiles0]','%FILE0%=setup.cmd'); Set-Content $sed $lines -Encoding ascii
# IExpress only needs setup.cmd; setup.cmd expands the adjacent payload ZIP.
$payload=Join-Path $source 'CamStreamPayload.zip'
if(Test-Path $payload){Remove-Item $payload -Force}
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $payload -CompressionLevel Optimal
$lines=@('[Version]','Class=IEXPRESS','SEDVersion=3','[Options]','PackagePurpose=InstallApp','ShowInstallProgramWindow=0','HideExtractAnimation=1','UseLongFileName=1','InsideCompressed=1','CAB_FixedSize=0','CAB_ResvCodeSigning=0','RebootMode=N','InstallPrompt=','DisplayLicense=','FinishMessage=','TargetName=CamStream-Setup-'+$Version+'.exe','FriendlyName=CamStream Setup','AppLaunched=setup.cmd','PostInstallCmd=<None>','SourceFiles=SourceFiles','[SourceFiles]','SourceFiles0='+$source,'[SourceFiles0]','%FILE0%=setup.cmd','%FILE1%=CamStreamPayload.zip'); Set-Content $sed $lines -Encoding ascii
& "$env:WINDIR\System32\iexpress.exe" /N $sed
if($LASTEXITCODE -ne 0){throw 'IExpress package build failed.'}
Write-Host "Portable package: $zip"
Write-Host "Installer: $(Join-Path $artifacts "CamStream-Setup-$Version.exe")"
