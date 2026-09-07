param([string]$ToolsRoot = (Join-Path $PSScriptRoot '../../.tools/zephyr'), [switch]$QualifiedHardware)
$ErrorActionPreference = 'Stop'
$ToolsRoot = [IO.Path]::GetFullPath($ToolsRoot)
$app = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$env:PATH = (Join-Path $ToolsRoot 'venv/Scripts') + ';' + $env:PATH
$env:ZEPHYR_BASE = Join-Path $ToolsRoot 'zephyr'
$env:ZEPHYR_SDK_INSTALL_DIR = Join-Path $ToolsRoot 'zephyr-sdk-0.17.2'
$env:ZEPHYR_TOOLCHAIN_VARIANT = 'zephyr'
$build = Join-Path $ToolsRoot $(if ($QualifiedHardware) {'build-aura-qualified'} else {'build-aura'})
$args = @('build', '-b', 'aura_a03/nrf52840', $app, '-d', $build)
if ($QualifiedHardware) { $args += @('--', '-DEXTRA_CONF_FILE=qualified.conf') }
Push-Location $ToolsRoot
try { & west @args; if ($LASTEXITCODE -ne 0) { throw 'ARM firmware build failed.' } } finally { Pop-Location }
if ($QualifiedHardware) {
    Write-Output "Qualification build only: $build. Do not flash an unqualified assembly."
} else {
    $release = Join-Path $app 'release'
    New-Item -ItemType Directory -Force $release | Out-Null
    foreach ($ext in @('elf','hex','bin','map')) { Copy-Item -LiteralPath (Join-Path $build "zephyr/zephyr.$ext") -Destination (Join-Path $release "aura-a03.$ext") -Force }
    Copy-Item -LiteralPath (Join-Path $build 'zephyr/.config') -Destination (Join-Path $release 'build.config') -Force
    & (Join-Path $ToolsRoot 'venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'manifest.py')
    if ($LASTEXITCODE -ne 0) { throw 'Release manifest failed.' }
}
