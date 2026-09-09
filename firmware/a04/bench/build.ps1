param([ValidateSet('all','arm','host')][string]$Mode='all')
$ErrorActionPreference='Stop'
$benchRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$benchTools=Join-Path $benchRoot '.tools/zephyr'
$benchPython=Join-Path $benchTools 'venv/Scripts/python.exe'
if(!(Test-Path -LiteralPath $benchPython)){throw 'Install the pinned firmware/scripts/setup.ps1 toolchain first.'}
$env:PATH=(Join-Path $benchTools 'venv/Scripts')+';'+$env:PATH
$benchEvidence=Join-Path $PSScriptRoot 'verification'
New-Item -ItemType Directory -Force -Path $benchEvidence | Out-Null
function Invoke-Bench([string]$Executable,[string[]]$Arguments,[string]$Report){
    $benchOutput=& $Executable @Arguments 2>&1
    $benchExit=$LASTEXITCODE
    $benchText=($benchOutput | ForEach-Object {$_.ToString().TrimEnd()}) -join "`n"
    [IO.File]::WriteAllText((Join-Path $benchEvidence $Report),$benchText+"`n",[Text.UTF8Encoding]::new($false))
    $benchOutput | Select-Object -Last 14
    if($benchExit -ne 0){throw "Bench command failed; see verification/$Report"}
}
& $benchPython (Join-Path $PSScriptRoot '../scripts/setup.py')
if($LASTEXITCODE -ne 0){throw 'Pinned Opus dependency verification failed.'}
if($Mode -in @('all','host')){
    Invoke-Bench $benchPython @((Join-Path $PSScriptRoot 'verify_host.py')) 'host-run.txt'
    Invoke-Bench $benchPython @((Join-Path $PSScriptRoot 'test_control.py'),'--report',
        (Join-Path $PSScriptRoot 'tests/control-report.json')) 'control-tests.txt'
}
if($Mode -in @('all','arm')){
    $env:ZEPHYR_BASE=Join-Path $benchTools 'zephyr'
    $env:ZEPHYR_SDK_INSTALL_DIR=Join-Path $benchTools 'zephyr-sdk-0.17.2'
    $env:ZEPHYR_TOOLCHAIN_VARIANT='zephyr'
    $benchBuild=Join-Path $benchRoot '.tools/a04-bench/arm'
    Push-Location $benchTools
    try {
        Invoke-Bench 'west' @('build','-b','nrf52840dk/nrf52840',$PSScriptRoot,'-d',$benchBuild) 'arm-build.txt'
    } finally {Pop-Location}
    Invoke-Bench $benchPython @((Join-Path $PSScriptRoot 'report_resources.py')) 'arm-resources.txt'
}
Write-Output 'Separate A04 bench build finished. No board was flashed or serial port opened.'
