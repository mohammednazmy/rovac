"""Pytest coverage for the direct-I2C LED driver (sense_hat_direct).

These tests stub smbus2 so they run on any machine — they verify the
I2C transaction shape (one 193-byte write per frame, register 0x00,
correct 5-bit channel packing), not actual hardware behavior.

Hardware-touching parts (real chip on real I2C bus) are tested
implicitly when the systemd service runs and lights up the LEDs.
"""
from __future__ import annotations

import os
import sys
import types
from typing import List

import pytest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))


@pytest.fixture
def fake_bus(monkeypatch):
    """Stub smbus2 so we can capture i2c_rdwr calls without real hardware."""
    edge_dir = os.path.join(REPO_ROOT, "scripts", "edge")
    monkeypatch.syspath_prepend(edge_dir)

    captured: List[dict] = []

    class _FakeMsg:
        def __init__(self, kind: str, addr: int, data):
            self.kind = kind
            self.addr = addr
            self.data = list(data)

        def __iter__(self):
            return iter(self.data)

    class _FakeMsgFactory:
        @staticmethod
        def write(addr, data):
            return _FakeMsg("write", addr, data)

        @staticmethod
        def read(addr, length):
            # Pre-fill with an identifying sentinel so read tests can
            # introspect what was returned. The chip's WAI byte is 0x73
            # — return that for register-read tests of register 0xF0.
            msg = _FakeMsg("read", addr, [0x73] * length)
            return msg

    class _FakeBus:
        def __init__(self, bus_num):
            self.bus_num = bus_num

        def i2c_rdwr(self, *msgs):
            for m in msgs:
                captured.append({
                    "kind": m.kind,
                    "addr": m.addr,
                    "data": list(m.data),
                    "len": len(m.data),
                })

        def close(self):
            pass

    fake_module = types.ModuleType("smbus2")
    fake_module.SMBus = _FakeBus  # type: ignore
    fake_module.i2c_msg = _FakeMsgFactory  # type: ignore
    monkeypatch.setitem(sys.modules, "smbus2", fake_module)

    sys.modules.pop("sense_hat_direct", None)
    import sense_hat_direct  # noqa: E402
    return sense_hat_direct, captured


class TestInit:
    def test_init_reads_wai_register(self, fake_bus):
        mod, captured = fake_bus
        led = mod.SenseHatDirect()
        # First two transactions are the WAI read: write [0xF0], read 1 byte
        assert captured[0]["kind"] == "write"
        assert captured[0]["data"] == [mod.REG_WAI]
        assert captured[1]["kind"] == "read"
        led.close()

    def test_init_raises_if_wai_mismatch(self, monkeypatch, fake_bus):
        mod, _ = fake_bus
        # Force the read to return wrong WAI by patching the read msg
        # factory used by the module after import.
        sys.modules.pop("sense_hat_direct", None)

        # Build a custom smbus2 that returns 0xAA on every read.
        class _BadMsg:
            def __init__(self, kind, addr, data):
                self.kind = kind
                self.addr = addr
                self.data = list(data)

            def __iter__(self):
                return iter(self.data)

        class _BadFactory:
            @staticmethod
            def write(addr, data):
                return _BadMsg("write", addr, data)

            @staticmethod
            def read(addr, length):
                return _BadMsg("read", addr, [0xAA] * length)

        class _BadBus:
            def __init__(self, n): pass
            def i2c_rdwr(self, *msgs): pass
            def close(self): pass

        bad = types.ModuleType("smbus2")
        bad.SMBus = _BadBus  # type: ignore
        bad.i2c_msg = _BadFactory  # type: ignore
        monkeypatch.setitem(sys.modules, "smbus2", bad)
        sys.modules.pop("sense_hat_direct", None)
        import sense_hat_direct as bad_mod
        with pytest.raises(RuntimeError, match="WAI"):
            bad_mod.SenseHatDirect()


class TestSetPixels:
    def test_writes_193_byte_transaction(self, fake_bus):
        mod, captured = fake_bus
        led = mod.SenseHatDirect()
        captured.clear()
        led.set_pixels([(0, 0, 0)] * 64)
        # Exactly one transaction: a write.
        assert len(captured) == 1
        assert captured[0]["kind"] == "write"
        # 1 register byte + 192 pixel bytes
        assert captured[0]["len"] == 193
        # First byte is the LED data register.
        assert captured[0]["data"][0] == mod.REG_DISPLAY == 0x00

    def test_pixel_data_is_5bit_packed(self, fake_bus):
        """255 → 31 (0x1F), 128 → 16 (0x10), 0 → 0."""
        mod, captured = fake_bus
        led = mod.SenseHatDirect()
        captured.clear()
        led.set_pixels([(255, 128, 0)] + [(0, 0, 0)] * 63)
        data = captured[0]["data"]
        # data[0] is register 0x00; pixel 0 starts at data[1]
        assert data[1] == 0x1F   # R=255 → 31
        assert data[2] == 0x10   # G=128 → 16
        assert data[3] == 0x00   # B=0 → 0

    def test_clear_is_all_zeros(self, fake_bus):
        mod, captured = fake_bus
        led = mod.SenseHatDirect()
        captured.clear()
        led.clear()
        assert captured[0]["data"] == [0x00] + [0] * 192

    def test_rejects_wrong_length(self, fake_bus):
        mod, _ = fake_bus
        led = mod.SenseHatDirect()
        with pytest.raises(ValueError):
            led.set_pixels([(0, 0, 0)] * 32)

    def test_high_bits_are_masked(self, fake_bus):
        """Channel values above 255 get masked to lower 5 bits after >>3."""
        mod, captured = fake_bus
        led = mod.SenseHatDirect()
        captured.clear()
        # 256 >> 3 = 32 = 0x20, but masked to 0x1F = 31
        led.set_pixels([(256, 0, 0)] + [(0, 0, 0)] * 63)
        data = captured[0]["data"]
        assert data[1] == 0x00   # 256 >> 3 = 32, & 0x1F = 0


class TestRegisterAddresses:
    def test_constants_match_hardware(self, fake_bus):
        mod, _ = fake_bus
        assert mod.I2C_ADDR == 0x46
        assert mod.REG_DISPLAY == 0x00
        assert mod.REG_WAI == 0xF0
        assert mod.REG_JOYSTICK == 0xF2
        assert mod.WAI_VALUE == 0x73   # ASCII 's'
