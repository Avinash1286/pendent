param(
  [string]$Java = 'java',
  [string]$Jar = 'tools/freerouting-2.4.1.jar',
  [string]$InputDsn = 'output/aura-a03.dsn',
  [string]$OutputSes = 'output/aura-a03-route-attempt.ses',
  [int]$Passes = 12
)
$ErrorActionPreference='Stop'
if (!(Test-Path -LiteralPath $Jar)) { throw 'Install Freerouting from its official GitHub releases and supply -Jar.' }
if (!(Test-Path -LiteralPath $InputDsn)) { throw 'Export the matching board through KiCad Specctra DSN first.' }
# In 2.4.1, max_threads=0 normalizes to all processors despite stale CLI prose.
# Disable optimization explicitly so the pass limit bounds this routing attempt.
& $Java '-Djava.awt.headless=true' '-Xmx768m' -jar $Jar '--gui.enabled=false' '--user_data_path=output/freerouting-local-runtime' '--logging.console.level=INFO' '--logging.file.level=INFO' '--router.optimizer.enabled=false' '--router.job_timeout=00:30:00' -da -de $InputDsn -do $OutputSes -mp $Passes -mt 1
if ($LASTEXITCODE -ne 0) { throw "Freerouting failed with exit code $LASTEXITCODE" }
Write-Output 'Import SES into a copy of the exact input board. Routing completion must be checked independently with KiCad DRC.'
