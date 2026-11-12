@echo off
cd /d "c:\Users\user\Downloads\bookmtaani\bookmtaani"
".venv\Scripts\python.exe" manage.py test > ".agents\tasks\test_stdout.txt" 2>&1
echo Exit code: %ERRORLEVEL%
type ".agents\tasks\test_stdout.txt"
