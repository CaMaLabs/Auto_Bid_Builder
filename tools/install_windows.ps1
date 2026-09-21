param(
    [string]$InstallRoot = "$env:LOCALAPPDATA\JTI\AutoBidBuilder",
    [switch]$NoLaunch
)

$ErrorActionPreference = 'Stop'
$RepoUrl = 'https://github.com/CaMaLabs/Auto_Bid_Builder.git'

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machine;$user"
}

function Ensure-Command([string]$Command, [string]$WingetId, [string]$FriendlyName) {
    if (Get-Command $Command -ErrorAction SilentlyContinue) { return }
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "$FriendlyName is required and Windows Package Manager (winget) is not available. Install $FriendlyName, then run this installer again."
    }
    Write-Step "Installing $FriendlyName"
    winget install --id $WingetId -e --accept-package-agreements --accept-source-agreements
    Refresh-Path
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        throw "$FriendlyName was installed but is not available in this terminal yet. Close this window, reopen PowerShell, and run the installer again."
    }
}

try {
    Write-Host "Auto Bid Builder - JTI Millwork" -ForegroundColor Green
    Write-Host "This installer will set up the app, create shortcuts, and launch it when finished."

    Ensure-Command -Command 'git' -WingetId 'Git.Git' -FriendlyName 'Git'
    Ensure-Command -Command 'python' -WingetId 'Python.Python.3.12' -FriendlyName 'Python 3.12'

    Write-Step "Installing Auto Bid Builder"
    $parent = Split-Path -Parent $InstallRoot
    New-Item -ItemType Directory -Force -Path $parent | Out-Null

    if (Test-Path (Join-Path $InstallRoot '.git')) {
        Push-Location $InstallRoot
        try {
            git fetch origin main
            git merge --ff-only origin/main
        }
        finally { Pop-Location }
    }
    else {
        if (Test-Path $InstallRoot) {
            $contents = Get-ChildItem -Force $InstallRoot -ErrorAction SilentlyContinue
            if ($contents) {
                throw "Install folder already exists and is not an Auto Bid Builder Git checkout: $InstallRoot"
            }
        }
        git clone $RepoUrl $InstallRoot
    }

    Push-Location $InstallRoot
    try {
        Write-Step "Installing required components"
        python -m pip install --upgrade pip
        python -m pip install -e .
    }
    finally { Pop-Location }

    Write-Step "Creating shortcuts"
    $pythonPath = (Get-Command python).Source
    $pythonwPath = Join-Path (Split-Path $pythonPath -Parent) 'pythonw.exe'
    if (-not (Test-Path $pythonwPath)) { $pythonwPath = $pythonPath }

    $shell = New-Object -ComObject WScript.Shell
    $desktop = [Environment]::GetFolderPath('Desktop')
    $startMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'

    foreach ($shortcutPath in @(
        (Join-Path $desktop 'Auto Bid Builder.lnk'),
        (Join-Path $startMenu 'Auto Bid Builder.lnk')
    )) {
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = $pythonwPath
        $shortcut.Arguments = '-m auto_bid_builder.gui'
        $shortcut.WorkingDirectory = $InstallRoot
        $shortcut.Description = 'JTI Millwork Auto Bid Builder'
        $shortcut.Save()
    }

    Write-Host "`nInstallation complete." -ForegroundColor Green
    Write-Host "A desktop shortcut named 'Auto Bid Builder' has been created."
    Write-Host "The app will guide users through first-time setup and can update itself from GitHub."

    if (-not $NoLaunch) {
        Write-Step "Launching Auto Bid Builder"
        Start-Process -FilePath $pythonwPath -ArgumentList '-m auto_bid_builder.gui' -WorkingDirectory $InstallRoot
    }
}
catch {
    Write-Host "`nInstallation could not be completed:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host "`nNothing in the JTI bid data folders was changed. Fix the item above and run this installer again."
    Read-Host 'Press Enter to close'
    exit 1
}
