param([switch]$DownloadsOnly)
$ErrorActionPreference='Stop'
$auraWorkspace=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$auraTools=Join-Path $auraWorkspace '.tools/android'
New-Item -ItemType Directory -Force -Path $auraTools | Out-Null
function Get-AuraArchive([string]$Name,[string]$Url,[string]$Expected,[string]$Folder,[string]$Marker){
    $auraArchive=Join-Path $auraTools $Name
    if(!(Test-Path -LiteralPath $auraArchive)){
        & curl.exe --fail --location --silent --show-error --retry 2 $Url --output $auraArchive
        if($LASTEXITCODE -ne 0){throw "Download failed: $Name"}
    }
    if((Get-FileHash -LiteralPath $auraArchive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Expected){
        throw "Checksum differs; preserve and inspect $Name before retrying."
    }
    $auraExtract=Join-Path $auraTools $Folder
    if(!(Test-Path -LiteralPath (Join-Path $auraExtract $Marker))){
        New-Item -ItemType Directory -Force -Path $auraExtract | Out-Null
        Expand-Archive -LiteralPath $auraArchive -DestinationPath $auraExtract
    }
    Write-Output "Verified and available: $Name"
}
Get-AuraArchive 'jdk17.zip' 'https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.20.1%2B1/OpenJDK17U-jdk_x64_windows_hotspot_17.0.20.1_1.zip' 'e53a79c3c3d86865bd7e787903884331068e71321714ffd44f145785affc7cb0' 'jdk17' 'jdk-17.0.20.1+1/bin/javac.exe'
Get-AuraArchive 'gradle-9.4.1-bin.zip' 'https://services.gradle.org/distributions/gradle-9.4.1-bin.zip' '2ab2958f2a1e51120c326cad6f385153bb11ee93b3c216c5fccebfdfbb7ec6cb' 'gradle' 'gradle-9.4.1/bin/gradle.bat'
Get-AuraArchive 'commandlinetools-22.zip' 'https://dl.google.com/android/repository/commandlinetools-win-15859902_latest.zip' '90ae805d20434428bffcb699c290860f19bb5f66a67e6b330067e3de801fb04a' 'commandline22' 'cmdline-tools/bin/sdkmanager.bat'
if($DownloadsOnly){return}
$env:JAVA_HOME=Join-Path $auraTools 'jdk17/jdk-17.0.20.1+1'
$auraSdk=Join-Path $auraTools 'sdk'
New-Item -ItemType Directory -Force -Path $auraSdk | Out-Null
$auraManager=Join-Path $auraTools 'commandline22/cmdline-tools/bin/sdkmanager.bat'
# Standard SDK licenses are accepted as part of the requested tool installation.
# No connected device is selected, flashed or reset by this script.
("y`n" * 100) | & $auraManager "--sdk_root=$auraSdk" --licenses
if($LASTEXITCODE -ne 0){throw 'SDK license installation failed.'}
& $auraManager "--sdk_root=$auraSdk" 'platforms;android-37.0' 'build-tools;36.0.0' 'platform-tools'
if($LASTEXITCODE -ne 0){throw 'SDK package installation failed.'}
Write-Output "Android tools ready in $auraTools; no device or host virtualization settings changed."
