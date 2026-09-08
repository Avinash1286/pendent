param([switch]$Refresh)
$ErrorActionPreference = 'Stop'
$hardwareRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Push-Location $hardwareRoot
try {
    $cli = 'C:/Program Files/KiCad/10.0/bin/kicad-cli.exe'
    if ($Refresh) {
        & $cli sch export netlist --format kicadxml --output output/aura-a03-native.net.xml output/aura-a03-electrical.kicad_sch
        if ($LASTEXITCODE -ne 0) { throw 'Native KiCad XML export failed' }
        & $cli sch erc --format json --output output/aura-a03-native-erc.json output/aura-a03-electrical.kicad_sch
        if ($LASTEXITCODE -ne 0) { throw 'Native KiCad ERC execution failed' }
    }
    $xml = [xml](Get-Content output/aura-a03-native.net.xml -Raw)
    $wanted = Get-Content output/logical-netlist.json -Raw | ConvertFrom-Json -AsHashtable
    $manifest = Get-Content output/design-manifest.json -Raw | ConvertFrom-Json -AsHashtable
    $footprints = Get-Content src/footprints.json -Raw | ConvertFrom-Json -AsHashtable
    $erc = Get-Content output/aura-a03-native-erc.json -Raw | ConvertFrom-Json -AsHashtable
    $failures = [System.Collections.Generic.List[string]]::new()
    $actual = @{}
    foreach ($net in $xml.export.nets.net) {
        $actual[[string]$net.name] = @($net.node | ForEach-Object { "$($_.ref).$($_.pin)" } | Sort-Object)
    }
    $checkedNets = @()
    foreach ($name in ($wanted.Keys | Sort-Object)) {
        $expectedPins = @($wanted[$name] | Sort-Object)
        $gotPins = @($actual[$name] | Sort-Object)
        $pass = ($expectedPins -join '|') -ceq ($gotPins -join '|')
        if (-not $pass) { $failures.Add("Net membership mismatch: $name") }
        $checkedNets += [ordered]@{ name=$name; status=$(if ($pass) {'PASS'} else {'FAIL'}); pins=$gotPins }
    }
    $expectedNC = @($manifest.parts | ForEach-Object { $ref = $_.ref; $_.nc | ForEach-Object { if ($_ -ne $null) { "$ref.$_" } } } | Sort-Object)
    $extraNets = @($actual.Keys | Where-Object { -not $wanted.ContainsKey($_) } | Sort-Object)
    $actualNC = @($extraNets | ForEach-Object {
        if ($_ -notlike 'unconnected-*' -or $actual[$_].Count -ne 1) { $failures.Add("Unexpected extra native net: $_") }
        $actual[$_]
    } | Sort-Object)
    if (($expectedNC -join '|') -cne ($actualNC -join '|')) { $failures.Add('Intentional NC pin set differs from manifest') }
    $expectedRefs = @($manifest.parts.ref | Sort-Object)
    $actualRefs = @($xml.export.components.comp.ref | Sort-Object)
    if (($expectedRefs -join '|') -cne ($actualRefs -join '|')) { $failures.Add('Native component reference set differs from manifest') }
    $componentChecks = @()
    foreach ($comp in $xml.export.components.comp) {
        $ref = [string]$comp.ref
        $part = $manifest.parts | Where-Object ref -CEQ $ref
        $expectedFP = if ($ref -match '^J[1-4]$') { "AURA:$($part.mpn)" } elseif ($ref -in @('C3','C4')) { 'AURA:AURA_SiCap_1.2x0.7mm_P0.7mm' } else { $footprints[$part.fp].library }
        $actualFP = [string]$comp.footprint
        $mpnField = @($comp.property | Where-Object name -CEQ 'MPN')[0]
        $actualMPN = [string]$mpnField.value
        if ($actualFP -cne $expectedFP) { $failures.Add("Footprint link differs for ${ref}: '$actualFP' vs '$expectedFP'") }
        if ($actualMPN -cne $part.mpn) { $failures.Add("MPN differs for $ref") }
        $componentChecks += [ordered]@{ reference=$ref; footprint=$actualFP; mpn=$actualMPN }
    }
    $violations = @($erc.sheets | ForEach-Object { $_.violations } | Where-Object { $_ -ne $null })
    if ($violations.Count -ne 0) { $failures.Add("Native ERC has $($violations.Count) findings") }
    $sheetFiles = @('radio','audio','storage','charging','controls' | ForEach-Object { "output/a03-$_.kicad_sch" })
    $ncMarkers = 0
    $powerFlags = 0
    foreach ($sheet in $sheetFiles) {
        $source = Get-Content $sheet -Raw
        $ncMarkers += [regex]::Matches($source,'\(no_connect\s').Count
        $powerFlags += [regex]::Matches($source,'\(lib_id "power:PWR_FLAG"\)').Count
    }
    if ($ncMarkers -ne $expectedNC.Count) { $failures.Add("NC marker count $ncMarkers differs from $($expectedNC.Count)") }
    if ($powerFlags -ne 4) { $failures.Add("Expected four explicit external/conditional power flags, found $powerFlags") }
    $files = @('output/design-manifest.json','output/logical-netlist.json','output/aura-a03-electrical.kicad_sch','output/aura-a03-native.net.xml','output/aura-a03-native-erc.json','library/AuraA03.kicad_sym') + $sheetFiles
    $hashes = @($files | ForEach-Object { [ordered]@{ path=$_; sha256=(Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash.ToLowerInvariant() } })
    $report = [ordered]@{
        schemaVersion=1; verifiedAt=(Get-Date).ToUniversalTime().ToString('o'); status=$(if ($failures.Count -eq 0) {'PASS'} else {'FAIL'})
        nativeTool=[string]$xml.export.design.tool; rootSchematic='output/aura-a03-electrical.kicad_sch'
        componentCount=$actualRefs.Count; intendedNetCount=$wanted.Count; connectedPinCount=($wanted.Values | ForEach-Object { $_ }).Count
        nativeNetCount=$actual.Count; intentionalNCCount=$actualNC.Count; exactNCMarkers=$ncMarkers; explicitPowerFlags=$powerFlags
        ercErrors=@($violations | Where-Object severity -EQ error).Count; ercWarnings=@($violations | Where-Object severity -EQ warning).Count
        projectAuthoredExclusions=@(); defaultIgnoredChecks=$erc.ignored_checks
        checkedNets=$checkedNets; intentionalNCs=$actualNC; components=$componentChecks; sourceHashes=$hashes; failures=@($failures)
        limitation='Electrical parity and native ERC only. No board synchronization; battery, RF, thermal and firmware qualification remain separate.'
    }
    $report | ConvertTo-Json -Depth 12 | Set-Content output/native-schematic-parity.json -Encoding utf8
    [ordered]@{ status=$report.status; components=$report.componentCount; intendedNets=$report.intendedNetCount; connectedPins=$report.connectedPinCount; intentionalNCs=$report.intentionalNCCount; ercErrors=$report.ercErrors; ercWarnings=$report.ercWarnings; failures=$report.failures } | ConvertTo-Json -Depth 4
    if ($failures.Count -ne 0) { exit 1 }
} finally { Pop-Location }
