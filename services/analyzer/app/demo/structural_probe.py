from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
import hashlib
import struct
from typing import Any, Iterator


MAGIC = b"PBDEMS2\x00"
HEADER_SIZE = 16
COMPRESSED_FLAG = 0x40

DEM_STOP = 0
DEM_FILE_HEADER = 1
DEM_FILE_INFO = 2
DEM_SYNC_TICK = 3
DEM_SEND_TABLES = 4
DEM_CLASS_INFO = 5
DEM_STRING_TABLES = 6
DEM_PACKET = 7
DEM_SIGNON_PACKET = 8
DEM_FULL_PACKET = 13
DEM_SPAWN_GROUPS = 15
DEM_RECOVERY = 18

GE_SOURCE1_LEGACY_EVENT_LIST = 205
GE_SOURCE1_LEGACY_EVENT = 207

COMMAND_NAMES = {
    0: "STOP",
    1: "FILE_HEADER",
    2: "FILE_INFO",
    3: "SYNC_TICK",
    4: "SEND_TABLES",
    5: "CLASS_INFO",
    6: "STRING_TABLES",
    7: "PACKET",
    8: "SIGNON_PACKET",
    9: "CONSOLE_CMD",
    10: "CUSTOM_DATA",
    11: "CUSTOM_DATA_CALLBACKS",
    12: "USER_CMD",
    13: "FULL_PACKET",
    14: "SAVE_GAME",
    15: "SPAWN_GROUPS",
    16: "ANIMATION_DATA",
    17: "ANIMATION_HEADER",
    18: "RECOVERY",
}

MAX_COMMAND_BODY = 64 * 1024 * 1024
MAX_PACKET_MESSAGE = 16 * 1024 * 1024
MAX_PROTO_DEPTH = 8


class ProbeError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class CommandFrame:
    index: int
    offset: int
    raw_command: int
    command: int
    compressed: bool
    tick: int
    body_size: int
    body_offset: int
    end_offset: int


@dataclass(frozen=True, slots=True)
class PlayerInfo:
    table_index: int
    name: str
    steamid64: int
    userid: int
    fake_player: bool
    is_hltv: bool


@dataclass(slots=True)
class ProbeSummary:
    sha256: str
    size_bytes: int
    file_info_offset: int
    spawn_groups_offset: int
    header: dict[str, Any]
    playback: dict[str, Any]
    command_counts: dict[str, int]
    outer_frame_count: int
    roster: list[PlayerInfo]
    event_schema_count: int
    legacy_event_count: int
    unique_legacy_event_types: int
    event_counts: dict[str, int]
    round_markers: dict[str, list[int]]
    server_tick_minus_demo_tick_histogram: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        return value


def _read_uvarint(data: bytes, pos: int, limit: int | None = None) -> tuple[int, int]:
    end = len(data) if limit is None else min(limit, len(data))
    value = 0
    shift = 0
    for _ in range(10):
        if pos >= end:
            raise ProbeError("truncated varint")
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, pos
        shift += 7
    raise ProbeError("varint exceeds supported width")


def _u32_to_i32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - (1 << 32) if value >= (1 << 31) else value


def _parse_wire(
    payload: bytes,
    *,
    max_fields: int = 100_000,
) -> list[tuple[int, int, int | bytes]]:
    pos = 0
    out: list[tuple[int, int, int | bytes]] = []

    while pos < len(payload):
        if len(out) >= max_fields:
            raise ProbeError("protobuf field limit exceeded")

        key, pos = _read_uvarint(payload, pos)
        field = key >> 3
        wire_type = key & 0x07

        if field <= 0:
            raise ProbeError("invalid protobuf field number")

        if wire_type == 0:
            value, pos = _read_uvarint(payload, pos)
        elif wire_type == 1:
            if pos + 8 > len(payload):
                raise ProbeError("truncated fixed64")
            value = payload[pos : pos + 8]
            pos += 8
        elif wire_type == 2:
            size, pos = _read_uvarint(payload, pos)
            if size > MAX_COMMAND_BODY or pos + size > len(payload):
                raise ProbeError("invalid length-delimited field")
            value = payload[pos : pos + size]
            pos += size
        elif wire_type == 5:
            if pos + 4 > len(payload):
                raise ProbeError("truncated fixed32")
            value = payload[pos : pos + 4]
            pos += 4
        else:
            raise ProbeError(f"unsupported protobuf wire type {wire_type}")

        out.append((field, wire_type, value))

    return out


def _decode_text(value: bytes) -> str:
    return value.decode("utf-8", errors="replace")


def _snappy_raw_decompress(data: bytes, *, max_output: int = MAX_COMMAND_BODY) -> bytes:
    pos = 0
    expected, pos = _read_uvarint(data, pos)
    if expected > max_output:
        raise ProbeError("snappy output exceeds decode limit")

    out = bytearray()
    n = len(data)

    while len(out) < expected:
        if pos >= n:
            raise ProbeError("truncated snappy stream")

        tag = data[pos]
        pos += 1
        kind = tag & 0x03

        if kind == 0:
            length_code = tag >> 2
            if length_code < 60:
                length = length_code + 1
            else:
                extra = length_code - 59
                if extra < 1 or extra > 4 or pos + extra > n:
                    raise ProbeError("invalid snappy literal length")
                length = int.from_bytes(data[pos : pos + extra], "little") + 1
                pos += extra

            if pos + length > n or len(out) + length > expected:
                raise ProbeError("invalid snappy literal")
            out.extend(data[pos : pos + length])
            pos += length
            continue

        if kind == 1:
            length = ((tag >> 2) & 0x07) + 4
            if pos >= n:
                raise ProbeError("truncated snappy copy-1")
            offset = ((tag & 0xE0) << 3) | data[pos]
            pos += 1
        elif kind == 2:
            length = (tag >> 2) + 1
            if pos + 2 > n:
                raise ProbeError("truncated snappy copy-2")
            offset = int.from_bytes(data[pos : pos + 2], "little")
            pos += 2
        else:
            length = (tag >> 2) + 1
            if pos + 4 > n:
                raise ProbeError("truncated snappy copy-4")
            offset = int.from_bytes(data[pos : pos + 4], "little")
            pos += 4

        if offset <= 0 or offset > len(out):
            raise ProbeError("invalid snappy back-reference")
        if len(out) + length > expected:
            raise ProbeError("snappy copy exceeds expected output")

        pattern = bytes(out[-offset:])
        repeats = (length + offset - 1) // offset
        out.extend((pattern * repeats)[:length])

    if len(out) != expected:
        raise ProbeError("snappy output length mismatch")

    return bytes(out)


class _BitReader:
    __slots__ = ("data", "bit", "nbits")

    def __init__(self, data: bytes):
        self.data = data
        self.bit = 0
        self.nbits = len(data) * 8

    def remaining(self) -> int:
        return self.nbits - self.bit

    def read_bits(self, count: int) -> int:
        if count < 0 or self.bit + count > self.nbits:
            raise ProbeError("bitstream underflow")
        byte_offset = self.bit >> 3
        bit_shift = self.bit & 7
        byte_count = (bit_shift + count + 7) >> 3
        chunk = int.from_bytes(
            self.data[byte_offset : byte_offset + byte_count],
            "little",
        )
        value = (chunk >> bit_shift) & ((1 << count) - 1 if count else 0)
        self.bit += count
        return value

    def read_ubitvar(self) -> int:
        value = self.read_bits(6)
        mode = value & 0x30
        if mode == 0x10:
            value = (value & 0x0F) | (self.read_bits(4) << 4)
        elif mode == 0x20:
            value = (value & 0x0F) | (self.read_bits(8) << 4)
        elif mode == 0x30:
            value = (value & 0x0F) | (self.read_bits(28) << 4)
        return value

    def read_uvarint32(self) -> int:
        value = 0
        shift = 0
        for _ in range(5):
            byte = self.read_bits(8)
            value |= (byte & 0x7F) << shift
            if byte < 0x80:
                return value
            shift += 7
        raise ProbeError("packet varint exceeds uint32")

    def skip_bytes(self, count: int) -> None:
        bits = count * 8
        if count < 0 or self.bit + bits > self.nbits:
            raise ProbeError("packet payload exceeds bitstream")
        self.bit += bits

    def read_bytes(self, count: int) -> bytes:
        if count < 0 or self.bit + count * 8 > self.nbits:
            raise ProbeError("packet payload exceeds bitstream")

        if (self.bit & 7) == 0:
            start = self.bit >> 3
            self.bit += count * 8
            return self.data[start : start + count]

        return bytes(self.read_bits(8) for _ in range(count))


def _iter_packet_messages(
    packet_data: bytes,
    capture_types: set[int],
) -> Iterator[tuple[int, bytes | None]]:
    reader = _BitReader(packet_data)

    while reader.remaining() > 8:
        message_type = reader.read_ubitvar()
        size = reader.read_uvarint32()

        if size > MAX_PACKET_MESSAGE or size * 8 > reader.remaining():
            raise ProbeError("invalid packet-message size")

        if message_type in capture_types:
            payload = reader.read_bytes(size)
        else:
            reader.skip_bytes(size)
            payload = None

        yield message_type, payload


def _iter_command_frames(data: bytes) -> Iterator[CommandFrame]:
    if len(data) < HEADER_SIZE or data[:8] != MAGIC:
        raise ProbeError("not a PBDEMS2 demo")

    pos = HEADER_SIZE
    index = 0

    while pos < len(data):
        offset = pos
        raw, pos = _read_uvarint(data, pos)
        tick_u32, pos = _read_uvarint(data, pos)
        body_size, pos = _read_uvarint(data, pos)

        if body_size > MAX_COMMAND_BODY:
            raise ProbeError("command body exceeds decode limit")

        body_offset = pos
        end_offset = body_offset + body_size
        if end_offset > len(data):
            raise ProbeError("truncated command body")

        yield CommandFrame(
            index=index,
            offset=offset,
            raw_command=raw,
            command=raw & ~COMPRESSED_FLAG,
            compressed=bool(raw & COMPRESSED_FLAG),
            tick=_u32_to_i32(tick_u32),
            body_size=body_size,
            body_offset=body_offset,
            end_offset=end_offset,
        )

        pos = end_offset
        index += 1


def _frame_body(data: bytes, frame: CommandFrame) -> bytes:
    encoded = data[frame.body_offset : frame.end_offset]
    if frame.compressed:
        return _snappy_raw_decompress(encoded)
    return encoded


def _parse_file_header(payload: bytes) -> dict[str, Any]:
    result: dict[str, Any] = {}
    names = {
        1: "demo_file_stamp",
        2: "patch_version",
        3: "server_name",
        4: "client_name",
        5: "map_name",
        6: "game_directory",
        7: "fullpackets_version",
        8: "allow_clientside_entities",
        9: "allow_clientside_particles",
        10: "addons",
        11: "demo_version_name",
        12: "demo_version_guid",
        13: "build_num",
        14: "game",
        15: "server_start_tick",
    }

    for field, wire_type, value in _parse_wire(payload):
        name = names.get(field, f"field_{field}")
        if wire_type == 2 and isinstance(value, bytes):
            result[name] = _decode_text(value)
        elif wire_type == 0 and isinstance(value, int):
            if field in {8, 9}:
                result[name] = bool(value)
            else:
                result[name] = _u32_to_i32(value)
    return result


def _parse_file_info(payload: bytes) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field, wire_type, value in _parse_wire(payload):
        if field == 1 and wire_type == 5 and isinstance(value, bytes):
            result["playback_time_seconds"] = struct.unpack("<f", value)[0]
        elif field == 2 and wire_type == 0 and isinstance(value, int):
            result["playback_ticks"] = _u32_to_i32(value)
        elif field == 3 and wire_type == 0 and isinstance(value, int):
            result["playback_frames"] = _u32_to_i32(value)

    duration = result.get("playback_time_seconds")
    ticks = result.get("playback_ticks")
    if isinstance(duration, float) and duration > 0 and isinstance(ticks, int):
        result["derived_tick_rate"] = ticks / duration
    return result


def _parse_string_tables(payload: bytes) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []

    for field, wire_type, table_payload in _parse_wire(payload):
        if field != 1 or wire_type != 2 or not isinstance(table_payload, bytes):
            continue

        table_name = ""
        items: list[dict[str, Any]] = []

        for table_field, table_wire, value in _parse_wire(table_payload):
            if table_field == 1 and table_wire == 2 and isinstance(value, bytes):
                table_name = _decode_text(value)
            elif table_field == 2 and table_wire == 2 and isinstance(value, bytes):
                item_name: str | None = None
                item_data: bytes | None = None
                for item_field, item_wire, item_value in _parse_wire(value):
                    if item_field == 1 and item_wire == 2 and isinstance(item_value, bytes):
                        item_name = _decode_text(item_value)
                    elif item_field == 2 and item_wire == 2 and isinstance(item_value, bytes):
                        item_data = item_value
                items.append({"str": item_name, "data": item_data})

        tables.append({"name": table_name, "items": items})

    return tables


def _parse_player_info(table_index: int, payload: bytes) -> PlayerInfo:
    name = ""
    steamid64 = 0
    userid = table_index
    fake_player = False
    is_hltv = False

    for field, wire_type, value in _parse_wire(payload):
        if field == 1 and wire_type == 2 and isinstance(value, bytes):
            name = _decode_text(value)
        elif field == 2 and wire_type == 1 and isinstance(value, bytes):
            steamid64 = int.from_bytes(value, "little")
        elif field == 3 and wire_type == 0 and isinstance(value, int):
            userid = _u32_to_i32(value)
        elif field == 5 and wire_type == 0 and isinstance(value, int):
            fake_player = bool(value)
        elif field == 6 and wire_type == 0 and isinstance(value, int):
            is_hltv = bool(value)

    return PlayerInfo(
        table_index=table_index,
        name=name,
        steamid64=steamid64,
        userid=userid,
        fake_player=fake_player,
        is_hltv=is_hltv,
    )


def _extract_packet_data(data: bytes, frame: CommandFrame) -> bytes | None:
    body = _frame_body(data, frame)

    if frame.command in {DEM_PACKET, DEM_SIGNON_PACKET}:
        for field, wire_type, value in _parse_wire(body):
            if field == 3 and wire_type == 2 and isinstance(value, bytes):
                return value
        return None

    if frame.command == DEM_FULL_PACKET:
        packet_message: bytes | None = None
        for field, wire_type, value in _parse_wire(body):
            if field == 2 and wire_type == 2 and isinstance(value, bytes):
                packet_message = value
                break
        if packet_message is None:
            return None
        for field, wire_type, value in _parse_wire(packet_message):
            if field == 3 and wire_type == 2 and isinstance(value, bytes):
                return value

    return None


def _parse_event_list(payload: bytes) -> dict[int, dict[str, Any]]:
    descriptors: dict[int, dict[str, Any]] = {}

    for field, wire_type, descriptor_payload in _parse_wire(payload):
        if field != 1 or wire_type != 2 or not isinstance(descriptor_payload, bytes):
            continue

        event_id: int | None = None
        name: str | None = None
        keys: list[dict[str, Any]] = []

        for desc_field, desc_wire, value in _parse_wire(descriptor_payload):
            if desc_field == 1 and desc_wire == 0 and isinstance(value, int):
                event_id = _u32_to_i32(value)
            elif desc_field == 2 and desc_wire == 2 and isinstance(value, bytes):
                name = _decode_text(value)
            elif desc_field == 3 and desc_wire == 2 and isinstance(value, bytes):
                key_type: int | None = None
                key_name: str | None = None
                for key_field, key_wire, key_value in _parse_wire(value):
                    if key_field == 1 and key_wire == 0 and isinstance(key_value, int):
                        key_type = _u32_to_i32(key_value)
                    elif key_field == 2 and key_wire == 2 and isinstance(key_value, bytes):
                        key_name = _decode_text(key_value)
                keys.append({"type": key_type, "name": key_name})

        if event_id is not None:
            descriptors[event_id] = {"name": name, "keys": keys}

    return descriptors


def _parse_event_value(payload: bytes) -> Any:
    value: Any = None

    for field, wire_type, raw in _parse_wire(payload):
        if field == 2 and wire_type == 2 and isinstance(raw, bytes):
            value = _decode_text(raw)
        elif field == 3 and wire_type == 5 and isinstance(raw, bytes):
            value = struct.unpack("<f", raw)[0]
        elif field in {4, 5, 6} and wire_type == 0 and isinstance(raw, int):
            value = _u32_to_i32(raw)
        elif field == 7 and wire_type == 0 and isinstance(raw, int):
            value = bool(raw)
        elif field == 8 and wire_type == 0 and isinstance(raw, int):
            value = raw

    return value


def _parse_legacy_event(
    payload: bytes,
    descriptors: dict[int, dict[str, Any]],
    demo_tick: int,
) -> dict[str, Any]:
    event_name: str | None = None
    event_id: int | None = None
    server_tick: int | None = None
    key_payloads: list[bytes] = []

    for field, wire_type, value in _parse_wire(payload):
        if field == 1 and wire_type == 2 and isinstance(value, bytes):
            event_name = _decode_text(value)
        elif field == 2 and wire_type == 0 and isinstance(value, int):
            event_id = _u32_to_i32(value)
        elif field == 3 and wire_type == 2 and isinstance(value, bytes):
            key_payloads.append(value)
        elif field == 4 and wire_type == 0 and isinstance(value, int):
            server_tick = _u32_to_i32(value)

    descriptor = descriptors.get(event_id or -1, {})
    resolved_name = event_name or descriptor.get("name") or f"event_{event_id}"
    key_defs = descriptor.get("keys") or []

    values: dict[str, Any] = {}
    for index, key_payload in enumerate(key_payloads):
        key_name = (
            key_defs[index].get("name")
            if index < len(key_defs) and key_defs[index].get("name")
            else f"key_{index}"
        )
        values[str(key_name)] = _parse_event_value(key_payload)

    return {
        "name": resolved_name,
        "event_id": event_id,
        "demo_tick": demo_tick,
        "server_tick": server_tick,
        "values": values,
    }


def probe_demo(path: str | Path, *, include_events: bool = False) -> tuple[ProbeSummary, list[dict[str, Any]]]:
    path = Path(path).expanduser().resolve(strict=True)
    data = path.read_bytes()

    if len(data) < HEADER_SIZE or data[:8] != MAGIC:
        raise ProbeError("file does not have a valid PBDEMS2 header")

    sha256 = hashlib.sha256(data).hexdigest()
    file_info_offset = int.from_bytes(data[8:12], "little")
    spawn_groups_offset = int.from_bytes(data[12:16], "little")

    frames = list(_iter_command_frames(data))
    if not frames:
        raise ProbeError("demo has no command frames")

    command_counts_raw = Counter(frame.command for frame in frames)
    command_counts = {
        COMMAND_NAMES.get(command, str(command)): count
        for command, count in sorted(command_counts_raw.items())
    }

    file_header_frame = next(
        (frame for frame in frames if frame.command == DEM_FILE_HEADER),
        None,
    )
    if file_header_frame is None:
        raise ProbeError("missing DEM_FileHeader")
    header = _parse_file_header(_frame_body(data, file_header_frame))

    file_info_frame = next(
        (
            frame
            for frame in frames
            if frame.offset == file_info_offset and frame.command == DEM_FILE_INFO
        ),
        None,
    )
    if file_info_frame is None:
        file_info_frame = next(
            (frame for frame in reversed(frames) if frame.command == DEM_FILE_INFO),
            None,
        )
    playback = (
        _parse_file_info(_frame_body(data, file_info_frame))
        if file_info_frame
        else {}
    )

    roster: list[PlayerInfo] = []
    string_table_frame = next(
        (frame for frame in frames if frame.command == DEM_STRING_TABLES),
        None,
    )
    if string_table_frame is not None:
        tables = _parse_string_tables(_frame_body(data, string_table_frame))
        userinfo = next((table for table in tables if table["name"] == "userinfo"), None)
        if userinfo:
            for index, item in enumerate(userinfo["items"]):
                item_data = item.get("data")
                if item_data:
                    roster.append(_parse_player_info(index, item_data))

    descriptors: dict[int, dict[str, Any]] = {}
    raw_events: list[tuple[int, bytes]] = []

    for frame in frames:
        if frame.command not in {DEM_PACKET, DEM_SIGNON_PACKET, DEM_FULL_PACKET}:
            continue

        packet_data = _extract_packet_data(data, frame)
        if packet_data is None:
            continue

        for message_type, message_payload in _iter_packet_messages(
            packet_data,
            capture_types={GE_SOURCE1_LEGACY_EVENT_LIST, GE_SOURCE1_LEGACY_EVENT},
        ):
            if message_payload is None:
                continue
            if message_type == GE_SOURCE1_LEGACY_EVENT_LIST:
                descriptors = _parse_event_list(message_payload)
            elif message_type == GE_SOURCE1_LEGACY_EVENT:
                raw_events.append((frame.tick, message_payload))

    events = [
        _parse_legacy_event(payload, descriptors, demo_tick)
        for demo_tick, payload in raw_events
    ]

    event_counts_raw = Counter(str(event["name"]) for event in events)
    event_counts = dict(sorted(event_counts_raw.items()))

    round_marker_names = [
        "round_prestart",
        "round_freeze_end",
        "round_officially_ended",
        "cs_win_panel_match",
    ]
    round_markers = {
        name: [
            int(event["demo_tick"])
            for event in events
            if event["name"] == name
        ]
        for name in round_marker_names
    }

    tick_deltas = Counter(
        int(event["server_tick"]) - int(event["demo_tick"])
        for event in events
        if event.get("server_tick") is not None
    )

    summary = ProbeSummary(
        sha256=sha256,
        size_bytes=len(data),
        file_info_offset=file_info_offset,
        spawn_groups_offset=spawn_groups_offset,
        header=header,
        playback=playback,
        command_counts=command_counts,
        outer_frame_count=len(frames),
        roster=roster,
        event_schema_count=len(descriptors),
        legacy_event_count=len(events),
        unique_legacy_event_types=len(event_counts),
        event_counts=event_counts,
        round_markers=round_markers,
        server_tick_minus_demo_tick_histogram={
            str(key): value for key, value in sorted(tick_deltas.items())
        },
    )

    return summary, events if include_events else []
