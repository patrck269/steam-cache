"""Apply the cache DNS record on the house router from a local JSON file.

The file is gitignored. It must contain vm_ipv4. This script shells out to
ssh only when run as a program. Tests import the command builder.
"""

import json
import subprocess
import sys
from pathlib import Path

from src.lancache_plan import (
    HEALTH_INTERVAL_S,
    LISTEN_PORT,
    RECORD_NAME,
    desired_record,
    routeros_down_script,
    routeros_up_script,
)

ROOT = Path(__file__).resolve().parents[1]
LOCAL_JSON = ROOT / "deploy.local.json"


def netwatch_commands(ipv4: str) -> list:
    record = desired_record(True, ipv4)
    if record is None:
        raise ValueError("refusing to install a watch with no address")
    down = routeros_down_script()
    up = routeros_up_script(ipv4)
    # RouterOS expands $ while it stores a script. Keep the loop variable for later.
    stored_down = down.replace("$", "\\$")
    stored_up = up.replace("$", "\\$")
    return [
        ":foreach i in=[/system script find where name=lancache-down] do={ /system script remove $i }",
        ":foreach i in=[/system script find where name=lancache-up] do={ /system script remove $i }",
        ":foreach i in=[/tool netwatch find where name=lancache-http] do={ /tool netwatch remove $i }",
        f'/system script add name=lancache-down source="{stored_down}"',
        f'/system script add name=lancache-up source="{stored_up}"',
        (
            "/tool netwatch add name=lancache-http "
            f"host={ipv4} type=tcp-conn port={LISTEN_PORT} "
            f"interval={HEALTH_INTERVAL_S}s timeout=3s "
            'down-script="/system script run lancache-down" '
            'up-script="/system script run lancache-up"'
        ),
        "/system script run lancache-up",
    ]


def load_vm_ipv4(path: Path = LOCAL_JSON) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    ipv4 = data["vm_ipv4"]
    desired_record(True, ipv4)
    return ipv4


def main() -> int:
    ipv4 = load_vm_ipv4()
    for command in netwatch_commands(ipv4):
        print(command, flush=True)
        result = subprocess.run(
            ["ssh", "router", command],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.stdout:
            print(result.stdout, end="" if result.stdout.endswith("\n") else "\n", flush=True)
        if result.stderr:
            print(result.stderr, end="" if result.stderr.endswith("\n") else "\n", file=sys.stderr, flush=True)
        combined = f"{result.stdout}\n{result.stderr}".lower()
        if result.returncode != 0 or "syntax error" in combined or "no such item" in combined or "failure:" in combined:
            print(f"router command failed ({result.returncode})", file=sys.stderr, flush=True)
            return 1
    print(f"published {RECORD_NAME} -> {ipv4}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
