param([string[]]$Tasks=@(':app:assembleDebug',':app:assembleDebugAndroidTest',':app:lintDebug'),[switch]$SkipCore)
$ErrorActionPreference='Stop'
$auraWorkspace=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$auraTools=Join-Path $auraWorkspace '.tools/android'
$env:JAVA_HOME=Join-Path $auraTools 'jdk17/jdk-17.0.20.1+1'
$env:ANDROID_HOME=Join-Path $auraTools 'sdk'
$env:GRADLE_USER_HOME=Join-Path $auraTools 'gradle-home'
$auraGradle=Join-Path $auraTools 'gradle/gradle-9.4.1/bin/gradle.bat'
if(!(Test-Path -LiteralPath $auraGradle)){throw 'Run mobile/android/setup.ps1 first.'}
if(!$SkipCore){
    & uv run --project (Join-Path $auraWorkspace 'companion') --locked python (Join-Path $PSScriptRoot 'core/scripts/verify_core.py') --gradle $auraGradle
    if($LASTEXITCODE -ne 0){throw 'Cross-language core verification failed.'}
}
Push-Location $PSScriptRoot
try {
    & $auraGradle --no-daemon --console=plain @Tasks
    if($LASTEXITCODE -ne 0){throw 'Android build/check failed.'}
} finally {Pop-Location}
