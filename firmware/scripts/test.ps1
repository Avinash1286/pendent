$ErrorActionPreference = 'Stop'
$app = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$tools = [IO.Path]::GetFullPath((Join-Path $app '../.tools/zephyr'))
$python = Join-Path $tools 'venv/Scripts/python.exe'
$executable = Join-Path $tools 'host-tests.exe'
& $python -m ziglang cc -std=c11 -Wall -Wextra -Werror "-I$app/include" (Join-Path $app 'src/journal.c') (Join-Path $app 'tests/host.c') -o $executable
if ($LASTEXITCODE -ne 0) { throw 'Host test compile failed.' }
& $executable | Tee-Object -FilePath (Join-Path $app 'verification/host-tests.txt')
if ($LASTEXITCODE -ne 0) { throw 'Host tests failed.' }
$nandExecutable = Join-Path $tools 'nand-tests.exe'
& $python -m ziglang cc -std=c11 -Wall -Wextra -Werror "-I$app/include" "-I$app/tests/stubs" (Join-Path $app 'src/nand.c') (Join-Path $app 'tests/nand_commands.c') -o $nandExecutable
if ($LASTEXITCODE -ne 0) { throw 'NAND command test compile failed.' }
& $nandExecutable | Tee-Object -FilePath (Join-Path $app 'verification/nand-tests.txt')
if ($LASTEXITCODE -ne 0) { throw 'NAND command tests failed.' }
