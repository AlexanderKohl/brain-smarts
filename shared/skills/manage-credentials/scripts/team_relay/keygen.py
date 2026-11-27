"""The relay's own key pair (design 6.1 and 6.3), made on an administrator's computer:

1. a new X25519 key pair, in this process's memory only;
2. the private key written once to the recovery file, sealed to the administrator's personal
   recovery key (section 12, question 7), so only those 24 words open it again;
3. the private key set as the Railway variable RELAY_PRIVATE_KEY of the relay's service through
   Railway's API, with the token the railway-access skill uses (RAILWAY_API_TOKEN, injected by
   vault_credentials.py run --map), never on a command line or in output;
4. the public key printed, for relay-init.

relay-restore reverses step 2 for a new Railway project: the words in the masked window, the file,
and step 3 again."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from secret_store import canonical, envelope, keys
from secret_store.errors import SecretStoreError
from secret_store.hpke import public_bytes

GRAPHQL = "https://backboard.railway.com/graphql/v2"
VARIABLE = "RELAY_PRIVATE_KEY"
RECOVERY_HEADER = {"group": "relay-recovery", "id": "relay-key", "kind": "static", "revision": 1}
_UPSERT = "mutation($input: VariableUpsertInput!) { variableUpsert(input: $input) }"


def seal_recovery(private_key: X25519PrivateKey, policy: Any) -> dict:
    """The recovery file: the relay's private key sealed to the personal store's recovery key."""
    recovery_id = policy.recovery[0]
    payload = {"relay_private_key": base64.b64encode(keys.raw_private(private_key)).decode("ascii")}
    return envelope.seal(payload, [(recovery_id, policy.enc_keys[recovery_id])],
                         {"repository": policy.repository, **RECOVERY_HEADER})


def open_recovery(doc: dict, recovery_x25519: X25519PrivateKey) -> X25519PrivateKey:
    payload = envelope.open_(doc, keys.key_id(recovery_x25519.public_key()), recovery_x25519)
    return X25519PrivateKey.from_private_bytes(base64.b64decode(payload["relay_private_key"], validate=True))


def _post(token: str, body: dict) -> dict:
    request = urllib.request.Request(GRAPHQL, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json",
        "User-Agent": "brain-team-relay/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - Railway's https API
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise SecretStoreError(f"Railway refused the variable (HTTP {error.code})") from None
    except (urllib.error.URLError, OSError, ValueError):
        raise SecretStoreError("Railway could not be reached; the key was not set there") from None


def set_railway_variable(private_key: X25519PrivateKey, project: str, environment: str, service: str,
                         post: Callable[[str, dict], dict] = _post) -> None:
    token = os.environ.get("RAILWAY_API_TOKEN", "").strip()
    if not token:
        raise SecretStoreError("RAILWAY_API_TOKEN is not set; run this through vault_credentials.py run "
                               "--map RAILWAY_API_TOKEN=api_token")
    value = base64.b64encode(keys.raw_private(private_key)).decode("ascii")
    answer = post(token, {"query": _UPSERT, "variables": {"input": {
        "projectId": project, "environmentId": environment, "serviceId": service, "name": VARIABLE,
        "value": value}}})
    if answer.get("errors") or not (answer.get("data") or {}).get("variableUpsert"):
        raise SecretStoreError("Railway did not set the variable (its answer named errors; no value is shown)")


def relay_keygen(recovery_file: str, project: str, environment: str, service: str,
                 post: Callable[[str, dict], dict] = _post) -> int:
    from secret_store.store import SecretStore
    path = Path(recovery_file)
    if path.exists():
        raise SecretStoreError(f"{path} already exists; a relay key is made once (6.3)")
    personal = SecretStore().open()
    private_key = X25519PrivateKey.generate()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical.dumps(seal_recovery(private_key, personal.policy)))
    set_railway_variable(private_key, project, environment, service, post)
    public = base64.b64encode(public_bytes(private_key.public_key())).decode("ascii")
    print(f"The relay key is made. Recovery file: {path} (opens only with your personal recovery words). "
          f"Railway variable {VARIABLE} is set. Relay public key, for relay-init: {public}")
    return 0
