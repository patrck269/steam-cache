# Steam LAN cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve repeat Steam downloads from a Lancache virtual machine on the file server's RAID0 array, and withdraw that cache from DNS when port 80 stops answering.

**Architecture:** An Ubuntu Server virtual machine (2 vCPU, 4 GB, autostart) runs `lancachenet/monolithic` on port 80. Its cache disk is one fixed VHDX on the RAID0 stripe. The house router publishes one IPv4 record for `lancache.steamcontent.com` with a 10-second TTL, and a port-80 probe every 10 seconds removes or restores that record. Decision logic lives in `src/lancache_plan.py` and is tested without the router. Live host names and addresses stay in gitignored `local.md` and `deploy.local.json`.

**Tech Stack:** Python 3 unittest, Hyper-V, Ubuntu Server cloud image, Docker, Lancache monolithic, RouterOS 7 netwatch.

**Spec:** `docs/superpowers/specs/2026-11-09-steam-lancache-design.md`

## Global Constraints

- Virtual machine: Ubuntu Server, 2 vCPU, 4 GB RAM, starts with the host.
- Listener: `lancachenet/monolithic` on port 80 only, unless a Steam download stalls on port 443, in which case add a pass-through that does not store bytes.
- Cache disk: one fixed VHDX on the RAID0 array. `CACHE_DISK_SIZE` is just under that disk.
- DNS: one IPv4 `A` record for `lancache.steamcontent.com`, TTL 10 seconds. No IPv6 record. No other launcher name.
- Health: probe port 80 every 10 seconds. Down withdraws the name. Up restores it.
- SMB: after the external switch, an 8 GiB copy to the RAID0 array and back must sit in the write and read ranges in `local.md`. If it does not, remove the switch and stop.
- Do not commit `local.md` or `deploy.local.json`.

## File structure

- `src/lancache_plan.py` owns cache-size, DNS record, RouterOS script text, compose text, and the SMB range check.
- `deploy/apply_dns.py` turns those scripts into RouterOS commands and applies them over `ssh router`.
- `tests/test_lancache_plan.py` drives both modules.
- `deploy.local.json` (gitignored) holds the VHDX size, paths, and the virtual machine address once it exists.
- `local.md` (gitignored) records the same facts in prose, including the image digest.

---

### Task 1: Decision logic

**Files:**
- Create: `src/lancache_plan.py`
- Create: `deploy/apply_dns.py`
- Test: `tests/test_lancache_plan.py`

**Interfaces:**
- Consumes: nothing
- Produces: `cache_disk_size_g(vhdx_bytes) -> str`, `desired_record(port80_up, ipv4) -> dict | None`, `routeros_down_script()`, `routeros_up_script(ipv4)`, `compose_yaml(image_ref, cache_disk_size)`, `rates_inside(...)`, `netwatch_commands(ipv4) -> list`

- [ ] **Step 1: Write the tests in `tests/test_lancache_plan.py`**

The tests assert: a 2 TiB disk caps at `1843g`; port 80 up yields one `A` record with `ttl=10s` for `192.0.2.50`; port 80 down yields `None`; an IPv6 address raises `ValueError`; the virtual machine is 2 vCPU and 4096 MB and listens on port 80; the health interval is 10 seconds; netwatch uses `type=tcp-conn`, `port=80`, `interval=10s`; compose publishes `80:80` and `CACHE_DISK_SIZE` and does not mention 443; SMB rates 710–724 write and 630–640 read are inside, and 709 or 629 are outside.

- [ ] **Step 2: Run the tests and confirm they fail before the functions exist**

Run from the repo root: `python -m unittest tests.test_lancache_plan -v`

- [ ] **Step 3: Implement `src/lancache_plan.py` and `deploy/apply_dns.py`**

`cache_disk_size_g` returns ninety percent of the disk in whole gibibytes, always at least 1 GiB under the disk. `desired_record` returns `None` when port 80 is down and refuses anything that is not dotted IPv4. Scripts name only `lancache.steamcontent.com`. `netwatch_commands` installs `lancache-down` and `lancache-up`, adds a tcp-conn netwatch, then runs the up script once.

- [ ] **Step 4: Re-run the tests**

Run: `python -m unittest tests.test_lancache_plan -v`
Expected: all tests pass.

- [ ] **Step 5: Commit the tests and the modules**

```
git add src/lancache_plan.py deploy/apply_dns.py tests/test_lancache_plan.py docs/superpowers/plans/2026-11-09-steam-lancache.md .gitignore
git commit -m "feat: add lancache dns and cache-size decisions"
```

### Task 2: Record the RAID0 size

**Files:**
- Modify: `local.md` (gitignored)
- Create: `deploy.local.json` (gitignored)

- [ ] **Step 1: Read free space on the stripe volume**

The RAID0 array is the dynamic stripe volume, not the PERC simple volume. Record its free bytes.

- [ ] **Step 2: Choose the fixed VHDX**

Use a 2 TiB fixed VHDX (`2199023255552` bytes). That leaves the bytes already stored on the stripe in place and leaves the rest of the free space as reserve. `cache_disk_size_g(2199023255552)` is `1843g`. Write both numbers into `local.md` and `deploy.local.json`.

- [ ] **Step 3: Do not commit those files**

`git status` must show them untracked or ignored.

### Task 3: Hyper-V external switch and SMB gate

**Files:**
- Live host only. No repo file receives an address.

- [ ] **Step 1: Measure an 8 GiB copy to the stripe and back before the switch**

Write the byte rates down. This is the control, not the gate.

- [ ] **Step 2: Enable the Hyper-V platform and reboot the file server**

The platform feature is disabled. Enabling it reboots the server. Docker Desktop's WSL virtual machines come back with the host.

- [ ] **Step 3: Create the external switch on the 10G adapter with a scheduled task**

The task creates the switch, gives the management adapter the host's existing IPv4 address, prefix, gateway, and DNS, and sets jumbo frames to 9014. The task logs to a file on the host. SSH will drop while the switch binds. Wait until SSH returns on the same address.

- [ ] **Step 4: Re-apply the SMB multichannel constraint if the selected path left the 10G client adapter**

The client constraint names the server and the 10G adapter. Keep that constraint. If the server name no longer selects that adapter, put it back.

- [ ] **Step 5: Copy 8 GiB to the stripe and back**

Pass only when `rates_inside` is true for the ranges in `local.md` (write 710 through 724, read 630 through 640). If either direction is outside, remove the virtual switch, restore the physical adapter's address, and stop. Do not treat later checks as success.

### Task 4: Virtual machine and Lancache

**Files:**
- Modify: `local.md` with the image digest and the virtual machine address

- [ ] **Step 1: Create the autostart virtual machine**

2 vCPU, 4096 MB, generation 2, automatic start, automatic stop as shutdown. OS disk is a cloud image converted to VHDX on the SSD. Cache disk is the fixed VHDX from Task 2 on the stripe. A NoCloud seed sets the hostname, installs Docker, formats the cache disk, and mounts it at `/data`.

- [ ] **Step 2: DHCP reservation**

When the lease appears, make it static on the router so the address stays put. Record the address in `deploy.local.json` as `vm_ipv4` and in `local.md`.

- [ ] **Step 3: Run Lancache**

Pull `lancachenet/monolithic`, record `docker image inspect` RepoDigests into `local.md`, and start the compose file from `compose_yaml` with `CACHE_DISK_SIZE` from `cache_disk_size_g`. Confirm port 80 answers inside the virtual machine.

### Task 5: Router record

**Files:**
- Uses `deploy/apply_dns.py`

- [ ] **Step 1: Apply `netwatch_commands` for `vm_ipv4`**

Run `python -m deploy.apply_dns` from the repo root.

- [ ] **Step 2: Query the name through the house router**

The answer is only the virtual machine IPv4 address. No AAAA.

### Task 6: Live gates

- [ ] **Step 1: DNS failover**

Query, stop port 80, wait 10 seconds, query, start port 80, query. Save all three to the scratch `dns-failover.txt`.

- [ ] **Step 2: Miss then hit**

Request one Steam content URL twice. The first fetch is upstream and grows the cache disk. The second is served from the cache with no second upstream fetch. Save logs to scratch `cache-miss-hit.txt`, including the digest line from `local.md`.

- [ ] **Step 3: SMB gate capture**

Save the post-switch copy rates to scratch `smb-copy.txt`.

- [ ] **Step 4: Steam**

On the gaming PC, with encrypted DNS not bypassing the router, restart Steam and capture `Enabling local content cache` for the virtual machine address. Install one uncached game, record growth and throughput, remove it, install it again, and record that the second install is faster and that Lancache does not fetch it upstream again. Repeat the cached install from one other LAN PC. Confirm one non-Steam launcher still reaches the internet. Save this to scratch `steam-install.txt`. If Steam cannot be driven, write that failure in the capture and leave the gate unmet. Do not invent a log line.

- [ ] **Step 5: Commit and status**

Commit the plan and the non-secret modules. Save `git status` to scratch `git-status.txt`. `local.md` must not be staged.
