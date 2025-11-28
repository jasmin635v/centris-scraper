import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List

try:
    import requests
except ImportError:
    requests = None

try:
    from prompt_toolkit.shortcuts import checkboxlist_dialog, radiolist_dialog
except ImportError:
    radiolist_dialog = None
    checkboxlist_dialog = None

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
TOOLS_DIR = SCRIPTS_DIR / "tools"
MISSIONS_DIR = REPO_ROOT / "missions"
PLANNER_DIR = MISSIONS_DIR / "_planner_logs"
ENV_OVERRIDES = {}
DEFAULT_PORT = 9222
PORT_RANGE = 20


def ensure_directories():
    MISSIONS_DIR.mkdir(exist_ok=True)
    PLANNER_DIR.mkdir(exist_ok=True, parents=True)


def read_sorted_directories(base: Path) -> List[Path]:
    if not base.exists():
        return []
    return sorted([p for p in base.iterdir() if p.is_dir()], key=lambda p: p.name)


def read_sorted_logs() -> List[Path]:
    if not PLANNER_DIR.exists():
        return []
    return sorted([p for p in PLANNER_DIR.glob("*.json")], key=lambda p: p.name)


def prompt_choice(items: List[Path], empty_msg: str, title: str = "Select an entry") -> Path:
    if not items:
        print(empty_msg)
        return None
    if radiolist_dialog:
        values = [(item, item.name) for item in items]
        selection = radiolist_dialog(title=title, text="", values=values).run()
        return selection
    for idx, item in enumerate(items, 1):
        print(f"{idx}. {item.name}")
    choice = input("Select an entry (or press Enter to cancel): ").strip()
    if not choice:
        return None
    try:
        index = int(choice) - 1
    except ValueError:
        print("Invalid selection.")
        return None
    if index < 0 or index >= len(items):
        print("Selection out of range.")
        return None
    return items[index]


def prompt_multi_choice(
    items: List[Path], empty_msg: str, title: str = "Select entries to delete"
) -> List[Path]:
    if not items:
        print(empty_msg)
        return []
    if checkboxlist_dialog:
        values = [(item, item.name) for item in items]
        selection = checkboxlist_dialog(
            title=title,
            text="Use space to toggle selections, then Enter to confirm.",
            values=values,
        ).run()
        return selection or []
    for idx, item in enumerate(items, 1):
        print(f"{idx}. {item.name}")
    choice = input("Select entries (comma-separated, 'a' for all, Enter to cancel): ").strip()
    if not choice:
        return []
    if choice.lower() == "a":
        return items
    selections = []
    for token in choice.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            idx = int(token) - 1
        except ValueError:
            print(f"Invalid selection: {token}")
            return []
        if idx < 0 or idx >= len(items):
            print(f"Selection out of range: {token}")
            return []
        selections.append(items[idx])
    return selections


def get_debugger_statuses():
    statuses = []
    if not requests:
        return statuses
    for port in range(DEFAULT_PORT, DEFAULT_PORT + PORT_RANGE):
        entry = {"port": port, "active": False, "description": "inactive"}
        url = f"http://127.0.0.1:{port}/json/version"
        try:
            resp = requests.get(url, timeout=1)
            resp.raise_for_status()
            data = resp.json()
            browser = data.get("Browser", "unknown")
            ws = data.get("webSocketDebuggerUrl", "unknown")
            entry["active"] = True
            entry["description"] = f"{browser} -> {ws}"
        except requests.RequestException:
            entry["description"] = "inactive"
        statuses.append(entry)
    return statuses


def format_debugger_lines(statuses, current_addr):
    lines = []
    if not statuses:
        lines.append("(requests module unavailable; cannot probe ports)")
        return lines
    for entry in statuses:
        state = "ACTIVE" if entry["active"] else "available"
        selected = ""
        if current_addr:
            if current_addr.endswith(str(entry["port"])) or current_addr == f"127.0.0.1:{entry['port']}":
                selected = " [SELECTED]"
        lines.append(f"  - Port {entry['port']}: {state} ({entry['description']}){selected}")
    return lines


def print_debugger_summary():
    statuses = get_debugger_statuses()
    current_addr = ENV_OVERRIDES.get("CHROME_DEBUGGER_ADDRESS")
    print("\nDebugger port summary:")
    for line in format_debugger_lines(statuses, current_addr):
        print(line)
    print()
    return statuses


def run_command(command: List[str]):
    print("\n[mission-menu] Running:", " ".join(command))
    env = os.environ.copy()
    env.update(ENV_OVERRIDES)
    result = subprocess.run(command, env=env)
    if result.returncode != 0:
        print(f"[mission-menu] Command exited with code {result.returncode}")


def choose_option(options, title="Select", text=None):
    if not options:
        return None
    if radiolist_dialog:
        return radiolist_dialog(title=title, text=text or "", values=options).run()
    if text:
        print(text)
    for idx, (_, label) in enumerate(options, 1):
        print(f"{idx}. {label}")
    choice = input("Choose an option: ").strip()
    if not choice:
        return None
    try:
        index = int(choice) - 1
        if index < 0 or index >= len(options):
            raise ValueError
    except ValueError:
        return None
    return options[index][0]


def plan_mission():
    clue = input("Enter mission clue: ").strip()
    if not clue:
        print("Clue is required.")
        return
    dry = input("Dry run only? [y/N]: ").strip().lower() == "y"
    command = [
        sys.executable,
        str(TOOLS_DIR / "plan_mission.py"),
        clue,
    ]
    if dry:
        command.append("--no-run/--dry-run")
    run_command(command)


def run_planner_log():
    logs = read_sorted_logs()
    log_path = prompt_choice(logs, "No planner logs found.", title="Select planner log to run")
    if not log_path:
        return
    dry = input("Dry run only? [y/N]: ").strip().lower() == "y"
    command = [
        sys.executable,
        str(TOOLS_DIR / "run_planner_log.py"),
        log_path.stem,
    ]
    if dry:
        command.append("--dry-run")
    run_command(command)


def rerun_mission():
    missions = [p for p in read_sorted_directories(MISSIONS_DIR) if p.name != "_planner_logs"]
    mission_dir = prompt_choice(missions, "No completed missions found.", title="Select mission to rerun")
    if not mission_dir:
        return
    dry = input("Dry run only? [y/N]: ").strip().lower() == "y"
    command = [
        sys.executable,
        str(TOOLS_DIR / "rerun_mission.py"),
        mission_dir.name,
    ]
    if dry:
        command.append("--dry-run")
    run_command(command)


def delete_planner_log():
    logs = read_sorted_logs()
    to_delete = prompt_multi_choice(
        logs, "No planner logs found.", title="Select planner logs to delete"
    )
    if not to_delete:
        return
    print("About to delete:")
    for path in to_delete:
        print(f" - {path.name}")
    confirm = input("Proceed? [y/N]: ").strip().lower() == "y"
    if confirm:
        for log_path in to_delete:
            log_path.unlink(missing_ok=True)
        print(f"Deleted {len(to_delete)} planner log(s).")


def delete_mission():
    missions = [p for p in read_sorted_directories(MISSIONS_DIR) if p.name != "_planner_logs"]
    to_delete = prompt_multi_choice(
        missions, "No completed missions found.", title="Select missions to delete"
    )
    if not to_delete:
        return
    print("About to delete:")
    for mission_dir in to_delete:
        print(f" - {mission_dir.name}")
    confirm = input("Proceed? [y/N]: ").strip().lower() == "y"
    if confirm:
        for mission_dir in to_delete:
            shutil.rmtree(mission_dir, ignore_errors=True)
        print(f"Deleted {len(to_delete)} mission(s).")


def configure_browser_mode():
    current_addr = ENV_OVERRIDES.get("CHROME_DEBUGGER_ADDRESS")
    statuses = get_debugger_statuses()
    text_lines = ["Debugger ports (ACTIVE vs available):"]
    text_lines.extend(format_debugger_lines(statuses, current_addr))
    mode_choice = choose_option(
        [
            ("auto", "Fully automatic (default)"),
            ("attach", "Attach to existing Chrome (requires debugger address)"),
            ("manual", "Launch Chrome and wait for manual confirmation each run"),
            ("back", "Back to main menu"),
        ],
        title="Browser Session Modes",
        text="\n".join(text_lines),
    )
    if mode_choice in (None, "back"):
        return
    if mode_choice == "auto":
        ENV_OVERRIDES.pop("CHROME_DEBUGGER_ADDRESS", None)
        ENV_OVERRIDES.pop("SELENIUM_DEBUGGER_ADDRESS", None)
        ENV_OVERRIDES.pop("SELENIUM_WAIT_FOR_USER", None)
        print("Browser mode set to automatic.")
    elif mode_choice == "attach":
        address = select_debugger_address(statuses)
        if not address:
            print("Debugger address required.")
            return
        ENV_OVERRIDES["CHROME_DEBUGGER_ADDRESS"] = address
        ENV_OVERRIDES.pop("SELENIUM_WAIT_FOR_USER", None)
        print(f"Browser mode set to attach to {address}.")
    elif mode_choice == "manual":
        ENV_OVERRIDES.pop("CHROME_DEBUGGER_ADDRESS", None)
        ENV_OVERRIDES.pop("SELENIUM_DEBUGGER_ADDRESS", None)
        ENV_OVERRIDES["SELENIUM_WAIT_FOR_USER"] = "1"
        print("Browser mode set to manual confirmation.")


def select_debugger_address(statuses):
    options = []
    for entry in statuses:
        marker = ""
        current_addr = ENV_OVERRIDES.get("CHROME_DEBUGGER_ADDRESS")
        if current_addr:
            if current_addr.endswith(str(entry["port"])) or current_addr == f"127.0.0.1:{entry['port']}":
                marker = " [SELECTED]"
        label = (
            f"Use 127.0.0.1:{entry['port']} ({'ACTIVE' if entry['active'] else 'available'}){marker}"
        )
        options.append((f"127.0.0.1:{entry['port']}", label))
    options.append(("custom", "Enter a custom debugger address"))
    choice = choose_option(options, title="Select debugger address")
    if choice is None:
        return None
    if choice == "custom" or not statuses:
        default_addr = ENV_OVERRIDES.get("CHROME_DEBUGGER_ADDRESS") or f"127.0.0.1:{DEFAULT_PORT}"
        return input(f"Enter debugger address [{default_addr}]: ").strip() or default_addr
    return choice


def main():
    ensure_directories()
    actions = [
        ("plan", "Plan mission from clue", plan_mission),
        ("planner", "Run planner log", run_planner_log),
        ("rerun", "Rerun existing mission", rerun_mission),
        ("del_logs", "Delete planner log", delete_planner_log),
        ("del_missions", "Delete mission", delete_mission),
        ("browser", "Configure browser session mode", configure_browser_mode),
        ("exit", "Exit", None),
    ]
    action_map = {key: handler for key, _, handler in actions}
    while True:
        print_debugger_summary()
        choice = choose_option([(key, label) for key, label, _ in actions], title="=== Mission Menu ===")
        if choice is None:
            continue
        if choice == "exit":
            print("Goodbye.")
            break
        handler = action_map.get(choice)
        if handler:
            handler()


if __name__ == "__main__":
    main()
