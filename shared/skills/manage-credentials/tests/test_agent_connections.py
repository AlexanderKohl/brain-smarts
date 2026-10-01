"""The Vault Agent survives a client with the wrong key, and the client never connects with the key of
an agent that has ended. Runs on its own pipe and runtime folder, never the owner's running agent."""
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from multiprocessing import AuthenticationError
from multiprocessing.connection import Client
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import vault_agent  # noqa: E402
import vault_agent_runtime  # noqa: E402
import vault_broker_client  # noqa: E402


class AgentConnectionsTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        name = f"PortableAIBrainVaultAgentTest-{secrets.token_hex(6)}"
        address = rf"\\.\pipe\{name}" if sys.platform == "win32" else str(self.folder / "agent.sock")
        self.address = address
        patches = [
            mock.patch.object(vault_agent_runtime, "runtime_dir", lambda: self.folder),
            mock.patch.object(vault_agent, "ipc_address", lambda: address),
            mock.patch.object(vault_broker_client, "ipc_address", lambda: address),
            mock.patch.object(vault_agent_runtime, "restrict_to_current_user", lambda path: None),
            mock.patch.object(vault_agent, "restrict_to_current_user", lambda path: None),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

    def start_agent(self):
        agent = vault_agent.VaultAgent(self.folder / "fictional.vault")
        thread = threading.Thread(target=agent.serve_forever, daemon=True)
        thread.start()
        deadline = time.time() + 5
        while time.time() < deadline and not (self.folder / "agent-state.json").is_file():
            time.sleep(0.05)
        self.assertTrue((self.folder / "agent-state.json").is_file(), "the agent did not start")
        self.addCleanup(agent.shutdown)
        return agent, thread

    def test_a_client_with_the_wrong_key_does_not_stop_the_agent(self):
        _agent, thread = self.start_agent()
        with self.assertRaises(AuthenticationError):
            Client(self.address, authkey=secrets.token_bytes(32))
        time.sleep(0.2)
        self.assertTrue(thread.is_alive(), "a refused connection stopped the agent")
        status = vault_broker_client.broker_request("status")
        self.assertIs(status["unlocked"], False)

    def test_the_client_refuses_the_state_of_an_agent_that_has_ended(self):
        ended = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True,
                               text=True).stdout.strip()
        vault_agent_runtime.write_state({"pid": int(ended), "address": self.address, "authkey": "00" * 32,
                                         "token": "0" * 64, "vault_path": "fictional.vault", "protocol": 1})
        with mock.patch.object(vault_broker_client, "Client", side_effect=AssertionError("connected")):
            with self.assertRaises(vault_broker_client.BrokerUnavailable) as caught:
                vault_broker_client.broker_request("status")
        self.assertIn("has ended", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
