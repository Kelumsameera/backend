"""
Thin async Modbus TCP helpers using pymodbus.
Connection is opened per poll cycle and closed immediately to avoid
leaking sockets on network glitches (common on factory floors).
"""

from __future__ import annotations

import logging
import struct
from typing import Optional

from pymodbus.client import AsyncModbusTcpClient

log = logging.getLogger("modbus")


async def read_float32(
    host: str,
    port: int,
    unit: int,
    address: int,
    *,
    byteorder: str = "BIG",
    wordorder: str = "LITTLE",
    timeout: float = 2.0,
) -> Optional[float]:
    """
    Read 2 holding registers and decode as 32-bit float.
    Default byte/word order matches common industrial gateways
    (BIG byte, LITTLE word) used by the existing system.
    """
    client = AsyncModbusTcpClient(host=host, port=port, timeout=timeout)
    try:
        connected = await client.connect()
        if not connected:
            log.warning("Cannot connect %s:%s", host, port)
            return None

        result = await client.read_holding_registers(
            address=address, count=2, slave=unit
        )
        if result.isError():
            log.warning("Read error %s@%s: %s", host, address, result)
            return None

        regs = result.registers
        if len(regs) < 2:
            return None

        # Word order: LITTLE → swap register pair
        if wordorder.upper() == "LITTLE":
            raw = struct.pack(">HH", regs[1], regs[0])
        else:
            raw = struct.pack(">HH", regs[0], regs[1])

        if byteorder.upper() == "LITTLE":
            raw = raw[::-1]

        value = struct.unpack(">f", raw)[0]
        if value != value:  # NaN
            return None
        return round(float(value), 2)
    except Exception as e:
        log.warning("Modbus %s:%s failed: %s", host, port, e)
        return None
    finally:
        client.close()


async def read_uint16_input(
    host: str,
    port: int,
    unit: int,
    address: int,
    *,
    scale: float = 1.0,
    timeout: float = 2.0,
) -> Optional[float]:
    """Read a single input register, optionally scaled."""
    client = AsyncModbusTcpClient(host=host, port=port, timeout=timeout)
    try:
        connected = await client.connect()
        if not connected:
            return None
        result = await client.read_input_registers(
            address=address, count=1, slave=unit
        )
        if result.isError() or not result.registers:
            return None
        return round(result.registers[0] / scale, 2) if scale != 1.0 else float(
            result.registers[0]
        )
    except Exception as e:
        log.warning("Input reg %s@%s failed: %s", host, address, e)
        return None
    finally:
        client.close()


async def read_uint16_holding(
    host: str,
    port: int,
    unit: int,
    address: int,
    *,
    scale: float = 1.0,
    timeout: float = 2.0,
) -> Optional[float]:
    """Read a single holding register, optionally scaled."""
    client = AsyncModbusTcpClient(host=host, port=port, timeout=timeout)
    try:
        connected = await client.connect()
        if not connected:
            return None
        result = await client.read_holding_registers(
            address=address, count=1, slave=unit
        )
        if result.isError() or not result.registers:
            return None
        return round(result.registers[0] / scale, 2) if scale != 1.0 else float(
            result.registers[0]
        )
    except Exception as e:
        log.warning("Holding reg %s@%s failed: %s", host, address, e)
        return None
    finally:
        client.close()
