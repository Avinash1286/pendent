param([ValidateSet('all','host','arm')][string]$Mode = 'all', [string]$ToolsRoot = (Join-Path $PSScriptRoot '../../../.tools/zephyr'))
$ErrorActionPreference = 'Stop'
$a04Tools = [IO.Path]::GetFullPath($ToolsRoot)
$a04App = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$a04Work = [IO.Path]::GetFullPath((Join-Path $a04App '../..'))
$a04Build = Join-Path $a04Work '.tools/a04-opus'
$a04Python = Join-Path $a04Tools 'venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $a04Python)) { throw 'Run the existing firmware/scripts/setup.ps1 to install the pinned Zephyr tools first.' }
$env:PATH = (Join-Path $a04Tools 'venv/Scripts') + ';' + $env:PATH
& $a04Python (Join-Path $PSScriptRoot 'setup.py')
if ($LASTEXITCODE -ne 0) { throw 'Pinned Opus source verification failed.' }
New-Item -ItemType Directory -Force (Join-Path $a04App 'verification') | Out-Null
function Invoke-A04Build([string]$Executable, [string[]]$Arguments, [string]$Report) {
    $a04Output = & $Executable @Arguments 2>&1
    $a04Exit = $LASTEXITCODE
    $a04CleanOutput = $a04Output | ForEach-Object { $_.ToString().TrimEnd() }
    [IO.File]::WriteAllText((Join-Path $a04App "verification/$Report"), ($a04CleanOutput -join "`n") + "`n", [Text.UTF8Encoding]::new($false))
    $a04Output | Select-Object -Last 12
    if ($a04Exit -ne 0) { throw "A04 command failed; see verification/$Report" }
}
if ($Mode -in @('all','host')) {
    $a04Zig = Join-Path $a04Tools 'venv/Lib/site-packages/ziglang/zig.exe'
    Invoke-A04Build 'cmake' @('-S',(Join-Path $a04App 'tests'),'-B',(Join-Path $a04Build 'host'),'-G','Ninja','-DCMAKE_BUILD_TYPE=Release',"-DCMAKE_C_COMPILER=$a04Zig",'-DCMAKE_C_COMPILER_ARG1=cc') 'host-configure.txt'
    Invoke-A04Build 'cmake' @('--build',(Join-Path $a04Build 'host'),'-j','6') 'host-build.txt'
    Invoke-A04Build $a04Python @((Join-Path $PSScriptRoot 'verify_fixtures.py')) 'host-verification.txt'
    Invoke-A04Build $a04Python @((Join-Path $PSScriptRoot 'verify_archives.py')) 'archive-verification.txt'
    $a04PreviousPythonPath = $env:PYTHONPATH
    $env:PYTHONPATH = Join-Path $a04Work 'companion/src'
    try {
        Invoke-A04Build $a04Python @('-m','unittest','discover','-s',(Join-Path $a04Work 'companion/tests'),'-p','test_protocol_v2.py','-q') 'archive-python-tests.txt'
    } finally { $env:PYTHONPATH = $a04PreviousPythonPath }
}
if ($Mode -in @('all','arm')) {
    $env:ZEPHYR_BASE = Join-Path $a04Tools 'zephyr'
    $env:ZEPHYR_SDK_INSTALL_DIR = Join-Path $a04Tools 'zephyr-sdk-0.17.2'
    $env:ZEPHYR_TOOLCHAIN_VARIANT = 'zephyr'
    Push-Location $a04Tools
    try {
        Invoke-A04Build 'west' @('build','-b','nrf52840dk/nrf52840',$a04App,'-d',(Join-Path $a04Build 'arm')) 'arm-build.txt'
    } finally { Pop-Location }
    & $a04Python (Join-Path $PSScriptRoot 'report_resources.py')
    if ($LASTEXITCODE -ne 0) { throw 'A04 resource report failed.' }
}
Write-Output 'A04 experimental codec build complete. No device was flashed; A03 release artifacts were not modified.'
