param([string]$ToolsRoot = (Join-Path $PSScriptRoot '../../.tools/zephyr'))
$ErrorActionPreference = 'Stop'
$ToolsRoot = [IO.Path]::GetFullPath($ToolsRoot)
New-Item -ItemType Directory -Force $ToolsRoot | Out-Null
function Run([scriptblock]$Command) { & $Command; if ($LASTEXITCODE -ne 0) { throw "Tool failed: $Command" } }
$python = Join-Path $ToolsRoot 'venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $python)) { Run { uv venv --python 3.12 (Join-Path $ToolsRoot 'venv') } }
Run { uv pip install --python $python west==1.4.0 cmake==3.31.6 ninja==1.11.1.4 ziglang==0.14.1 clang-format==20.1.8 }
$env:PATH = (Join-Path $ToolsRoot 'venv/Scripts') + ';' + $env:PATH
$zephyr = Join-Path $ToolsRoot 'zephyr'
if (!(Test-Path -LiteralPath $zephyr)) { Run { git clone --branch v4.2.0 --depth 1 https://github.com/zephyrproject-rtos/zephyr.git $zephyr } }
$revision = (& git -C $zephyr rev-parse HEAD).Trim()
if ($revision -ne '413b789deb391d3a37d06b463288a5fe765ee57e') { throw 'Unexpected Zephyr revision; use the pinned v4.2.0 checkout.' }
Push-Location $ToolsRoot
try {
    if (!(Test-Path -LiteralPath '.west')) { Run { west init -l zephyr } }
    Run { west update --narrow -o=--depth=1 cmsis cmsis_6 hal_nordic mbedtls tinycrypt }
    Run { uv pip install --python $python -r zephyr/scripts/requirements-base.txt }
    $release = 'https://github.com/zephyrproject-rtos/sdk-ng/releases/download/v0.17.2/'
    $archives = @(
        @{Name='zephyr-sdk-0.17.2_windows-x86_64_minimal.7z'; File='sdk.7z'; Hash='819C6988E0C7EAB315689563D78424B6835D82AE49E59ABE27D1139C905E434C'},
        @{Name='toolchain_windows-x86_64_arm-zephyr-eabi.7z'; File='arm.7z'; Hash='D29E27A4223FEE6A866F72C69322493E97767C568F51EEB0DB3F135D3B200DA1'}
    )
    foreach ($archive in $archives) {
        if (!(Test-Path -LiteralPath $archive.File)) { Run { curl.exe -L --fail --silent --show-error ($release + $archive.Name) -o $archive.File } }
        if ((Get-FileHash -LiteralPath $archive.File -Algorithm SHA256).Hash -ne $archive.Hash) { throw "Checksum mismatch: $($archive.File)" }
    }
    if (!(Test-Path -LiteralPath 'zephyr-sdk-0.17.2')) { Run { tar -xf sdk.7z } }
    if (!(Test-Path -LiteralPath 'zephyr-sdk-0.17.2/arm-zephyr-eabi')) { Run { tar -xf arm.7z -C zephyr-sdk-0.17.2 } }
} finally { Pop-Location }
Write-Output "Pinned firmware tools ready in $ToolsRoot"
