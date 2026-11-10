import unittest

from deploy.apply_dns import netwatch_commands
from src.lancache_plan import (
    HEALTH_INTERVAL_S,
    LISTEN_PORT,
    VM_RAM_MB,
    VM_VCPU,
    cache_disk_size_g,
    compose_yaml,
    desired_record,
    rates_inside,
    routeros_down_script,
    routeros_up_script,
)


class CacheSizeTests(unittest.TestCase):
    def test_two_tebibyte_disk_is_capped_under_the_disk(self):
        self.assertEqual(cache_disk_size_g(2 * 1024**4), "1843g")

    def test_cap_is_always_one_gibibyte_under_a_small_disk(self):
        self.assertEqual(cache_disk_size_g(2 * 1024**3), "1g")

    def test_rejects_a_disk_too_small_to_cap(self):
        with self.assertRaises(ValueError):
            cache_disk_size_g(1024**3)


class DnsRecordTests(unittest.TestCase):
    def test_up_publishes_one_a_record_with_ten_second_ttl(self):
        record = desired_record(True, "192.0.2.50")
        self.assertEqual(
            record,
            {
                "name": "lancache.steamcontent.com",
                "type": "A",
                "address": "192.0.2.50",
                "ttl": "10s",
            },
        )

    def test_down_withdraws_the_record(self):
        self.assertIsNone(desired_record(False, "192.0.2.50"))

    def test_rejects_ipv6(self):
        with self.assertRaises(ValueError):
            desired_record(True, "2001:db8::1")

    def test_health_interval_and_vm_shape(self):
        self.assertEqual(HEALTH_INTERVAL_S, 10)
        self.assertEqual(VM_VCPU, 2)
        self.assertEqual(VM_RAM_MB, 4096)
        self.assertEqual(LISTEN_PORT, 80)


class RouterosScriptTests(unittest.TestCase):
    def test_down_script_removes_only_the_cache_name(self):
        script = routeros_down_script()
        self.assertIn("name=lancache.steamcontent.com", script)
        self.assertNotIn("192.0.2.50", script)
        self.assertIn("remove", script)
        self.assertNotIn('"', script)

    def test_netwatch_probes_port_80_every_ten_seconds(self):
        commands = netwatch_commands("192.0.2.50")
        watch = next(command for command in commands if command.startswith("/tool netwatch add"))
        self.assertIn("type=tcp-conn", watch)
        self.assertIn("port=80", watch)
        self.assertIn("interval=10s", watch)
        self.assertIn("host=192.0.2.50", watch)
        self.assertNotIn("AAAA", "\n".join(commands))

    def test_compose_listens_on_port_80_only(self):
        text = compose_yaml("lancachenet/monolithic@sha256:abc", "1843g")
        self.assertIn('      - "80:80"', text)
        self.assertIn("CACHE_DISK_SIZE: 1843g", text)
        self.assertNotIn("443", text)

    def test_up_script_writes_a_ten_second_a_record(self):
        script = routeros_up_script("192.0.2.50")
        self.assertIn("type=A", script)
        self.assertIn("address=192.0.2.50", script)
        self.assertIn("ttl=10s", script)
        self.assertNotIn("AAAA", script)


class SmbBaselineTests(unittest.TestCase):
    def test_baseline_band_accepts_its_edges(self):
        self.assertTrue(rates_inside(710, 630, 710, 724, 630, 640))
        self.assertTrue(rates_inside(724, 640, 710, 724, 630, 640))

    def test_baseline_band_rejects_a_drop(self):
        self.assertFalse(rates_inside(709, 635, 710, 724, 630, 640))
        self.assertFalse(rates_inside(715, 629, 710, 724, 630, 640))


if __name__ == "__main__":
    unittest.main()
