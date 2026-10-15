<#
Windows side of Animesito. Called by Instalar.bat and Iniciar.bat.

  install  runs scripts/install.sh inside WSL, pointing it at ComfyUI's models;
           it downloads the model sets chosen with -Models (or asks)
  start    starts ComfyUI and Ollama if they are down, then the app, and opens it

The repo lives inside a WSL distro and this runs from its \\wsl.localhost (or
\\wsl$) path; the distro and the Linux path are read from that path.
Keep this file ASCII: Windows PowerShell 5.1 reads BOM-less files as ANSI.
#>
param(
    [Parameter(Mandatory = $true)][ValidateSet('install', 'start')][string]$Action,
    # ComfyUI folder on Windows. Default: the parent of JFAST_COMFY_MODELS_DIR in
    # animesito\.env, else Desktop\ComfyUI.
    [string]$ComfyDir,
    # Model sets from scripts/models.toml: comma list, 'all' or 'none'. Default: ask.
    [string]$Models
)
$ErrorActionPreference = 'Stop'

$ComfyUrl = 'http://127.0.0.1:8188/system_stats'
$OllamaUrl = 'http://127.0.0.1:11434/api/tags'
# Not "localhost": Windows tries ::1 first, and mirrored WSL only forwards the
# 127.0.0.1 that Vite listens on, so the request hangs.
$AppUrl = 'http://127.0.0.1:7799'

$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..')).TrimEnd('\')
if ($repo -notmatch '^\\\\wsl(?:\.localhost|\$)\\([^\\]+)(\\.+)$') {
    throw "Run this from the repo inside WSL (\\wsl.localhost\<distro>\...), not from $repo."
}
$distro = $Matches[1]
$linuxRepo = $Matches[2] -replace '\\', '/'

function ConvertTo-LinuxPath([string]$path) {
    if ($path -notmatch '^([A-Za-z]):\\?(.*)$') { throw "Not a drive path: $path" }
    return '/mnt/' + $Matches[1].ToLower() + '/' + ($Matches[2] -replace '\\', '/')
}

function ConvertTo-WindowsPath([string]$path) {
    if ($path -notmatch '^/mnt/([a-z])/(.*)$') { return $null }
    return $Matches[1].ToUpper() + ':\' + ($Matches[2] -replace '/', '\')
}

function Get-ComfyDir {
    if ($ComfyDir) { return $ComfyDir }
    $envFile = Join-Path $repo 'animesito\.env'
    if (Test-Path $envFile) {
        $hit = Select-String -Path $envFile -Pattern '^JFAST_COMFY_MODELS_DIR=(.+)$' | Select-Object -First 1
        if ($hit) {
            $models = ConvertTo-WindowsPath $hit.Matches[0].Groups[1].Value.Trim()
            if ($models) { return Split-Path $models -Parent }
        }
    }
    return Join-Path ([Environment]::GetFolderPath('Desktop')) 'ComfyUI'
}

function Test-Http([string]$url) {
    try {
        $null = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
        return $true
    } catch {
        return $false
    }
}

function Wait-Http([string]$url, [int]$seconds, [string]$name) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Http $url) { return $true }
        Start-Sleep -Seconds 2
    }
    Write-Warning "$name did not answer on $url after $seconds s."
    return $false
}

function Invoke-Wsl([string[]]$command) {
    & wsl.exe -d $distro --cd $linuxRepo -- @command
    if ($LASTEXITCODE -ne 0) { throw "Failed in WSL ($distro): $($command -join ' ')" }
}

function Test-MirroredNetworking {
    # WSL reaches ComfyUI and Ollama on 127.0.0.1 only with mirrored networking.
    $config = Join-Path $env:USERPROFILE '.wslconfig'
    if (-not ((Test-Path $config) -and (Select-String -Path $config -Pattern '^\s*networkingMode\s*=\s*mirrored' -Quiet))) {
        Write-Warning "networkingMode=mirrored is not set in $config. Without it the app inside WSL cannot reach ComfyUI or Ollama on 127.0.0.1. Add it under [wsl2] and run 'wsl --shutdown'."
    }
}

function Start-Comfy([string]$dir) {
    if (Test-Http $ComfyUrl) { Write-Host 'ComfyUI: already running'; return }
    $launcher = @('Iniciar ComfyUI.bat', 'run_nvidia_gpu.bat') |
        ForEach-Object { Join-Path $dir $_ } | Where-Object { Test-Path $_ } | Select-Object -First 1
    $python = Join-Path $dir 'venv\Scripts\python.exe'
    if ($launcher) {
        Start-Process -FilePath $launcher -WorkingDirectory $dir
    } elseif (Test-Path $python) {
        Start-Process -FilePath $python -ArgumentList @('main.py', '--disable-smart-memory') -WorkingDirectory $dir
    } else {
        throw "ComfyUI not found in $dir. Pass -ComfyDir, or fix JFAST_COMFY_MODELS_DIR in animesito\.env."
    }
    Write-Host 'ComfyUI: starting...'
    [void](Wait-Http $ComfyUrl 180 'ComfyUI')
}

function Start-Ollama {
    if (Test-Http $OllamaUrl) { Write-Host 'Ollama: already running'; return }
    $app = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama app.exe'
    if (Test-Path $app) {
        Start-Process -FilePath $app
    } elseif (Get-Command ollama.exe -ErrorAction SilentlyContinue) {
        Start-Process -FilePath 'ollama.exe' -ArgumentList 'serve' -WindowStyle Minimized
    } else {
        Write-Warning 'Ollama is not installed: "Mejorar con IA" will be unavailable.'
        return
    }
    Write-Host 'Ollama: starting...'
    [void](Wait-Http $OllamaUrl 30 'Ollama')
}

function Start-App {
    if (Test-Http $AppUrl) {
        Write-Host 'Animesito: already running'
    } else {
        # Its own window: closing it stops the app (scripts/dev.sh cleans up on the next start).
        Start-Process -FilePath 'wsl.exe' -ArgumentList @('-d', $distro, '--cd', $linuxRepo, '--', 'bash', 'scripts/dev.sh')
        Write-Host 'Animesito: starting...'
        if (-not (Wait-Http $AppUrl 120 'Animesito')) { return }
    }
    Start-Process $AppUrl
}

Write-Host "Animesito: $distro $linuxRepo"
switch ($Action) {
    'install' {
        Test-MirroredNetworking
        $comfy = Get-ComfyDir
        $command = @('bash', 'scripts/install.sh')
        if (Test-Path (Join-Path $comfy 'models')) {
            $command += @('--comfy-models', (ConvertTo-LinuxPath (Join-Path $comfy 'models')))
        } else {
            Write-Warning "ComfyUI not found in $comfy; run again with -ComfyDir <folder>."
        }
        if ($Models) { $command += @('--models', $Models) }
        # Ollama models are pulled through its API.
        Start-Ollama
        Invoke-Wsl $command
    }
    'start' {
        if (-not (Test-Path (Join-Path $repo 'animesito\.venv'))) { throw 'Not installed yet: run Instalar.bat first.' }
        Test-MirroredNetworking
        Start-Comfy (Get-ComfyDir)
        Start-Ollama
        Start-App
    }
}
