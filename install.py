import shutil
import subprocess
import os

try:
    import requests
except ImportError:
    subprocess.run(["pip", "install", "requests"], check=True)
    import requests

try:
    subprocess.run(
        ["git", "--version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
except (subprocess.CalledProcessError, FileNotFoundError):
    print("Git is not installed or not found in PATH. Please install Git to continue.")
    input("Press Enter to exit...")
    exit(1)

if (
    input("MSS Proposal Automation will install in this folder. Continue? (y/n): ")
    == "y"
):
    response = requests.get(
        "https://raw.githubusercontent.com/FusionAtom360/MSSProposalAutomation/main/src/details.json"
    )
    if response.status_code == 200:
        details = response.json()
        version = details.get("version", "0.0.0")
        print(f"Installing MSS Proposal Automation version {version}...")
        subprocess.run(
            ["git", "clone", "https://github.com/FusionAtom360/MSSProposalAutomation"]
        , check=True)
        subprocess.run(["python", "-m", "venv", "MSSProposalAutomation/.venv"], check=True)
        subprocess.run(["MSSProposalAutomation/.venv/Scripts/pip", "install", "-r", "MSSProposalAutomation/src/requirements.txt"], check=True)
        os.remove("MSSProposalAutomation/.gitignore")
        os.remove("MSSProposalAutomation/src/.gitignore")
        os.remove("MSSProposalAutomation/install.py")
        shutil.rmtree("MSSProposalAutomation/.git")
        required_keys = [
            "SOLARGRAF_EMAIL",
            "SOLARGRAF_PASSWORD",
            "LOAN_INTEREST_RATE"
            "BIDS_FOLDER"
        ]
        with open("MSSProposalAutomation/src/.env", "w", encoding="utf-8") as file:
            for key in required_keys:
                file.write(f"{key}={input(f'{key}=')}\n")
        script_dir = os.path.dirname(os.path.abspath(__file__))
        subprocess.Popen(["cd", os.path.join(script_dir, "MSSProposalAutomation/"), "&&", os.path.join(script_dir, "MSSProposalAutomation/.venv/Scripts/python.exe"), "src/main.py"], shell=True)
        os.remove("install.py")
        exit(0)
    else:
        print("Failed to fetch version details. Please check your internet connection.")
        input("Press Enter to exit...")
        exit(1)
