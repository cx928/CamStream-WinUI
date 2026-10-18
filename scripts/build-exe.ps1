param([string]$Version='1.0.0')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$artifacts=Join-Path $root 'artifacts'
$bootstrap=Join-Path $PSScriptRoot 'Bootstrapper'
$payload=Join-Path $artifacts 'bootstrap-payload'
$publish=Join-Path $bootstrap 'publish'
if(Test-Path $payload){Remove-Item $payload -Recurse -Force}
New-Item -ItemType Directory -Force $payload | Out-Null
& dotnet publish (Join-Path $bootstrap 'Bootstrapper.csproj') -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:PublishTrimmed=false -o $publish --nologo
if($LASTEXITCODE -ne 0){throw 'Bootstrapper build failed.'}
Copy-Item (Join-Path $publish 'Bootstrapper.exe') (Join-Path $payload 'Bootstrapper.exe') -Force
Copy-Item (Join-Path $artifacts "CamStream-$Version-x64.msi") $payload -Force
Copy-Item (Join-Path $root 'tools\WindowsAppRuntimeInstall-x64.exe') $payload -Force
$sed=Join-Path $artifacts 'CamStream-Setup.sed'
$lines=@('[Version]','Class=IEXPRESS','SEDVersion=3','[Options]','PackagePurpose=InstallApp','ShowInstallProgramWindow=1','HideExtractAnimation=1','UseLongFileName=1','InsideCompressed=1','CAB_FixedSize=0','CAB_ResvCodeSigning=0','RebootMode=N','InstallPrompt=','DisplayLicense=','FinishMessage=','TargetName=CamStream-Setup-'+$Version+'.exe','FriendlyName=CamStream Setup','AppLaunched=Bootstrapper.exe','PostInstallCmd=<None>','SourceFiles=SourceFiles','[SourceFiles]','SourceFiles0='+$payload,'[SourceFiles0]','%FILE0%=Bootstrapper.exe','%FILE1%=CamStream-'+$Version+'-x64.msi','%FILE2%=WindowsAppRuntimeInstall-x64.exe','[Strings]','FILE0="Bootstrapper.exe"','FILE1="CamStream-'+$Version+'-x64.msi"','FILE2="WindowsAppRuntimeInstall-x64.exe"')
Set-Content $sed $lines -Encoding ascii
Push-Location $artifacts
try { & "$env:WINDIR\System32\iexpress.exe" /N (Split-Path $sed -Leaf) }
finally { Pop-Location }
$final=Join-Path $artifacts "CamStream-Setup-$Version.exe"
if(-not(Test-Path $final)){throw 'IExpress did not produce the setup EXE.'}
Get-Item $final | Select-Object FullName,Length
