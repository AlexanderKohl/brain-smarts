"""The POSIX proof of a private folder and file (follow-up plan R16, rules 1 and 2, with their amendments),
run for real on Linux: in WSL on the computer it was written on (Ubuntu, as root; /tmp is tmpfs, the home
is ext4, /mnt/c is 9p). It imports only vault_agent_runtime and the standard library, so that it runs
without the skill's other dependencies. Every folder is made with tempfile under /tmp or the home and
removed; nothing else is changed. MacProofTest is the same proof on macOS (TASK-alec-2026-0365): it uses
chmod +a and ls -le, and its folders are made under the home folder and removed; one test makes the
agent's own runtime folder private, as the agent's start does. On any other system the tests of each class
are skipped by platform."""
from __future__ import annotations

import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import ctypes
import os
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import vault_agent_runtime as runtime  # noqa: E402
from vault_agent_runtime import NotPrivate  # noqa: E402

LINUX = sys.platform.startswith("linux")
MAC = sys.platform == "darwin"
ROOT = LINUX and os.geteuid() == 0
UNDEFINED = 0xFFFFFFFF  # the id field of an access-list entry that names no one
USER_OBJ, USER, GROUP_OBJ, MASK, OTHER = 0x01, 0x02, 0x04, 0x10, 0x20
XFS = 0x58465342


def nobody() -> int:
    import pwd

    return pwd.getpwnam("nobody").pw_uid


def access_list(uid: int, perm: int, owner_perm: int) -> bytes:
    """The kernel's binary form of a POSIX access list (version 2) with one entry for `uid`."""
    entries = [(USER_OBJ, owner_perm, UNDEFINED), (USER, perm, uid), (GROUP_OBJ, 0, UNDEFINED),
               (MASK, perm, UNDEFINED), (OTHER, 0, UNDEFINED)]
    return struct.pack("<I", 2) + b"".join(struct.pack("<HHI", *entry) for entry in entries)


def can_read_as_nobody(path: Path) -> bool:
    result = subprocess.run([sys.executable, "-B", "-c", "import sys; open(sys.argv[1], 'rb').read()", str(path)],
                            user="nobody", capture_output=True)
    return result.returncode == 0


def acl_names(path: Path) -> list[str]:
    return [name for name in os.listxattr(path) if name.startswith("system.posix_acl")]


@unittest.skipUnless(LINUX, "the Linux proof; refused and not run elsewhere")
class LinuxProofTest(unittest.TestCase):
    def folder(self, under: str) -> Path:
        base = "/tmp" if under == "tmpfs" else str(Path.home())
        folder = Path(tempfile.mkdtemp(dir=base))
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        return folder

    def test_group_and_other_bits_are_removed_and_proved(self) -> None:
        for under in ("ext4 home", "tmpfs"):
            with self.subTest(under):
                folder = self.folder(under)
                file = folder / "fictional.txt"
                file.write_text("x", encoding="utf-8")
                for path, loose, tight in ((folder, 0o755, 0o700), (file, 0o644, 0o600)):
                    os.chmod(path, loose)
                    self.assertFalse(runtime.is_private(path))
                    runtime.make_private(path)
                    self.assertTrue(runtime.is_private(path))
                    self.assertEqual(os.stat(path).st_mode & 0o777, tight)

    def test_a_symbolic_link_is_refused(self) -> None:
        folder = self.folder("tmpfs")
        target = folder / "fictional.txt"
        target.write_text("x", encoding="utf-8")
        os.chmod(target, 0o644)
        link = folder / "link"
        os.symlink(target, link)
        with self.assertRaises(NotPrivate):
            runtime.make_private(link)
        self.assertFalse(runtime.is_private(link))
        self.assertEqual(os.stat(target).st_mode & 0o777, 0o644)

    def test_an_access_list_entry_for_another_user_is_seen_removed_and_proved_gone(self) -> None:
        for under in ("ext4 home", "tmpfs"):
            with self.subTest(under):
                file = self.folder(under) / "fictional.txt"
                file.write_text("x", encoding="utf-8")
                os.chmod(file, 0o600)
                os.setxattr(file, "system.posix_acl_access", access_list(nobody(), 4, 6))
                self.assertEqual(acl_names(file), ["system.posix_acl_access"])
                self.assertFalse(runtime.is_private(file))
                runtime.make_private(file)
                self.assertEqual(acl_names(file), [])
                self.assertTrue(runtime.is_private(file))

    def test_a_default_access_list_on_a_folder_is_seen_removed_and_proved_gone(self) -> None:
        for under in ("ext4 home", "tmpfs"):
            with self.subTest(under):
                folder = self.folder(under)
                os.chmod(folder, 0o700)
                os.setxattr(folder, "system.posix_acl_default", access_list(nobody(), 5, 7))
                self.assertIn("system.posix_acl_default", acl_names(folder))
                self.assertFalse(runtime.is_private(folder))
                runtime.make_private(folder)
                self.assertEqual(acl_names(folder), [])
                self.assertTrue(runtime.is_private(folder))

    @unittest.skipUnless(ROOT, "a second user id needs root")
    def test_a_second_user_reads_through_its_entry_until_the_file_is_made_private(self) -> None:
        outer = self.folder("tmpfs")
        os.chmod(outer, 0o711)  # others, the user nobody among them, may traverse it but not list it
        file = outer / "fictional.txt"
        file.write_text("x", encoding="utf-8")
        os.chmod(file, 0o600)
        os.setxattr(file, "system.posix_acl_access", access_list(nobody(), 4, 6))
        self.assertTrue(can_read_as_nobody(file), "the entry did not let the second user read")
        runtime.make_private(file)
        self.assertFalse(can_read_as_nobody(file))

    @unittest.skipUnless(ROOT, "a second user id needs root")
    def test_a_second_user_reads_inside_a_folder_until_the_folder_is_made_private(self) -> None:
        outer = self.folder("tmpfs")
        os.chmod(outer, 0o711)
        folder = outer / "data"
        folder.mkdir(mode=0o700)
        os.setxattr(folder, "system.posix_acl_access", access_list(nobody(), 5, 7))
        file = folder / "fictional.txt"
        file.write_text("x", encoding="utf-8")
        os.chmod(file, 0o644)
        self.assertTrue(can_read_as_nobody(file), "the folder's entry did not let the second user in")
        runtime.make_private(folder)
        self.assertFalse(can_read_as_nobody(file))

    def test_a_9p_folder_is_refused_as_a_file_system_that_cannot_be_proved(self) -> None:
        here = Path(__file__).resolve().parent
        if not str(here).startswith("/mnt/"):
            self.skipTest("this file is not on a 9p mount")
        before = os.stat(here).st_mode
        self.assertFalse(runtime.is_private(here))
        with self.assertRaises(NotPrivate) as caught:
            runtime._posix(here, change=False)
        self.assertIn("file system (type 0x1021997)", str(caught.exception))
        self.assertEqual(os.stat(here).st_mode, before)

    def test_write_state_and_prepare_runtime_dir_in_a_temporary_runtime_folder(self) -> None:
        folder = self.folder("tmpfs") / "vault-agent"
        payload = {"pid": os.getpid(), "address": "fictional", "authkey": "ab" * 32, "token": "fictional-token",
                   "vault_path": "fictional.vault", "protocol": runtime.AGENT_PROTOCOL_VERSION}
        with mock.patch.object(runtime, "runtime_base", lambda: folder):
            runtime.prepare_runtime_dir()
            runtime.write_state(payload)
            self.assertEqual(runtime.read_state(), payload)
            self.assertTrue(runtime.is_private(folder))
            self.assertTrue(runtime.is_private(folder / "agent-state.json"))
            self.assertEqual(list(folder.glob("agent-state*.tmp")), [])

    def test_an_unadmitted_file_system_number_refuses(self) -> None:
        def xfs(_descriptor, buffer):
            ctypes.c_long.from_buffer(buffer).value = XFS
            return 0

        folder = self.folder("tmpfs")
        with mock.patch.object(runtime, "_linux_libc", lambda: mock.Mock(fstatfs=xfs)):
            with self.assertRaises(NotPrivate) as caught:
                runtime.make_private(folder)
        self.assertIn("0x58465342", str(caught.exception))

    def test_a_failing_fstatfs_refuses(self) -> None:
        folder = self.folder("tmpfs")
        with mock.patch.object(runtime, "_linux_libc", lambda: mock.Mock(fstatfs=lambda _d, _b: -1)):
            with self.assertRaises(NotPrivate) as caught:
                runtime.make_private(folder)
        self.assertIn("cannot be read", str(caught.exception))

    def test_a_left_over_system_attribute_refuses(self) -> None:
        folder = self.folder("tmpfs")
        for name in ("system.richacl", "user.fictional_ACL"):
            with self.subTest(name), mock.patch.object(runtime.os, "listxattr", return_value=[name]):
                with self.assertRaises(NotPrivate):
                    runtime.make_private(folder)


def mac_acl_lines(path: Path) -> list[str]:
    """The access-list entries `ls -led` shows under the path's own line (" 0: group:everyone allow read")."""
    shown = subprocess.run(["ls", "-led", str(path)], capture_output=True, text=True, check=True).stdout
    return [line for line in shown.splitlines()[1:] if line.strip()]


def mac_add_acl(path: Path, entry: str) -> None:
    subprocess.run(["chmod", "+a", entry, str(path)], check=True)


@unittest.skipUnless(MAC, "the macOS proof; refused and not run elsewhere")
class MacProofTest(unittest.TestCase):
    def folder(self) -> Path:
        folder = Path(tempfile.mkdtemp(dir=str(Path.home())))
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        return folder

    def test_the_home_folder_is_on_an_admitted_file_system(self) -> None:
        folder = self.folder()
        descriptor = os.open(folder, os.O_RDONLY)
        try:
            runtime._mac_file_system(folder, descriptor)
        finally:
            os.close(descriptor)

    def test_group_and_other_bits_are_removed_and_proved(self) -> None:
        folder = self.folder()
        file = folder / "fictional.txt"
        file.write_text("x", encoding="utf-8")
        os.chmod(folder, 0o755)
        os.chmod(file, 0o644)
        self.assertFalse(runtime.is_private(folder))
        self.assertFalse(runtime.is_private(file))
        runtime.make_private(folder)
        runtime.make_private(file)
        self.assertEqual(stat.S_IMODE(os.stat(folder).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(file).st_mode), 0o600)
        self.assertTrue(runtime.is_private(folder))
        self.assertTrue(runtime.is_private(file))

    def test_a_symbolic_link_is_refused(self) -> None:
        folder = self.folder()
        target = folder / "fictional.txt"
        target.write_text("x", encoding="utf-8")
        link = folder / "link"
        os.symlink(target, link)
        with self.assertRaises(NotPrivate) as caught:
            runtime.make_private(link)
        self.assertIn("symbolic link", str(caught.exception))

    def test_an_access_list_entry_for_everyone_is_seen_removed_and_proved_gone(self) -> None:
        folder = self.folder()
        file = folder / "fictional.txt"
        file.write_text("x", encoding="utf-8")
        runtime.make_private(file)
        mac_add_acl(file, "everyone allow read")
        self.assertEqual(stat.S_IMODE(os.stat(file).st_mode), 0o600)  # the mode alone does not show it
        self.assertTrue(mac_acl_lines(file))
        self.assertFalse(runtime.is_private(file))
        runtime.make_private(file)
        self.assertEqual(mac_acl_lines(file), [])
        self.assertTrue(runtime.is_private(file))

    def test_an_inherited_access_list_on_a_folder_is_seen_removed_and_proved_gone(self) -> None:
        folder = self.folder() / "vault-agent"
        folder.mkdir()
        mac_add_acl(folder, "everyone allow list,search,file_inherit,directory_inherit")
        self.assertFalse(runtime.is_private(folder))
        runtime.make_private(folder)
        self.assertEqual(mac_acl_lines(folder), [])
        self.assertTrue(runtime.is_private(folder))

    def test_a_file_made_in_a_folder_with_an_inheritable_entry_is_made_private(self) -> None:
        folder = self.folder()
        mac_add_acl(folder, "everyone allow list,file_inherit")  # list is read on a file
        file = folder / "fictional.txt"
        file.write_text("x", encoding="utf-8")
        self.assertTrue(mac_acl_lines(file))  # inherited at creation
        runtime.make_private(file)
        self.assertEqual(mac_acl_lines(file), [])
        self.assertTrue(runtime.is_private(file))

    def test_write_state_and_prepare_runtime_dir_in_a_temporary_runtime_folder(self) -> None:
        folder = self.folder() / "vault-agent"
        payload = {"pid": os.getpid(), "address": "fictional", "authkey": "ab" * 32, "token": "fictional-token",
                   "vault_path": "fictional.vault", "protocol": runtime.AGENT_PROTOCOL_VERSION}
        with mock.patch.object(runtime, "runtime_base", lambda: folder):
            runtime.prepare_runtime_dir()
            runtime.write_state(payload)
            self.assertEqual(runtime.read_state(), payload)
            self.assertTrue(runtime.is_private(folder))
            self.assertTrue(runtime.is_private(folder / "agent-state.json"))
            self.assertEqual(mac_acl_lines(folder / "agent-state.json"), [])
            self.assertEqual(list(folder.glob("agent-state*.tmp")), [])

    def test_the_real_runtime_folder_can_be_proved_private(self) -> None:
        """The folder the agent will use on this Mac, made private as the agent's start makes it."""
        runtime.prepare_runtime_dir()
        self.assertTrue(runtime.is_private(runtime.runtime_dir()))


@unittest.skipUnless(os.name == "posix", "a POSIX system that is not Linux, simulated on a POSIX system")
class RefusedSystemTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(dir="/tmp"))
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        patch = mock.patch.object(runtime.sys, "platform", "freebsd14")
        patch.start()
        self.addCleanup(patch.stop)

    def test_make_private_refuses_and_restrict_still_sets_the_mode(self) -> None:
        file = self.folder / "fictional.txt"
        file.write_text("x", encoding="utf-8")
        os.chmod(file, 0o644)
        with self.assertRaises(NotPrivate) as caught:
            runtime.make_private(file)
        self.assertIn("never been run on freebsd14", str(caught.exception))
        self.assertEqual(os.stat(file).st_mode & 0o777, 0o644)
        runtime.restrict_to_current_user(file)
        self.assertEqual(os.stat(file).st_mode & 0o777, 0o600)
        os.chmod(self.folder, 0o755)
        runtime.restrict_to_current_user(self.folder)
        self.assertEqual(stat.S_IMODE(os.stat(self.folder).st_mode), 0o700)

    def test_the_fallback_does_not_follow_a_symbolic_link(self) -> None:
        target = self.folder / "fictional.txt"
        target.write_text("x", encoding="utf-8")
        os.chmod(target, 0o644)
        link = self.folder / "link"
        os.symlink(target, link)
        runtime.restrict_to_current_user(link)
        self.assertEqual(os.stat(target).st_mode & 0o777, 0o644)


if __name__ == "__main__":
    unittest.main()
