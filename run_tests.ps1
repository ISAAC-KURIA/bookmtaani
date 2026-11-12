Set-Location "c:\Users\user\Downloads\bookmtaani\bookmtaani"
$out = & ".\.venv\Scripts\python.exe" manage.py test 2>&1
$out | Out-File -FilePath ".\.agents\tasks\test_stdout.txt" -Encoding UTF8
$LASTEXITCODE
$out
