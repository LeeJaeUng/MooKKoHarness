"""PostgreSQL 접속 도구(표준 라이브러리만, 시험용).

CI 장비에 psql·psycopg가 없어도 실제 PostgreSQL에 이관을 적용해 볼 수 있게, 프로토콜 3.0의 단순 질의만 구현한다.
인증은 SCRAM-SHA-256(PostgreSQL 기본)만, 전송 암호화는 하지 않는다 — 같은 장비의 시험 컨테이너 전용(test-postgres.json `tls.mode = disable`).
운영 접속에 쓰지 않는다. 근거: docs/architecture/engine.md › 시험용 PostgreSQL, PostgreSQL 문서 "Frontend/Backend Protocol".
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import socket
import struct
from dataclasses import dataclass

PROTOCOL_3 = 196608


class PgError(Exception):
    """서버가 돌려준 오류(SQLSTATE와 글)."""

    def __init__(self, sqlstate: str, message: str) -> None:
        super().__init__(f"{sqlstate} {message}")
        self.sqlstate = sqlstate
        self.message = message


@dataclass
class Result:
    """단순 질의 결과: 마지막 결과 집합의 행(글자 그대로)과 끝난 뒤 트랜잭션 상태(I·T·E)."""

    rows: list[list[str | None]]
    status: str


class Connection:
    """접속 하나."""

    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock

    @classmethod
    def connect(cls, host: str, port: int, user: str, password: str, database: str, timeout: float) -> Connection:
        sock = socket.create_connection((host, port), timeout=timeout)
        conn = cls(sock)
        try:
            conn._startup(user, password, database)
        except BaseException:
            sock.close()
            raise
        return conn

    def close(self) -> None:
        try:
            self.sock.sendall(b"X" + struct.pack("!i", 4))
        except OSError:
            pass  # 끊긴 접속을 닫는 중이라 보낼 수 없어도 됨
        self.sock.close()

    def __enter__(self) -> Connection:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ---- 보내고 받기 ----
    def _send(self, kind: bytes, payload: bytes) -> None:
        self.sock.sendall(kind + struct.pack("!i", len(payload) + 4) + payload)

    def _recv_exact(self, n: int) -> bytes:
        chunks: list[bytes] = []
        while n > 0:
            chunk = self.sock.recv(n)
            if not chunk:
                raise ConnectionError("server closed the connection")
            chunks.append(chunk)
            n -= len(chunk)
        return b"".join(chunks)

    def _recv(self) -> tuple[bytes, bytes]:
        head = self._recv_exact(5)
        kind = head[:1]
        (length,) = struct.unpack("!i", head[1:])
        return kind, self._recv_exact(length - 4)

    @staticmethod
    def _error(payload: bytes) -> PgError:
        fields: dict[str, str] = {}
        for part in payload.split(b"\0"):
            if part:
                fields[chr(part[0])] = part[1:].decode("utf-8", "replace")
        return PgError(fields.get("C", "?????"), fields.get("M", ""))

    # ---- 시작·인증 ----
    def _startup(self, user: str, password: str, database: str) -> None:
        params = b"".join(
            k.encode() + b"\0" + v.encode() + b"\0"
            for k, v in (("user", user), ("database", database), ("application_name", "mookko-dbcheck"), ("client_encoding", "UTF8"))
        )
        body = struct.pack("!i", PROTOCOL_3) + params + b"\0"
        self.sock.sendall(struct.pack("!i", len(body) + 4) + body)
        scram: _Scram | None = None
        while True:
            kind, payload = self._recv()
            if kind == b"E":
                raise self._error(payload)
            if kind == b"R":
                (code,) = struct.unpack("!i", payload[:4])
                if code == 0:
                    continue
                if code == 10:
                    if b"SCRAM-SHA-256\0" not in payload[4:]:
                        raise PgError("28000", "server does not offer SCRAM-SHA-256")
                    scram = _Scram(password)
                    first = scram.client_first().encode()
                    self._send(b"p", b"SCRAM-SHA-256\0" + struct.pack("!i", len(first)) + first)
                elif code == 11 and scram is not None:
                    self._send(b"p", scram.client_final(payload[4:].decode()).encode())
                elif code == 12 and scram is not None:
                    scram.verify_server(payload[4:].decode())
                else:
                    raise PgError("28000", f"unsupported authentication request {code}")
            elif kind == b"Z":
                return

    # ---- 질의 ----
    def query(self, sql: str) -> Result:
        """단순 질의(여러 문장 가능, 한 질의 안이면 암묵 트랜잭션). 오류면 끝까지 읽은 뒤 PgError."""
        self._send(b"Q", sql.encode("utf-8") + b"\0")
        rows: list[list[str | None]] = []
        error: PgError | None = None
        while True:
            kind, payload = self._recv()
            if kind == b"T":
                rows = []
            elif kind == b"D":
                (count,) = struct.unpack("!h", payload[:2])
                pos = 2
                row: list[str | None] = []
                for _ in range(count):
                    (size,) = struct.unpack("!i", payload[pos : pos + 4])
                    pos += 4
                    if size < 0:
                        row.append(None)
                    else:
                        row.append(payload[pos : pos + size].decode("utf-8"))
                        pos += size
                rows.append(row)
            elif kind == b"E":
                error = self._error(payload)
            elif kind == b"Z":
                status = payload.decode()
                if error is not None:
                    raise error
                return Result(rows=rows, status=status)


def quote_literal(value: str) -> str:
    """SQL 문자열 상수(시험 도구가 만든 값에만 씀)."""
    return "'" + value.replace("'", "''") + "'"


def quote_ident(value: str) -> str:
    """SQL 이름."""
    return '"' + value.replace('"', '""') + '"'


class _Scram:
    """SCRAM-SHA-256 (RFC 5802/7677). PostgreSQL은 사용자 이름을 시작 메시지에서 쓰므로 `n=`은 비움."""

    def __init__(self, password: str) -> None:
        self.password = password.encode("utf-8")
        self.nonce = base64.b64encode(os.urandom(18)).decode()
        self.first_bare = f"n=,r={self.nonce}"
        self.auth_message = b""
        self.salted = b""

    def client_first(self) -> str:
        return "n,," + self.first_bare

    def client_final(self, server_first: str) -> str:
        attrs = dict(item.split("=", 1) for item in server_first.split(","))
        if not attrs["r"].startswith(self.nonce):
            raise PgError("28000", "SCRAM nonce mismatch")
        salt = base64.b64decode(attrs["s"])
        self.salted = hashlib.pbkdf2_hmac("sha256", self.password, salt, int(attrs["i"]))
        client_key = hmac.new(self.salted, b"Client Key", hashlib.sha256).digest()
        stored_key = hashlib.sha256(client_key).digest()
        without_proof = f"c=biws,r={attrs['r']}"
        self.auth_message = f"{self.first_bare},{server_first},{without_proof}".encode()
        signature = hmac.new(stored_key, self.auth_message, hashlib.sha256).digest()
        proof = bytes(a ^ b for a, b in zip(client_key, signature))
        return f"{without_proof},p={base64.b64encode(proof).decode()}"

    def verify_server(self, server_final: str) -> None:
        attrs = dict(item.split("=", 1) for item in server_final.split(","))
        server_key = hmac.new(self.salted, b"Server Key", hashlib.sha256).digest()
        expected = hmac.new(server_key, self.auth_message, hashlib.sha256).digest()
        if not hmac.compare_digest(base64.b64decode(attrs.get("v", "")), expected):
            raise PgError("28000", "SCRAM server signature mismatch")
