# Steam LAN cache

Date: 2026-11-09. Status: approved, not implemented.

Steam installs on the house LAN come from a cache on the Windows file server once the bytes have been fetched. The first download still comes from Steam, through the cache, at internet speed. A later download of the same content is served from the file server's RAID0 array.

## Decisions

The cache stores Steam's download stream. It does not store a copy of an installed game folder.

On a miss, the cache fetches the pieces from Steam and passes them to the client. On a hit, the client receives them from the array.

The cache runs on the Windows file server. Its disk is a fixed VHDX on that server's RAID0 array.

Every machine on the LAN can use it. The house router is the only DNS server those machines use. The router answers one name, `lancache.steamcontent.com`, with the cache address. No other launcher is redirected.

When the cache stops answering, the router stops answering that name. Steam then uses the internet.

The cache is Lancache's monolithic container, inside an Ubuntu Server virtual machine. A new cache program is out of scope.

Host names, addresses, the disk path, and the SMB baseline live in `local.md` at the repo root. That file is gitignored.

## Architecture

A small Ubuntu Server virtual machine on the file server runs Lancache. The virtual machine has 2 vCPU and 4 GB of RAM, and it starts with the host. Its disk is one fixed VHDX on the RAID0 array. It has its own DHCP reservation, so its address stays put.

The virtual machine is attached through a Hyper-V external switch on the file server's 10G adapter. The host keeps its own address and remains the file server. The host's SMB multichannel pin moves to the new virtual adapter. That copy path is measured again before the cache is trusted.

The link to this server tops out near 7 Gbit/s. The hard-drive array may come in under that once the cache is a large tree of slice files. Repeat downloads run at whatever those two can sustain.

The router holds one IPv4 record for `lancache.steamcontent.com`, with a 10-second time-to-live, pointing at the virtual machine. There is no IPv6 record, and there is no second DNS server.

Before the VHDX is created, free space on the array is read. A reserve stays for the media already stored there. The operator confirms the reserve and the VHDX size before the disk is created. Lancache's `CACHE_DISK_SIZE` is set just under the VHDX. When the cap is hit, Lancache drops the least recently used pieces.

A dead disk in the RAID0 array wipes the cache. Steam still has the games. The cache is not backed up.

## Data flow

A Steam client looks up `lancache.steamcontent.com` through the router. If the name resolves to the virtual machine, Steam enables its local content cache, connects to that address over HTTP, and raises its connection limit. The requests carry the real content-server name in the Host header.

Lancache serves a piece from disk when it has it. Otherwise it fetches the piece from Steam, stores it, and serves it. Two clients asking for the same missing piece cause one upstream fetch.

If the name does not resolve, Steam downloads from the internet and the cache stores nothing.

The image is `lancachenet/monolithic`, pinned to the digest from the day it is first deployed. That digest is recorded in `local.md`. The virtual machine listens on port 80.

## Failure

The router checks port 80 on the virtual machine every 10 seconds. While the check fails, the router withdraws `lancache.steamcontent.com`. New lookups use the internet. When port 80 answers again, the router puts the record back.

A Steam client that already found the cache can keep the old address until that download errors or Steam is restarted. That window is the limit of a DNS health check.

If the DHCP reservation is lost, the health check fails against the old address and the router withdraws the name. Steam keeps using the internet until the record points at the new address.

The size cap is what keeps a full disk from breaking downloads. If the array fails, port 80 stops and the router withdraws the name. Later downloads fill a new cache.

A bad piece already in the cache is different. Port 80 still answers, so the router keeps sending Steam there, and the download retries that piece. Delete the piece and let the next download fetch it again.

A PC that does not use the router for DNS never sees the cache. Its downloads come from the internet and do not fill the cache. Encrypted DNS on a PC does the same.

The virtual machine listens on port 80 only. If a test download stalls while connecting to port 443 on the virtual machine, add a pass-through on 443 that forwards the encrypted traffic and does not store it.

## Testing

The tests run in this order. The cache is not trusted until they pass.

1. After the 10G adapter moves onto the virtual switch and the SMB pin is on the new adapter, copy a large file to the RAID0 array and back. Both directions stay in the range recorded in `local.md`. If they fall off, remove the switch and stop.
2. From the gaming PC, through the router, `lancache.steamcontent.com` returns only the virtual machine's IPv4 address. Stopping the virtual machine, or closing port 80, makes the router drop the name within the health-check interval. Starting the virtual machine puts the name back.
3. With the cache up, a restarted Steam client logs `Enabling local content cache` for that address. Installing a game that is not cached runs at internet speed, and the cache disk grows by about that game's size. Removing it and installing it again comes from the array, well above the internet line, and the cache does not fetch the game a second time.
4. One other PC on the LAN repeats that second install and gets the same result. A launcher other than Steam still reaches the internet.
5. The gaming PC is checked for encrypted DNS. If it bypasses the router, turn that off or repeat the Steam test after it is off.

## Out of scope

Other game launchers, pre-filling a library, a Windows-native cache program, and backups of the cache.
