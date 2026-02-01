#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import random
import socket
import struct
import time
from dataclasses import dataclass
from typing import Optional, Tuple

CONTROL_PORT = 50001

CONTROL_SIZE = 0x10
PING_SIZE = 0x15
OPENCLOSE_SIZE = 0x16
LOGIN_SIZE = 0x80
LOGIN_RESPONSE_SIZE = 0x60
TOKEN_SIZE = 0x40
STATUS_SIZE = 0x50
CONNINFO_SIZE = 0x90

AREYOUTHERE_PERIOD = 0.5
IDLE_PERIOD = 0.1
TOKEN_RENEWAL = 60.0  # seconds (WFview: 60000ms)


def passcode(s: str) -> bytes:
    sequence = bytes([
        0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
        0x47,0x5d,0x4c,0x42,0x66,0x20,0x23,0x46,0x4e,0x57,0x45,0x3d,0x67,0x76,0x60,0x41,0x62,0x39,0x59,0x2d,0x68,0x7e,
        0x7c,0x65,0x7d,0x49,0x29,0x72,0x73,0x78,0x21,0x6e,0x5a,0x5e,0x4a,0x3e,0x71,0x2c,0x2a,0x54,0x3c,0x3a,0x63,0x4f,
        0x43,0x75,0x27,0x79,0x5b,0x35,0x70,0x48,0x6b,0x56,0x6f,0x34,0x32,0x6c,0x30,0x61,0x6d,0x7b,0x2f,0x4b,0x64,0x38,
        0x2b,0x2e,0x50,0x40,0x3f,0x55,0x33,0x37,0x25,0x77,0x24,0x26,0x74,0x6a,0x28,0x53,0x4d,0x69,0x22,0x5c,0x44,0x31,
        0x36,0x58,0x3b,0x7a,0x51,0x5f,0x52,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
    ])
    b = s.encode("latin-1", errors="ignore")
    out = bytearray()
    for i in range(min(len(b), 16)):
        p = b[i] + i
        if p > 126:
            p = 32 + (p % 127)
        out.append(sequence[p])
    return bytes(out)


def u16be(x: int) -> bytes:
    return struct.pack(">H", x & 0xFFFF)


def u32be(x: int) -> bytes:
    return struct.pack(">I", x & 0xFFFFFFFF)


def pick_local_ip_for(remote_ip: str, remote_port: int) -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((remote_ip, remote_port))
        return s.getsockname()[0]
    finally:
        s.close()


def reserve_two_udp_ports(local_ip: str) -> Tuple[int, int]:
    ports = []
    for _ in range(2):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind((local_ip, 0))
        ports.append(s.getsockname()[1])
        s.close()
    if ports[0] == ports[1]:
        return reserve_two_udp_ports(local_ip)
    return ports[0], ports[1]


def compute_my_id(local_ip: str, local_port: int) -> int:
    addr_be = struct.unpack("!I", socket.inet_aton(local_ip))[0]
    return (((addr_be >> 8) & 0xFF) << 24) | ((addr_be & 0xFF) << 16) | (local_port & 0xFFFF)


def parse_header_le(data: bytes) -> Optional[Tuple[int, int, int, int, int]]:
    if len(data) < 0x10:
        return None
    return struct.unpack_from("<IHHII", data, 0)


def bcd_lsb_bytes_to_int(bcd: bytes) -> Optional[int]:
    value = 0
    mul = 1
    for byte in bcd:
        lo = byte & 0x0F
        hi = (byte >> 4) & 0x0F
        if lo > 9 or hi > 9:
            return None
        value += lo * mul
        mul *= 10
        value += hi * mul
        mul *= 10
    return value


def int_to_bcd_lsb_bytes(value: int, digits: int = 10) -> bytes:
    if value < 0:
        raise ValueError("Frequency must be >= 0")
    out = bytearray()
    for _ in range(digits // 2):
        lo = value % 10
        value //= 10
        hi = value % 10
        value //= 10
        out.append((hi << 4) | lo)
    if value != 0:
        raise ValueError("Frequency too large for BCD field")
    return bytes(out)


def parse_civ_frame(payload: bytes) -> Optional[Tuple[int, int, int, bytes]]:
    if len(payload) < 6:
        return None
    if payload[0] != 0xFE or payload[1] != 0xFE or payload[-1] != 0xFD:
        return None
    to_addr = payload[2]
    from_addr = payload[3]
    cmd = payload[4]
    data = payload[5:-1]
    return to_addr, from_addr, cmd, data


@dataclass
class UdpStream:
    sock: socket.socket
    local_port: int
    my_id: int
    remote_id: int = 0
    send_seq: int = 1


class IC705Client:
    def __init__(
        self,
        radio_ip: str,
        username: str,
        password: str,
        local_ip: Optional[str] = None,
        radio_name: str = "IC-705",
        radio_mac: Optional[bytes] = None,
        radio_guid: Optional[bytes] = None,
        civ_to: int = 0xA4,
        civ_from: int = 0xE0,
        comp_name: str = "PC-wfview",
    ) -> None:
        self.radio_ip = radio_ip
        self.username = username
        self.password = password
        self.local_ip = local_ip or pick_local_ip_for(radio_ip, CONTROL_PORT)
        self.radio_name = radio_name
        self.radio_mac = radio_mac
        self.radio_guid = radio_guid
        self.civ_to = civ_to & 0xFF
        self.civ_from = civ_from & 0xFF
        self.comp_name = comp_name

        self.ctrl_stream: Optional[UdpStream] = None
        self.civ_stream: Optional[UdpStream] = None

        self.civ_local_port = 0
        self.audio_local_port = 0
        self.civ_remote_port = 0

        self.auth_seq = 0x30
        self.tok_request = 0
        self.token = 0
        self.civ_sendseq_b = 0

    def connect(self, timeout_s: float = 20.0) -> None:
        self._open_control()
        self._control_handshake(timeout_s)
        if self.civ_remote_port == 0:
            raise RuntimeError("CIV port is 0 (streams not granted).")
        self._open_civ()
        self._civ_handshake(10.0)

    def close(self) -> None:
        if self.civ_stream:
            self.civ_stream.sock.close()
        if self.ctrl_stream:
            self.ctrl_stream.sock.close()

    def send_civ_frame(self, civ_payload: bytes) -> None:
        if not self.civ_stream:
            raise RuntimeError("CIV stream not ready.")
        hdr = bytearray(PING_SIZE)
        struct.pack_into(
            "<IHHII",
            hdr,
            0,
            PING_SIZE + len(civ_payload),
            0,
            0,
            self.civ_stream.my_id,
            self.civ_stream.remote_id,
        )
        hdr[0x10] = 0xC1
        struct.pack_into("<H", hdr, 0x11, len(civ_payload) & 0xFFFF)
        hdr[0x13:0x15] = u16be(self.civ_sendseq_b & 0xFFFF)
        self.civ_sendseq_b = (self.civ_sendseq_b + 1) & 0xFFFF

        pkt = hdr + civ_payload
        self._set_external_seq(self.civ_stream, pkt)
        self.civ_stream.sock.sendto(pkt, (self.radio_ip, self.civ_remote_port))

    def send_civ_cmd(self, cmd: int, data: bytes = b"") -> None:
        frame = bytes([0xFE, 0xFE, self.civ_to, self.civ_from, cmd]) + data + bytes([0xFD])
        self.send_civ_frame(frame)

    def get_frequency(self, timeout_s: float = 1.0) -> Optional[int]:
        self.send_civ_cmd(0x03)
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            payload = self.recv_civ(timeout_s=deadline - time.time())
            if not payload:
                continue
            parsed = parse_civ_frame(payload)
            if not parsed:
                continue
            to_addr, from_addr, cmd, data = parsed
            if cmd != 0x03:
                continue
            if to_addr != self.civ_from or from_addr != self.civ_to:
                continue
            if len(data) != 5:
                continue
            freq = bcd_lsb_bytes_to_int(data)
            return freq
        return None

    def set_frequency(self, freq_hz: int) -> None:
        data = int_to_bcd_lsb_bytes(freq_hz, 10)
        self.send_civ_cmd(0x05, data)

    def recv_civ(self, timeout_s: float = 0.1) -> Optional[bytes]:
        if not self.civ_stream:
            return None
        end = time.time() + max(timeout_s, 0.0)
        while time.time() < end:
            try:
                r, _ = self.civ_stream.sock.recvfrom(8192)
            except socket.timeout:
                return None
            if len(r) == CONTROL_SIZE:
                hdr = parse_header_le(r)
                if hdr:
                    _, ptype, _, sentid, _ = hdr
                    if ptype in (0x04, 0x06):
                        self.civ_stream.remote_id = sentid
                continue
            if len(r) == PING_SIZE:
                self._handle_ping(self.civ_stream, r, self.civ_remote_port)
                continue
            if len(r) > PING_SIZE and r[0x10] == 0xC1:
                return r[0x15:]
        return None

    def _open_control(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((self.local_ip, 0))
        sock.settimeout(0.1)
        local_port = sock.getsockname()[1]
        my_id = compute_my_id(self.local_ip, local_port)
        self.ctrl_stream = UdpStream(sock=sock, local_port=local_port, my_id=my_id, send_seq=1)

    def _open_civ(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((self.local_ip, self.civ_local_port))
        sock.settimeout(0.1)
        my_id = compute_my_id(self.local_ip, self.civ_local_port)
        self.civ_stream = UdpStream(sock=sock, local_port=self.civ_local_port, my_id=my_id, send_seq=1)

    def _control_handshake(self, timeout_s: float) -> None:
        if not self.ctrl_stream:
            raise RuntimeError("Control stream not open.")
        t0 = time.time()
        next_ayt = 0.0
        next_idle = 0.0
        next_token_renew = 0.0
        connected = False
        authenticated = False
        stream_requested = False

        while time.time() - t0 < timeout_s:
            now = time.time()
            if not connected and now >= next_ayt:
                self._send_control(self.ctrl_stream, 0x03, tracked=False, seq_untracked=0x0000, port=CONTROL_PORT)
                next_ayt = now + AREYOUTHERE_PERIOD

            if connected and now >= next_idle:
                self._send_control(self.ctrl_stream, 0x00, tracked=True, seq_untracked=0, port=CONTROL_PORT)
                next_idle = now + IDLE_PERIOD

            if authenticated and now >= next_token_renew:
                self._send_token(0x05)
                next_token_renew = now + TOKEN_RENEWAL

            try:
                r, _ = self.ctrl_stream.sock.recvfrom(4096)
            except socket.timeout:
                continue

            if len(r) == PING_SIZE:
                self._handle_ping(self.ctrl_stream, r, CONTROL_PORT)
                continue

            hdr = parse_header_le(r)
            if not hdr:
                continue
            plen, ptype, pseq, sentid, rcvdid = hdr

            if len(r) == CONTROL_SIZE:
                if ptype == 0x04:
                    self.ctrl_stream.remote_id = sentid
                    connected = True
                    self._send_control(self.ctrl_stream, 0x06, tracked=False, seq_untracked=0x0001, port=CONTROL_PORT)
                elif ptype == 0x06:
                    self._send_login()

            elif len(r) == LOGIN_RESPONSE_SIZE:
                error = struct.unpack_from("<I", r, 0x30)[0]
                tokreq = struct.unpack_from("<H", r, 0x1A)[0]
                token = struct.unpack_from("<I", r, 0x1C)[0]
                if error == 0xFEFFFFFF:
                    raise RuntimeError("Invalid Username/Password (0xFEFFFFFF)")
                if (not authenticated) and (tokreq == (self.tok_request & 0xFFFF)):
                    self.token = token
                    authenticated = True
                    self._send_token(0x02)
                    self._send_token(0x05)
                    next_token_renew = now + TOKEN_RENEWAL

            elif len(r) == TOKEN_SIZE:
                requestreply = r[0x14]
                requesttype = r[0x15]
                response = struct.unpack_from("<I", r, 0x30)[0]
                if requesttype == 0x05 and requestreply == 0x02 and ptype != 0x01:
                    if response == 0x00000000:
                        if not stream_requested:
                            self._send_request_stream()
                            stream_requested = True
                    elif response == 0xFFFFFFFF:
                        self.ctrl_stream.remote_id = sentid
                        self.tok_request = struct.unpack_from("<H", r, 0x1A)[0]
                        self.token = struct.unpack_from("<I", r, 0x1C)[0]
                        self._send_request_stream()
                        stream_requested = True

            elif len(r) == STATUS_SIZE:
                error = struct.unpack_from("<I", r, 0x30)[0]
                disc = r[0x40]
                civ_port = struct.unpack_from(">H", r, 0x42)[0]
                if error == 0xFFFFFFFF:
                    raise RuntimeError("Connection failed (status error=0xFFFFFFFF).")
                if error == 0x00000000 and disc == 0x01:
                    raise RuntimeError("Radio reports disconnected (disc=0x01).")
                self.civ_remote_port = civ_port
                return

        raise TimeoutError("Timeout during control handshake.")

    def _civ_handshake(self, timeout_s: float) -> None:
        if not self.civ_stream:
            raise RuntimeError("CIV stream not open.")
        t0 = time.time()
        next_ayt = 0.0

        while time.time() - t0 < timeout_s:
            now = time.time()
            if now >= next_ayt:
                self._send_control(self.civ_stream, 0x03, tracked=False, seq_untracked=0x0000, port=self.civ_remote_port)
                next_ayt = now + AREYOUTHERE_PERIOD

            try:
                r, _ = self.civ_stream.sock.recvfrom(8192)
            except socket.timeout:
                continue

            if len(r) == PING_SIZE:
                self._handle_ping(self.civ_stream, r, self.civ_remote_port)
                continue

            if len(r) == CONTROL_SIZE:
                hdr = parse_header_le(r)
                if not hdr:
                    continue
                _, ptype, _, sentid, _ = hdr
                if ptype == 0x04:
                    self.civ_stream.remote_id = sentid
                    self._send_control(self.civ_stream, 0x06, tracked=False, seq_untracked=0x0001, port=self.civ_remote_port)
                elif ptype == 0x06:
                    self.civ_stream.remote_id = sentid
                    self._send_openclose(True)
                    return

            if len(r) > PING_SIZE and r[0x10] == 0xC1:
                return

    def _send_control(self, stream: UdpStream, pkt_type: int, tracked: bool, seq_untracked: int, port: int) -> None:
        b = self._build_header(stream, CONTROL_SIZE, pkt_type=pkt_type)
        if not tracked:
            struct.pack_into("<H", b, 6, seq_untracked & 0xFFFF)
        else:
            self._set_external_seq(stream, b)
        stream.sock.sendto(b, (self.radio_ip, port))

    def _send_login(self) -> None:
        if not self.ctrl_stream:
            return
        self.tok_request = random.randrange(0, 65536)
        u = passcode(self.username)
        p = passcode(self.password)

        b = self._build_header(self.ctrl_stream, LOGIN_SIZE, pkt_type=0)
        b[0x10:0x14] = u32be(LOGIN_SIZE - 0x10)
        b[0x14] = 0x01
        b[0x15] = 0x00
        b[0x16:0x18] = u16be(self.auth_seq & 0xFFFF)
        self.auth_seq = (self.auth_seq + 1) & 0xFFFF
        struct.pack_into("<H", b, 0x1A, self.tok_request & 0xFFFF)

        b[0x40:0x40 + len(u)] = u
        b[0x50:0x50 + len(p)] = p
        cn = self.comp_name.encode("latin-1", errors="ignore")[:16]
        b[0x60:0x60 + len(cn)] = cn

        self._set_external_seq(self.ctrl_stream, b)
        self.ctrl_stream.sock.sendto(b, (self.radio_ip, CONTROL_PORT))

    def _send_token(self, magic: int) -> None:
        if not self.ctrl_stream:
            return
        b = self._build_header(self.ctrl_stream, TOKEN_SIZE, pkt_type=0)
        b[0x10:0x14] = u32be(TOKEN_SIZE - 0x10)
        b[0x14] = 0x01
        b[0x15] = magic & 0xFF
        b[0x16:0x18] = u16be(self.auth_seq & 0xFFFF)
        self.auth_seq = (self.auth_seq + 1) & 0xFFFF
        struct.pack_into("<H", b, 0x1A, self.tok_request & 0xFFFF)
        struct.pack_into("<I", b, 0x1C, self.token & 0xFFFFFFFF)
        b[0x24:0x26] = u16be(0x0798)

        self._set_external_seq(self.ctrl_stream, b)
        self.ctrl_stream.sock.sendto(b, (self.radio_ip, CONTROL_PORT))

    def _send_request_stream(self) -> None:
        if not self.ctrl_stream:
            return
        self.civ_local_port, self.audio_local_port = reserve_two_udp_ports(self.local_ip)
        u = passcode(self.username)

        b = self._build_header(self.ctrl_stream, CONNINFO_SIZE, pkt_type=0)
        b[0x10:0x14] = u32be(CONNINFO_SIZE - 0x10)
        b[0x14] = 0x01
        b[0x15] = 0x03
        b[0x16:0x18] = u16be(self.auth_seq & 0xFFFF)
        self.auth_seq = (self.auth_seq + 1) & 0xFFFF
        struct.pack_into("<H", b, 0x1A, self.tok_request & 0xFFFF)
        struct.pack_into("<I", b, 0x1C, self.token & 0xFFFFFFFF)

        if self.radio_guid:
            b[0x20:0x20 + 16] = self.radio_guid[:16].ljust(16, b"\x00")
        else:
            struct.pack_into("<H", b, 0x27, 0x8010)
            if self.radio_mac:
                b[0x2A:0x2A + 6] = self.radio_mac[:6].ljust(6, b"\x00")

        dn = self.radio_name.encode("latin-1", errors="ignore")[:32]
        b[0x40:0x40 + len(dn)] = dn

        b[0x60:0x60 + len(u)] = u
        b[0x70] = 1
        b[0x71] = 0
        b[0x72] = 0x04
        b[0x73] = 0x00
        b[0x74:0x78] = u32be(48000)
        b[0x78:0x7C] = u32be(0)
        b[0x7C:0x80] = u32be(self.civ_local_port)
        b[0x80:0x84] = u32be(self.audio_local_port)
        b[0x84:0x88] = u32be(0)
        b[0x88] = 1

        self._set_external_seq(self.ctrl_stream, b)
        self.ctrl_stream.sock.sendto(b, (self.radio_ip, CONTROL_PORT))

    def _send_openclose(self, open_: bool) -> None:
        if not self.civ_stream:
            return
        b = bytearray(OPENCLOSE_SIZE)
        struct.pack_into(
            "<IHHII",
            b,
            0,
            OPENCLOSE_SIZE,
            0,
            0,
            self.civ_stream.my_id,
            self.civ_stream.remote_id,
        )
        struct.pack_into("<H", b, 0x10, 0x01C0)
        b[0x12] = 0x00
        b[0x13:0x15] = u16be(self.civ_sendseq_b & 0xFFFF)
        b[0x15] = 0x04 if open_ else 0x00
        self.civ_sendseq_b = (self.civ_sendseq_b + 1) & 0xFFFF

        self._set_external_seq(self.civ_stream, b)
        self.civ_stream.sock.sendto(b, (self.radio_ip, self.civ_remote_port))

    def _build_header(self, stream: UdpStream, total_len: int, pkt_type: int = 0) -> bytearray:
        b = bytearray(total_len)
        struct.pack_into("<IHHII", b, 0, total_len, pkt_type & 0xFFFF, 0, stream.my_id, stream.remote_id)
        return b

    def _set_external_seq(self, stream: UdpStream, b: bytearray) -> None:
        b[6] = stream.send_seq & 0xFF
        b[7] = (stream.send_seq >> 8) & 0xFF
        stream.send_seq = (stream.send_seq + 1) & 0xFFFF

    def _handle_ping(self, stream: UdpStream, data: bytes, port: int) -> None:
        if len(data) != PING_SIZE:
            return
        hdr = parse_header_le(data)
        if not hdr:
            return
        _, ptype, pseq, _, _ = hdr
        if ptype != 0x07:
            return
        reply = data[0x10]
        if reply != 0x00:
            return
        b = bytearray(PING_SIZE)
        struct.pack_into("<IHHII", b, 0, PING_SIZE, 0x07, pseq & 0xFFFF, stream.my_id, stream.remote_id)
        b[0x10] = 0x01
        b[0x11:0x15] = data[0x11:0x15]
        stream.sock.sendto(b, (self.radio_ip, port))
