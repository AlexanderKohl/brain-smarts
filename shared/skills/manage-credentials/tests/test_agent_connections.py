"""The Vault Agent survives a client with the wrong key, and the client never connects with the key of
an agent that has ended. Runs on its own pipe and runtime folder, never the owner's running agent."""
import os
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
        ]  # the real proof of a private folder and file runs in the temporary folder (plan R15, rule 9)
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

    def test_on_windows_the_runtime_folder_is_outside_appdata(self):
        with mock.patch.object(vault_agent_runtime.os, "name", "nt"), \
                mock.patch.dict(vault_agent_runtime.os.environ, {"USERPROFILE": r"D:\profile"}):
            base = vault_agent_runtime.runtime_base()
        self.assertNotIn("appdata", str(base).lower())
        self.assertEqual(base.parts[-2:], (".portable-ai-brain", "vault-agent"))

    def test_the_client_refuses_the_state_of_an_agent_that_has_ended(self):
        ended = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True,
                               text=True).stdout.strip()
        vault_agent_runtime.write_state({"pid": int(ended), "address": self.address, "authkey": "00" * 32,
                                         "token": "0" * 64, "vault_path": "fictional.vault", "protocol": 1})
        with mock.patch.object(vault_broker_client, "Client", side_effect=AssertionError("connected")):
            with self.assertRaises(vault_broker_client.BrokerUnavailable) as caught:
                vault_broker_client.broker_request("status")
        self.assertIn("has ended", str(caught.exception))

    def test_an_agent_that_stops_leaves_another_agents_state_file(self):
        # The fault of 16 November 2026: a test agent's shutdown at interpreter exit removed the
        # state file of the owner's running tray, which then could not be reached until restarted.
        agent, _thread = self.start_agent()
        other = {"pid": os.getpid() + 1, "address": self.address, "authkey": "00" * 32,
                 "token": "0" * 64, "vault_path": "fictional.vault", "protocol": 1}
        vault_agent_runtime.write_state(other)
        agent.shutdown()
        self.assertEqual(vault_agent_runtime.read_state(), other)

    def test_a_stopped_agent_leaves_nothing_to_run_at_exit(self):
        agent, _thread = self.start_agent()
        with mock.patch.object(vault_agent.atexit, "unregister") as unregister:
            agent.shutdown()
        unregister.assert_called_once_with(agent.shutdown)

    def test_a_running_agent_puts_back_a_state_file_that_went_missing(self):
        with mock.patch.object(vault_agent.VaultAgent, "STATE_CHECK_SECONDS", 0.1):
            self.start_agent()
            state = self.folder / "agent-state.json"
            state.unlink()
            deadline = time.time() + 5
            while time.time() < deadline and not state.is_file():
                time.sleep(0.05)
        self.assertTrue(state.is_file(), "the agent did not write its state file again")
        self.assertIs(vault_broker_client.broker_request("status")["unlocked"], False)

    def test_a_second_start_leaves_a_running_agents_state_file(self):
        self.start_agent()
        with mock.patch.object(vault_agent_runtime.Path, "read_text", side_effect=PermissionError("locked")):
            vault_agent_runtime.prepare_runtime_dir()
        self.assertTrue((self.folder / "agent-state.json").is_file())


if __name__ == "__main__":
    unittest.main()
