import subprocess
try:
    result = subprocess.run(['git', 'log', '-n', '3', '--oneline'], capture_output=True, text=True, cwd=r'e:\project-django')
    print("GIT LOG:")
    print(result.stdout)
except Exception as e:
    print("Error:", e)
