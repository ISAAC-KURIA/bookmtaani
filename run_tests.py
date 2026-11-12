"""Run Django tests and save output."""
import subprocess, sys, os

os.chdir(r"c:\Users\user\Downloads\bookmtaani\bookmtaani")
python = r".venv\Scripts\python.exe"
result = subprocess.run(
    [python, "manage.py", "test"],
    capture_output=True, text=True
)
output = result.stdout + result.stderr
with open(r".agents\tasks\test_stdout.txt", "w", encoding="utf-8") as f:
    f.write(output)
print(output)
print(f"\nExit code: {result.returncode}")
sys.exit(result.returncode)
