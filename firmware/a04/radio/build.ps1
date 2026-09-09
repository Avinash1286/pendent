#requires -Version 7.0
param([ValidateSet('arm')][string]$Mode='arm', [ValidateRange(1,8)][int]$Jobs=2, [switch]$Pristine)
$ErrorActionPreference='Stop'
$radioWorkspace=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$radioTools=Join-Path $radioWorkspace '.tools/zephyr'
$radioPython=Join-Path $radioTools 'venv/Scripts/python.exe'
if(!(Test-Path -LiteralPath $radioPython)){throw 'Install the pinned firmware/scripts/setup.ps1 toolchain first.'}
$env:PATH=(Join-Path $radioTools 'venv/Scripts')+';'+$env:PATH
$env:ZEPHYR_BASE=Join-Path $radioTools 'zephyr'
$env:ZEPHYR_SDK_INSTALL_DIR=Join-Path $radioTools 'zephyr-sdk-0.17.2'
$env:ZEPHYR_TOOLCHAIN_VARIANT='zephyr'
$env:CMAKE_BUILD_PARALLEL_LEVEL=[string]$Jobs
$radioEvidence=Join-Path $PSScriptRoot 'verification'
$radioBuild=[IO.Path]::GetFullPath((Join-Path $radioWorkspace '.tools/a04-radio/arm'))
New-Item -ItemType Directory -Force -Path $radioEvidence | Out-Null
function Invoke-Radio([string]$Executable,[string[]]$Arguments,[string]$Report){
    $radioOutput=& $Executable @Arguments 2>&1
    $radioExit=$LASTEXITCODE
    $radioText=($radioOutput | ForEach-Object {$_.ToString().TrimEnd()}) -join "`n"
    [IO.File]::WriteAllText((Join-Path $radioEvidence $Report),$radioText+"`n",[Text.UTF8Encoding]::new($false))
    $radioOutput | Select-Object -Last 14
    if($radioExit -ne 0){throw "Radio command failed; see verification/$Report"}
}
Invoke-Radio $radioPython @((Join-Path $PSScriptRoot '../scripts/setup.py')) 'dependency-check.txt'
$radioInputs=Join-Path $radioEvidence 'arm-inputs.json'
Invoke-Radio $radioPython @((Join-Path $PSScriptRoot 'report_resources.py'),'--capture-inputs',$radioInputs) 'arm-inputs.txt'
$radioArguments=@('build','-b','nrf52840dk/nrf52840',$PSScriptRoot,'-d',$radioBuild)
if($Pristine){
    $radioResolved=if(Test-Path -LiteralPath $radioBuild){(Resolve-Path -LiteralPath $radioBuild).Path}else{$radioBuild}
    $radioExpected=[IO.Path]::GetFullPath((Join-Path $radioWorkspace '.tools/a04-radio/arm'))
    if($radioResolved -ne $radioExpected -or !$radioResolved.StartsWith($radioWorkspace.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)){
        throw 'Refusing pristine cleanup outside the exact generated radio ARM directory.'
    }
    $radioArguments+=@('--pristine','always')
}
Push-Location $radioTools
try {Invoke-Radio 'west' $radioArguments 'arm-build.txt'} finally {Pop-Location}
Invoke-Radio $radioPython @((Join-Path $PSScriptRoot 'report_resources.py'),'--inputs',$radioInputs) 'arm-resources.txt'
Write-Output 'Separate A04 Bluetooth DK image cross-compiled. No device was flashed or serial port opened.'
