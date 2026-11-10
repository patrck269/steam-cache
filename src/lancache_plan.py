"""Decisions for the Steam LAN cache that can be tested without the live router."""

RECORD_NAME = "lancache.steamcontent.com"
RECORD_TTL = "10s"
HEALTH_INTERVAL_S = 10
VM_VCPU = 2
VM_RAM_MB = 4096
LISTEN_PORT = 80
GIB = 1024 ** 3


def cache_disk_size_g(vhdx_bytes: int) -> str:
    """Nginx max size, in gibibytes, just under the fixed VHDX.

    Ninety percent of the disk, and always at least one gibibyte under it,
    so Lancache evicts before the filesystem fills.
    """
    if vhdx_bytes < 2 * GIB:
        raise ValueError("VHDX must be at least 2 GiB")
    gib = vhdx_bytes // GIB
    sized = int(gib * 9 / 10)
    if sized >= gib:
        sized = gib - 1
    if sized < 1:
        raise ValueError("VHDX leaves no room for a cache cap")
    return f"{sized}g"


def desired_record(port80_up: bool, ipv4: str):
    """The single IPv4 record to publish, or None when port 80 is down."""
    if not port80_up:
        return None
    _require_ipv4(ipv4)
    return {
        "name": RECORD_NAME,
        "type": "A",
        "address": ipv4,
        "ttl": RECORD_TTL,
    }


def routeros_down_script() -> str:
    """Withdraw only the cache name. Leave every other static record alone."""
    return (
        ":foreach i in=[/ip dns static find where name="
        "lancache.steamcontent.com] do={ /ip dns static remove $i }"
    )


def compose_yaml(image_ref: str, cache_disk_size: str) -> str:
    """Lancache compose file. Port 80 only. The image ref is pinned by the caller."""
    if not cache_disk_size.endswith("g") or not cache_disk_size[:-1].isdigit():
        raise ValueError("cache disk size must look like 1843g")
    if image_ref == "" or any(char in image_ref for char in " \n\r\t"):
        raise ValueError("bad image ref")
    return (
        "services:\n"
        "  monolithic:\n"
        f"    image: {image_ref}\n"
        "    restart: unless-stopped\n"
        "    ports:\n"
        '      - "80:80"\n'
        "    environment:\n"
        f"      CACHE_DISK_SIZE: {cache_disk_size}\n"
        "      CACHE_MEM_SIZE: 500m\n"
        "    volumes:\n"
        "      - /data/cache:/data/cache\n"
        "      - /data/logs:/data/logs\n"
    )


def routeros_up_script(ipv4: str) -> str:
    """Replace any existing cache record with one A record, TTL 10s."""
    record = desired_record(True, ipv4)
    return (
        routeros_down_script()
        + "; /ip dns static add name="
        + record["name"]
        + " type=A address="
        + record["address"]
        + " ttl="
        + record["ttl"]
    )


def rates_inside(write_mb_s, read_mb_s, write_min, write_max, read_min, read_max) -> bool:
    """True when both copy directions sit inside the recorded baseline."""
    return (
        write_min <= write_mb_s <= write_max
        and read_min <= read_mb_s <= read_max
    )


def _require_ipv4(ipv4: str) -> None:
    parts = ipv4.split(".")
    if len(parts) != 4:
        raise ValueError("IPv4 only")
    for part in parts:
        if not part.isdigit():
            raise ValueError("IPv4 only")
        number = int(part)
        if number > 255 or (len(part) > 1 and part.startswith("0")):
            raise ValueError("IPv4 only")
