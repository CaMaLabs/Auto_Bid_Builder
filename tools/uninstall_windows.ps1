param(
    [string]$InstallRoot = "$env:LOCALAPPDATA\JTI\AutoBidBuilder",
    [switch]$KeepSettings
)

$ErrorActionPreference = 'Stop'

Write-Host "Auto Bid Builder - Uninstall" -ForegroundColor Yellow
Write-Host "This removes the app installation and shortcuts. It does not remove bid/project folders you created elsewhere."

$answer = Read-Host 'Type YES to continue'
if ($answer -ne 'YES') {
    Write-Host 'Cancelled.'
    exit 0
}

$shellDesktop = [Environment]::GetFolderPath('Desktop')
$shortcuts = @(
    (Join-Path $shellDesktop 'Auto Bid Builder.lnk'),
    (Join-Path (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs') 'Auto Bid Builder.lnk')
)
foreach ($shortcut in $shortcuts) {
    Remove-Item -Force -ErrorAction SilentlyContinue $shortcut
}

if (Test-Path $InstallRoot) {
    Remove-Item -Recurse -Force $InstallRoot
}

if (-not $KeepSettings) {
    $settingsRoot = Join-Path $HOME '.auto_bid_builder'
    if (Test-Path $settingsRoot) {
        Remove-Item -Recurse -Force $settingsRoot
    }
}

Write-Host 'Auto Bid Builder has been removed.' -ForegroundColor Green
Write-Host 'Python, Git, and any JTI bid/project folders were left in place.'
