param([switch]$Uninstall)
$ErrorActionPreference='Stop'
$installDir=Join-Path $env:LOCALAPPDATA 'Programs\CamStream'
$desktop=[Environment]::GetFolderPath('Desktop')
$startMenu=Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\CamStream'
if($Uninstall){
  Get-Process -Name 'CamStream.WinUI' -ErrorAction SilentlyContinue | Stop-Process -Force
  Remove-Item $startMenu -Recurse -Force -ErrorAction SilentlyContinue
  Remove-Item (Join-Path $desktop 'CamStream.lnk') -Force -ErrorAction SilentlyContinue
  Remove-Item $installDir -Recurse -Force -ErrorAction SilentlyContinue
  Write-Host 'CamStream was removed. User media cache was preserved.'
  exit 0
}
$source=Split-Path -Parent $MyInvocation.MyCommand.Path
if($source -ne $installDir){
  New-Item -ItemType Directory -Force $installDir | Out-Null
  Copy-Item (Join-Path $source '*') $installDir -Recurse -Force
}
$runtimeKey='HKLM:\SOFTWARE\Microsoft\WindowsAppRuntime\InstalledVersions\1.6\x64'
$userRuntimeKey='HKCU:\SOFTWARE\Microsoft\WindowsAppRuntime\InstalledVersions\1.6\x64'
if(-not(Test-Path $runtimeKey) -and -not(Test-Path $userRuntimeKey)){
  $runtimeInstaller=Join-Path $installDir 'WindowsAppRuntimeInstall-x64.exe'
  if(-not(Test-Path $runtimeInstaller)){throw 'Windows App Runtime installer is missing.'}
  $p=Start-Process -FilePath $runtimeInstaller -ArgumentList '/quiet','/norestart' -Wait -PassThru
  if($p.ExitCode -notin @(0,3010)){throw "Windows App Runtime installation failed: $($p.ExitCode)"}
}
New-Item -ItemType Directory -Force $startMenu | Out-Null
$ws=New-Object -ComObject WScript.Shell
$link=$ws.CreateShortcut((Join-Path $startMenu 'CamStream.lnk'))
$link.TargetPath=Join-Path $installDir 'CamStream.WinUI.exe'
$link.WorkingDirectory=$installDir
$link.Save()
$desktopLink=$ws.CreateShortcut((Join-Path $desktop 'CamStream.lnk'))
$desktopLink.TargetPath=Join-Path $installDir 'CamStream.WinUI.exe'
$desktopLink.WorkingDirectory=$installDir
$desktopLink.Save()
Start-Process -FilePath $link.TargetPath -WorkingDirectory $installDir
