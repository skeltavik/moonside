#!/usr/bin/env python3
"""
Moonside BLE Protocol Test Script

This script tests the reverse-engineered BLE protocol for Moonside lights
without requiring Home Assistant. Run this first to verify communication
before installing the integration.

Requirements:
    pip install bleak

Usage:
    python test_moonside.py
    python test_moonside.py --mac XX:XX:XX:XX:XX:XX
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import Any

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

# Setup logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
LOGGER = logging.getLogger(__name__)

# Constants from reverse engineering
UART_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
UART_RX_CHAR_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
UART_TX_CHAR_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

# Test commands
CMD_LED_ON = "LEDON"
CMD_LED_OFF = "LEDOFF"
CMD_BRIGHTNESS = "BRIGH"
CMD_COLOR = "COLOR"
CMD_PIXEL = "PIXEL"
CMD_MODE_PIXEL = "MODEPIXEL"


class MoonsideTester:
    """Test class for Moonside BLE communication."""

    def __init__(self, mac_address: str):
        self.mac_address = mac_address
        self.client: BleakClient | None = None
        self.rx_char: BleakGATTCharacteristic | None = None
        self.tx_char: BleakGATTCharacteristic | None = None
        self.responses: list[bytes] = []

    async def discover(self, timeout: float = 10.0) -> list[tuple[str, str]]:
        """Discover Moonside devices."""
        LOGGER.info("🔍 Scanning for Moonside devices...")
        devices_found: list[tuple[str, str]] = []

        def device_found(device: BLEDevice, adv: AdvertisementData) -> None:
            name = adv.local_name or device.name
            if name and "MOONSIDE" in name.upper():
                LOGGER.info(f"  Found: {name} ({device.address})")
                devices_found.append((device.address, name))

        scanner = BleakScanner(
            detection_callback=device_found,
            service_uuids=[UART_SERVICE_UUID],
        )

        await scanner.start()
        await asyncio.sleep(timeout)
        await scanner.stop()

        return devices_found

    async def connect(self) -> bool:
        """Connect to the Moonside device."""
        LOGGER.info(f"🔗 Connecting to {self.mac_address}...")

        try:
            self.client = BleakClient(self.mac_address)
            await self.client.connect()

            if not self.client.is_connected:
                LOGGER.error("❌ Failed to connect")
                return False

            LOGGER.info("✅ Connected!")

            # Get UART service and characteristics
            service = self.client.services.get_service(UART_SERVICE_UUID)
            if not service:
                LOGGER.error(f"❌ UART service not found (UUID: {UART_SERVICE_UUID})")
                return False

            self.rx_char = service.get_characteristic(UART_RX_CHAR_UUID)
            self.tx_char = service.get_characteristic(UART_TX_CHAR_UUID)

            if not self.rx_char:
                LOGGER.error(
                    f"❌ RX characteristic not found (UUID: {UART_RX_CHAR_UUID})"
                )
                return False

            if not self.tx_char:
                LOGGER.error(
                    f"❌ TX characteristic not found (UUID: {UART_TX_CHAR_UUID})"
                )
                return False

            LOGGER.info("✅ UART characteristics found")
            LOGGER.info(f"   RX: {self.rx_char.uuid}")
            LOGGER.info(f"   TX: {self.tx_char.uuid}")

            # Setup notification handler
            await self.client.start_notify(self.tx_char, self._notification_handler)
            LOGGER.info("✅ Notifications enabled")

            return True

        except Exception as e:
            LOGGER.error(f"❌ Connection error: {e}")
            return False

    def _notification_handler(
        self, sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        """Handle incoming notifications."""
        LOGGER.info(f"📩 Received: {data}")
        self.responses.append(bytes(data))

    async def send_command(
        self, command: str, wait_for_response: bool = False, timeout: float = 2.0
    ) -> bool:
        """Send a command to the device."""
        if not self.client or not self.client.is_connected:
            LOGGER.error("❌ Not connected")
            return False

        try:
            data = command.encode("utf-8")
            LOGGER.info(f"📤 Sending: {command}")

            await self.client.write_gatt_char(self.rx_char, data, response=False)

            # Wait a bit for command processing
            await asyncio.sleep(0.1)

            if wait_for_response:
                LOGGER.info(f"⏳ Waiting {timeout}s for response...")
                await asyncio.sleep(timeout)

            return True

        except Exception as e:
            LOGGER.error(f"❌ Error sending command: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        if self.client and self.client.is_connected:
            await self.client.disconnect()
            LOGGER.info("🔌 Disconnected")

    async def run_tests(self) -> dict[str, Any]:
        """Run all protocol tests."""
        results = {
            "connection": False,
            "led_on": False,
            "led_off": False,
            "brightness": False,
            "color_red": False,
            "color_green": False,
            "color_blue": False,
            "theme": False,
            "pixel": False,
            "errors": [],
        }

        # Test 1: Connection
        if not await self.connect():
            results["errors"].append("Connection failed")
            return results
        results["connection"] = True

        try:
            # Test 2: LED ON
            LOGGER.info("\n" + "=" * 50)
            LOGGER.info("TEST 1: LED ON")
            LOGGER.info("=" * 50)
            input("💡 Press ENTER to turn LED ON...")
            if await self.send_command(CMD_LED_ON, wait_for_response=True):
                results["led_on"] = True
                LOGGER.info("✅ LED ON command sent")
            else:
                results["errors"].append("LED ON failed")

            # Test 3: Brightness
            LOGGER.info("\n" + "=" * 50)
            LOGGER.info("TEST 2: Brightness (50%)")
            LOGGER.info("=" * 50)
            input("💡 Press ENTER to set brightness to 50%...")
            brightness_cmd = f"{CMD_BRIGHTNESS}060"  # 60/120 = 50%
            if await self.send_command(brightness_cmd, wait_for_response=True):
                results["brightness"] = True
                LOGGER.info("✅ Brightness command sent")
            else:
                results["errors"].append("Brightness failed")

            # Test 4: Color - RED
            LOGGER.info("\n" + "=" * 50)
            LOGGER.info("TEST 3: Color RED")
            LOGGER.info("=" * 50)
            input("💡 Press ENTER to set color to RED...")
            color_cmd = f"{CMD_COLOR}255000000"
            await self.send_command(color_cmd)
            brightness_cmd = f"{CMD_BRIGHTNESS}060"
            if await self.send_command(brightness_cmd, wait_for_response=True):
                results["color_red"] = True
                LOGGER.info("✅ Red color command sent")
            else:
                results["errors"].append("Color RED failed")

            # Test 5: Color - GREEN
            LOGGER.info("\n" + "=" * 50)
            LOGGER.info("TEST 4: Color GREEN")
            LOGGER.info("=" * 50)
            input("💡 Press ENTER to set color to GREEN...")
            color_cmd = f"{CMD_COLOR}000255000"
            await self.send_command(color_cmd)
            brightness_cmd = f"{CMD_BRIGHTNESS}060"
            if await self.send_command(brightness_cmd, wait_for_response=True):
                results["color_green"] = True
                LOGGER.info("✅ Green color command sent")
            else:
                results["errors"].append("Color GREEN failed")

            # Test 6: Color - BLUE
            LOGGER.info("\n" + "=" * 50)
            LOGGER.info("TEST 5: Color BLUE")
            LOGGER.info("=" * 50)
            input("💡 Press ENTER to set color to BLUE...")
            color_cmd = f"{CMD_COLOR}000000255"
            await self.send_command(color_cmd)
            brightness_cmd = f"{CMD_BRIGHTNESS}060"
            if await self.send_command(brightness_cmd, wait_for_response=True):
                results["color_blue"] = True
                LOGGER.info("✅ Blue color command sent")
            else:
                results["errors"].append("Color BLUE failed")

            # Test 7: Theme
            LOGGER.info("\n" + "=" * 50)
            LOGGER.info("TEST 6: Theme (Rainbow)")
            LOGGER.info("=" * 50)
            input("💡 Press ENTER to activate RAINBOW effect...")
            theme_cmd = "THEME.RAINBOW1.20,"
            if await self.send_command(theme_cmd, wait_for_response=True):
                results["theme"] = True
                LOGGER.info("✅ Theme command sent")
            else:
                results["errors"].append("Theme failed")

            # Test 8: Pixel
            LOGGER.info("\n" + "=" * 50)
            LOGGER.info("TEST 7: Individual Pixel")
            LOGGER.info("=" * 50)
            input("💡 Press ENTER to test individual pixel (first 5 pixels)...")

            # Turn off first
            await self.send_command(CMD_LED_OFF)
            await asyncio.sleep(0.5)

            # Set pixels
            for i in range(5):
                pixel_cmd = f"{CMD_PIXEL},{i},120"  # Pixel 0-4 at max brightness
                await self.send_command(pixel_cmd)
                await asyncio.sleep(0.1)

            # Apply
            if await self.send_command(CMD_MODE_PIXEL, wait_for_response=True):
                results["pixel"] = True
                LOGGER.info("✅ Pixel commands sent")
            else:
                results["errors"].append("Pixel failed")

            # Test 9: LED OFF
            LOGGER.info("\n" + "=" * 50)
            LOGGER.info("TEST 8: LED OFF")
            LOGGER.info("=" * 50)
            input("💡 Press ENTER to turn LED OFF...")
            if await self.send_command(CMD_LED_OFF, wait_for_response=True):
                results["led_off"] = True
                LOGGER.info("✅ LED OFF command sent")
            else:
                results["errors"].append("LED OFF failed")

        except Exception as e:
            results["errors"].append(f"Test error: {e}")
            LOGGER.error(f"❌ Test error: {e}")

        finally:
            await self.disconnect()

        return results


def print_report(results: dict[str, Any]) -> None:
    """Print test report."""
    LOGGER.info("\n" + "=" * 50)
    LOGGER.info("TEST REPORT")
    LOGGER.info("=" * 50)

    total_tests = 8
    passed = sum(
        [
            results["connection"],
            results["led_on"],
            results["led_off"],
            results["brightness"],
            results["color_red"],
            results["color_green"],
            results["color_blue"],
            results["theme"],
            results["pixel"],
        ]
    )

    LOGGER.info(f"\nResults: {passed}/{total_tests} tests passed\n")

    for test, result in results.items():
        if test == "errors":
            continue
        status = "✅ PASS" if result else "❌ FAIL"
        LOGGER.info(f"  {test:15s}: {status}")

    if results["errors"]:
        LOGGER.info("\n❌ Errors encountered:")
        for error in results["errors"]:
            LOGGER.info(f"  - {error}")

    LOGGER.info("\n" + "=" * 50)
    if passed == total_tests:
        LOGGER.info("🎉 ALL TESTS PASSED!")
        LOGGER.info("The integration should work correctly.")
    elif passed >= total_tests // 2:
        LOGGER.info("⚠️  PARTIAL SUCCESS")
        LOGGER.info("Some features work. Check errors above.")
    else:
        LOGGER.info("❌ MOST TESTS FAILED")
        LOGGER.info("The protocol may have changed or there's a connection issue.")
    LOGGER.info("=" * 50)


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Test Moonside BLE Protocol")
    parser.add_argument("--mac", help="MAC address of Moonside device")
    parser.add_argument("--scan", action="store_true", help="Only scan for devices")
    parser.add_argument("--timeout", type=float, default=10.0, help="Scan timeout")
    args = parser.parse_args()

    tester = MoonsideTester(args.mac) if args.mac else MoonsideTester("")

    # Scan mode
    if args.scan or not args.mac:
        devices = await tester.discover(timeout=args.timeout)

        if not devices:
            LOGGER.error("❌ No Moonside devices found!")
            LOGGER.info("\nTroubleshooting:")
            LOGGER.info("  1. Ensure the light is powered on")
            LOGGER.info("  2. Ensure it's in pairing mode (blinking)")
            LOGGER.info("  3. Move closer to the Bluetooth adapter")
            LOGGER.info("  4. Check that your Bluetooth adapter supports BLE")
            sys.exit(1)

        if args.scan:
            LOGGER.info(f"\n📝 Found {len(devices)} device(s)")
            LOGGER.info(
                "Run again with: python test_moonside.py --mac XX:XX:XX:XX:XX:XX"
            )
            return

        # Use first device if found
        args.mac = devices[0][0]
        tester = MoonsideTester(args.mac)
        LOGGER.info(f"\n🎯 Auto-selected device: {devices[0][1]} ({args.mac})")

    # Run tests
    LOGGER.info("\n🧪 Starting protocol tests...")
    LOGGER.info("Follow the prompts to verify each function visually.")
    LOGGER.info("Press Ctrl+C to abort at any time.\n")

    try:
        results = await tester.run_tests()
        print_report(results)
    except KeyboardInterrupt:
        LOGGER.info("\n\n⚠️  Tests aborted by user")
        await tester.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
