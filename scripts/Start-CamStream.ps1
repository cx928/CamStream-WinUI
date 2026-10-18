param([switch]$Install)
$ErrorActionPreference='Stop'
$base=Split-Path -Parent $MyInvocation.MyCommand.Path
$runtimeKey='HKLM:\SOFTWARE\Microsoft\WindowsAppRuntime\InstalledVersions\1.6\x64'
$userRuntimeKey='HKCU:\SOFTWARE\Microsoft\WindowsAppRuntime\InstalledVersions\1.6\x64'
if(-not(Test-Path $runtimeKey) -and -not(Test-Path $userRuntimeKey)){
  $installer=Join-Path $base 'WindowsAppRuntimeInstall-x64.exe'
  if(-not(Test-Path $installer)){throw 'Windows App Runtime installer not found.'}
  $p=Start-Process -FilePath $installer -ArgumentList '/quiet','/norestart' -Wait -PassThru
  if($p.ExitCode -notin @(0,3010)){throw "Runtime installation failed: $($p.ExitCode)"}
}
$exe=Join-Path $base 'CamStream.WinUI.exe'
if(-not(Test-Path $exe)){throw 'CamStream.WinUI.exe not found.'}
Start-Process -FilePath $exe -WorkingDirectory $base
