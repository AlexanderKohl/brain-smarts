"""The fake token endpoint: TLS on 127.0.0.1 with a certificate made for the run (conductor's
decision: post_token accepts https only). The certificate is trusted only inside wrapper.py, by a
context that holds this one certificate and nothing else. Every token it issues is invented and
derived from the run's seed, so the parent can compare hashes without seeing a value."""

from __future__ import annotations

import datetime
import hashlib
import hmac
import ipaddress
import json
import socket
import ssl
import threading
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

LOOPBACK = "127.0.0.1"
MODES = ("token", "refuse", "hang")


def make_certificate(folder: Path) -> tuple[Path, Path]:
    """A self-signed certificate for 127.0.0.1, valid for one day, and its key, in folder."""
    folder.mkdir(parents=True, exist_ok=True)
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "brain rehearsal token endpoint")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5)).not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(LOOPBACK))]), critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False,
                                         data_encipherment=False, key_agreement=False, key_cert_sign=True,
                                         crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()), critical=False)
            .sign(key, hashes.SHA256()))
    cert_path, key_path = folder / "cert.pem", folder / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    return cert_path, key_path


def certificate_hosts(cert_path: Path) -> list[str]:
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    return sorted(str(ip) for ip in names.get_values_for_type(x509.IPAddress))


def trusted_context(cafile: str | Path) -> ssl.SSLContext:
    """A client context that trusts only the run's certificate (no system store)."""
    return ssl.create_default_context(cafile=str(cafile))


def server_context(cert_path: Path, key_path: Path) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert_path), str(key_path))
    return context


def memory_handshake(client: ssl.SSLContext, server: ssl.SSLContext) -> bool:
    """A TLS handshake between two in-memory ends (no socket): whether the client trusts the
    server's certificate for 127.0.0.1. Used by --check and the tests."""
    pipes = [ssl.MemoryBIO() for _ in range(4)]  # client in/out, server in/out
    c = client.wrap_bio(pipes[0], pipes[1], server_hostname=LOOPBACK)
    s = server.wrap_bio(pipes[2], pipes[3], server_side=True)
    done = {"c": False, "s": False}
    for _ in range(20):
        for label, end in (("c", c), ("s", s)):
            if done[label]:
                continue
            try:
                end.do_handshake()
                done[label] = True
            except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
                pass
            except ssl.SSLError:
                return False
        pipes[2].write(pipes[1].read())
        pipes[0].write(pipes[3].read())
        if all(done.values()):
            return True
    return False


def _derive(label: str, number: int, seed: bytes) -> str:
    return "rehearsal-" + hmac.new(seed, f"{label}:{number}".encode(), hashlib.sha256).hexdigest()[:32]


def token_hash(number: int, seed: bytes) -> str:
    """The hash of the access token the endpoint issues as its number-th token."""
    return hashlib.sha256(_derive("access", number, seed).encode()).hexdigest()


def answer(mode: str, number: int, seed: bytes) -> tuple[int, bytes] | None:
    """The endpoint's answer in a mode; None means read the request and never answer."""
    if mode == "token":
        return 200, json.dumps({"access_token": _derive("access", number, seed),
                                "refresh_token": _derive("refresh", number, seed),
                                "token_type": "Bearer", "expires_in": 3600}).encode()
    if mode == "refuse":
        return 400, b'{"error": "invalid_grant"}'
    if mode == "hang":
        return None
    raise ValueError(f"unknown mode {mode}")


def free_closed_port() -> int:
    """A loopback port nothing listens on (bound, then closed): the "nothing was sent" case."""
    with socket.socket() as probe:
        probe.bind((LOOPBACK, 0))
        return probe.getsockname()[1]


class FakeTokenServer:
    """A one-thread HTTPS server on 127.0.0.1; the parent sets mode before each sub-step."""

    def __init__(self, cert_path: Path, key_path: Path, seed: bytes) -> None:
        self._context = server_context(cert_path, key_path)
        self._seed, self.mode, self.issued, self.calls = seed, "token", 0, 0
        self._listener = socket.create_server((LOOPBACK, 0))
        self._listener.settimeout(0.5)
        self._stop = threading.Event()
        self._held: list[socket.socket] = []
        self._thread = threading.Thread(target=self._loop, daemon=True)

    @property
    def url(self) -> str:
        return f"https://{LOOPBACK}:{self._listener.getsockname()[1]}/token"

    def start(self) -> "FakeTokenServer":
        self._thread.start()
        return self

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                raw, _ = self._listener.accept()
            except (socket.timeout, OSError):
                continue
            try:
                self._serve(raw)
            except (OSError, ssl.SSLError):
                raw.close()

    def _serve(self, raw: socket.socket) -> None:
        conn = self._context.wrap_socket(raw, server_side=True)
        conn.settimeout(10)
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk
        head, _, body = data.partition(b"\r\n\r\n")
        length = next((int(line.split(b":", 1)[1]) for line in head.split(b"\r\n")
                       if line.lower().startswith(b"content-length:")), 0)
        while len(body) < length:
            chunk = conn.recv(4096)
            if not chunk:
                break
            body += chunk
        self.calls += 1
        if self.mode == "token":
            self.issued += 1
        reply = answer(self.mode, self.issued, self._seed)
        if reply is None:  # time-out case: keep the connection open, never answer
            self._held.append(conn)
            return
        status, payload = reply
        reason = {200: "OK", 400: "Bad Request"}.get(status, "Status")
        conn.sendall(f"HTTP/1.1 {status} {reason}\r\nContent-Type: application/json\r\nContent-Length: "
                     f"{len(payload)}\r\nConnection: close\r\n\r\n".encode() + payload)
        conn.close()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5) if self._thread.is_alive() else None
        for conn in self._held:
            conn.close()
        self._listener.close()
