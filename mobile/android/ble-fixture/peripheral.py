"""Public synthetic A04 peripheral for Android/Netsim transport verification.

This is a Python protocol fixture, not Zephyr firmware or an ownership service.
Only the two pinned C-generated archives below can be served. No physical HCI,
arbitrary source path, provisioning, recording, deletion or release is exposed.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import struct
import sys
import time
from uuid import UUID
import zlib

from bumble.att import ATT_Error, ATT_INSUFFICIENT_RESOURCES_ERROR, ATT_WRITE_NOT_PERMITTED_ERROR
from bumble.device import Device, DeviceConfiguration
from bumble.gatt import Characteristic, CharacteristicValue, Service
from bumble.transport import open_transport

ROOT = Path(__file__).resolve().parents[3]
INDEX = ROOT / 'mobile/android/app/src/androidTest/assets/downloads/index.json'
INDEX_SHA = 'a160804c8090e09ecd2b13436e27d2ed334b65cdf819b12ad715b3d3882d96cd'
ADDRESS = 'F0:F1:F2:F3:F4:F5'
SERVICE = '7f520000-1b15-4f0d-8fe5-3f942170a004'
COMMAND = '7f520001-1b15-4f0d-8fe5-3f942170a004'
RESPONSE = '7f520002-1b15-4f0d-8fe5-3f942170a004'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Fixture:
    name: str
    wire: bytes
    physical: bytes
    select: bytes
    finish: bytes
    boundaries: frozenset[int]

    @property
    def identity(self) -> bytes:
        return self.wire[24:40]


def load_fixtures() -> tuple[dict, list[Fixture], dict[str, str]]:
    raw = INDEX.read_bytes()
    if sha(raw) != INDEX_SHA:
        raise ValueError('Pinned public fixture index differs')
    index = json.loads(raw)
    bindings = {INDEX.relative_to(ROOT).as_posix(): sha(raw)}
    golden = ROOT / 'firmware/a04/verification/transfer-wire-golden.tsv'
    if sha(golden.read_bytes()) != index['golden_sha256']:
        raise ValueError('C wire-vector binding differs')
    bindings[golden.relative_to(ROOT).as_posix()] = sha(golden.read_bytes())
    fixtures = []
    for item in index['fixtures']:
        name = item['name']
        if name not in ('finalized', 'open'):
            raise ValueError('Only fixed public C fixtures are supported')
        sources = []
        for kind, suffix in [('archive', '.aura'), ('physical', '.physical.ack3')]:
            source = ROOT / 'firmware/a04/verification/transfer-fixtures' / (name + suffix)
            wire = source.read_bytes()
            if sha(wire) != item[kind]['sha256'] or len(wire) != item[kind]['bytes']:
                raise ValueError('C source identity differs')
            bindings[source.relative_to(ROOT).as_posix()] = sha(wire)
            sources.append(wire)
        wire, physical = sources
        selected, finished = bytes.fromhex(item['select_response']), bytes.fromhex(item['finish_response'])
        if selected[8:76] != wire[:68] or selected[76:170] != physical or finished[8:102] != physical:
            raise ValueError('C selection/finish source binding differs')
        boundaries = {0, 68}
        offset = 68
        while offset < len(wire):
            magic = wire[offset:offset + 4]
            if magic == b'ASE3':
                size = 120
                if offset + size != len(wire):
                    raise ValueError('Unexpected terminal boundary')
            elif magic == b'AFR3':
                size = 26 + struct.unpack_from('<H', wire, offset + 20)[0]
            else:
                raise ValueError('Unexpected record magic')
            record = wire[offset:offset + size]
            if len(record) != size or zlib.crc32(record[:-4]) != int.from_bytes(record[-4:], 'little'):
                raise ValueError('Invalid fixed record framing')
            offset += size
            boundaries.add(offset)
        fixtures.append(Fixture(name, wire, physical, selected, finished, frozenset(boundaries)))
    if len(fixtures) != 2 or {x.name for x in fixtures} != {'finalized', 'open'}:
        raise ValueError('Exactly two source fixtures required')
    bindings[Path(__file__).relative_to(ROOT).as_posix()] = sha(Path(__file__).read_bytes())
    return index, fixtures, bindings


@dataclass
class Session:
    serial: int
    last_command: bytes = b''
    last_response: bytes = b''
    transaction: int = 0
    handle: int = 0
    selected: Fixture | None = None
    offset: int | None = None
    sent_eof: bool = False
    send_task: asyncio.Task | None = None
    commands: Counter = field(default_factory=Counter)
    notifications: int = 0
    duplicates: int = 0
    read_bytes: int = 0
    mtu: int = 23
    completed: list[str] = field(default_factory=list)


class Peripheral:
    def __init__(self, device: Device, index: dict, fixtures: list[Fixture], args, bindings: dict):
        self.device, self.index, self.fixtures, self.args, self.bindings = device, index, fixtures, args, bindings
        self.sessions: dict[object, Session] = {}
        self.history: list[Session] = []
        self.errors: list[str] = []
        self.response = Characteristic(RESPONSE, Characteristic.Properties.NOTIFY, 0, b'')
        command = Characteristic(COMMAND, Characteristic.Properties.WRITE, Characteristic.WRITEABLE,
                                 CharacteristicValue(write=self.write))
        device.add_service(Service(SERVICE, [command, self.response]))
        device.gatt_server.max_mtu = args.mtu
        device.on('connection', self.connected)

    def connected(self, connection):
        state = Session(len(self.history) + 1)
        self.history.append(state)
        self.sessions[connection] = state

        def disconnected(_reason):
            self.sessions.pop(connection, None)
            if state.send_task:
                state.send_task.cancel()
            self.report('advertising')

        connection.on('disconnection', disconnected)
        self.report('connected')

    def write(self, connection, value):
        state = self.sessions.get(connection)
        wire = bytes(value)
        if state is None or len(wire) not in range(4, 21):
            raise ATT_Error(ATT_WRITE_NOT_PERMITTED_ERROR)
        subscribers = self.device.gatt_server.subscribers.get(connection, {})
        subscribed = subscribers.get(self.response.handle, b'')
        if len(subscribed) != 2 or subscribed[0] & 1 == 0:
            raise ATT_Error(ATT_WRITE_NOT_PERMITTED_ERROR)
        version, opcode, transaction = struct.unpack_from('<BBH', wire)
        lengths = {1: 4, 2: 10, 3: 20, 4: 18, 5: 16, 6: 8}
        if version != 1 or not transaction or lengths.get(opcode) != len(wire):
            raise ATT_Error(ATT_WRITE_NOT_PERMITTED_ERROR)
        if transaction == state.transaction:
            if wire != state.last_command:
                raise ATT_Error(ATT_WRITE_NOT_PERMITTED_ERROR)
            state.duplicates += 1
            if state.send_task and not state.send_task.done():
                return
        else:
            if transaction < state.transaction or (state.send_task and not state.send_task.done()):
                raise ATT_Error(ATT_INSUFFICIENT_RESOURCES_ERROR)
            state.transaction, state.last_command = transaction, wire
            state.last_response = self.command(state, opcode, transaction, wire)
            state.commands[str(opcode)] += 1
        state.mtu = connection.att_mtu
        state.send_task = asyncio.create_task(self.send(connection, state, state.last_response))

    def command(self, state: Session, opcode: int, transaction: int, wire: bytes) -> bytes:
        header = struct.pack('<BBH', 0, opcode, transaction)
        failure = lambda status: struct.pack('<BBH', status, opcode, transaction)
        if opcode == 1:
            return header + bytes.fromhex(self.index['contexts']['device_id']) + bytes.fromhex(
                self.index['contexts']['incarnation']) + struct.pack('<IHHH', 1, len(self.fixtures), 512, 256)
        if opcode == 2:
            revision, index = struct.unpack_from('<IH', wire, 4)
            if revision != 1:
                return failure(7)
            if index >= len(self.fixtures):
                return failure(6)
            fixture = self.fixtures[index]
            return header + struct.pack('<IH', 1, index) + fixture.wire[:68] + bytes([
                2 if fixture.name == 'finalized' else 1, 0])
        if opcode == 3:
            state.selected = next((x for x in self.fixtures if x.identity == wire[4:]), None)
            state.offset, state.sent_eof = None, False
            if state.selected is None:
                return failure(3)
            state.handle += 1
            return header + struct.pack('<I', state.handle) + state.selected.select[8:]
        handle = struct.unpack_from('<I', wire, 4)[0]
        if state.selected is None or handle != state.handle:
            return failure(3)
        source = state.selected
        if opcode == 4:
            offset, requested = struct.unpack_from('<QH', wire, 8)
            if requested not in range(1, 257) or offset > len(source.wire):
                return failure(2)
            if (state.offset is None and offset not in source.boundaries) or (
                    state.offset is not None and offset != state.offset):
                return failure(8)
            data = source.wire[offset:offset + min(requested, self.args.chunk_bytes)]
            state.offset = offset + len(data)
            state.sent_eof = len(data) == 0 and offset == len(source.wire)
            state.read_bytes += len(data)
            return header + struct.pack('<IQH', handle, offset, len(data)) + data + struct.pack('<I', zlib.crc32(data))
        if opcode == 5:
            expected = struct.unpack_from('<Q', wire, 8)[0]
            if expected != len(source.wire) or state.offset != expected or not state.sent_eof:
                return failure(2)
            state.completed.append(source.name)
            return header + struct.pack('<I', handle) + source.finish[8:]
        if opcode == 6:
            state.selected, state.offset = None, None
            return header + struct.pack('<I', handle)
        return failure(2)

    async def send(self, connection, state: Session, response: bytes):
        try:
            for offset in range(0, len(response), connection.att_mtu - 11):
                if self.sessions.get(connection) is not state:
                    return
                fragment = struct.pack('<BBHHH', 1, 0, state.transaction, offset, len(response)) + response[
                    offset:offset + connection.att_mtu - 11]
                await self.device.notify_subscriber(connection, self.response, fragment)
                state.notifications += 1
                await asyncio.sleep(0)  # Let ATT write completion run; no simulated packet loss.
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.errors.append(type(error).__name__)
            self.report('send-failed')

    def report(self, state: str):
        self.args.report.parent.mkdir(parents=True, exist_ok=True)
        content = {
            'schema': 'aura.android.netsim.peripheral.v1', 'state': state,
            'observed_utc': datetime.now(timezone.utc).isoformat(),
            'fixture_only': True, 'zephyr_firmware_executed': False,
            'physical_radio_tested': False, 'ownership_authenticated': False,
            'address': ADDRESS, 'name': 'AURA-test-only', 'configured_att_mtu': self.args.mtu,
            'read_chunk_limit': self.args.chunk_bytes, 'source_sha256': self.bindings,
            'python': sys.version, 'bumble_version': importlib.metadata.version('bumble'),
            'errors': self.errors,
            'connections': [{'number': s.serial, 'commands': dict(s.commands), 'att_mtu': s.mtu,
                'notifications': s.notifications, 'exact_command_retries': s.duplicates,
                'source_bytes_sent': s.read_bytes, 'finished_sources': s.completed} for s in self.history],
        }
        self.args.report.write_text(json.dumps(content, indent=2) + '\n', encoding='utf-8')


async def run(args):
    index, fixtures, bindings = load_fixtures()
    if args.check:
        print(json.dumps({'fixed_sources': len(fixtures), 'source_sha256': bindings}, indent=2))
        return
    if args.report.exists() or args.stop_file.exists():
        raise ValueError('Use new report and stop-file paths for each retained run')
    config = DeviceConfiguration()
    name = b'AURA-test-only'
    advertising = b'\x02\x01\x06\x11\x07' + UUID(SERVICE).bytes[::-1]
    scan_response = bytes([len(name) + 1, 9]) + name
    config.load_from_dict({'name': 'AURA-test-only', 'address': ADDRESS,
                           'classic_enabled': False, 'le_privacy_enabled': False, 'keystore': None,
                           'advertising_data': advertising.hex(), 'scan_response_data': scan_response.hex()})
    transport = f'android-netsim:127.0.0.1:{args.netsim_port},name=aura_a04_fixture'
    async with await open_transport(transport) as hci:
        device = Device.from_config_with_hci(config, hci.source, hci.sink)
        peripheral = Peripheral(device, index, fixtures, args, bindings)
        try:
            await device.power_on()
            await device.start_advertising(auto_restart=True)
            peripheral.report('advertising')
            print('AURA_PUBLIC_FIXTURE_READY', flush=True)
            end = time.monotonic() + args.duration_seconds
            while time.monotonic() < end and not args.stop_file.exists():
                await asyncio.sleep(0.5)
        finally:
            for session in peripheral.history:
                if session.send_task:
                    session.send_task.cancel()
            peripheral.report('stopped')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Validate fixed source bindings without any connection')
    parser.add_argument('--netsim-port', type=int, default=0)
    parser.add_argument('--mtu', type=int, choices=(23, 517), default=517)
    parser.add_argument('--chunk-bytes', type=int, choices=(128, 256), default=256)
    parser.add_argument('--duration-seconds', type=int, default=900)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--stop-file', type=Path)
    args = parser.parse_args()
    if not args.check and (not 1 <= args.netsim_port <= 65535 or args.report is None or args.stop_file is None or
                           not 60 <= args.duration_seconds <= 1800):
        parser.error('Explicit local Netsim port, new report/stop paths and 60..1800 second duration required')
    asyncio.run(run(args))


if __name__ == '__main__':
    main()
