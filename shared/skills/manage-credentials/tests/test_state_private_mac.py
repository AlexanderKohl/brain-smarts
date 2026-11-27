"""The macOS proof of a private folder and file (TASK-alec-2026-0365), with the C library replaced, so
that its decisions are checked on every system: which file systems are admitted, how struct statfs is
read, and how the extended access list is seen, removed and proved gone. The real calls run on a Mac
in tests/test_state_private_posix.py (MacProofTest). Every value is fictional."""
import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import ctypes
import errno
import struct
import sys
import unittest
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import vault_agent_runtime as runtime  # noqa: E402
from vault_agent_runtime import NotPrivate  # noqa: E402

PATH = Path("fictional-folder")


def statfs(name: bytes = b"apfs", flags: int = 0, bsize: int = 4096) -> bytes:
    """A macOS struct statfs (64-bit inodes) with the three fields the proof reads."""
    data = bytearray(2168)
    struct.pack_into("=I", data, 0, bsize)
    struct.pack_into("=I", data, 64, flags)
    data[72:72 + len(name)] = name
    return bytes(data)


class FakeLibc:
    """fstatfs fills the buffer; the access list is a count of entries; every call is recorded."""

    def __init__(self, data: bytes = statfs(), entries: int = 0, removable: bool = True, fstatfs_code: int = 0,
                 attributes=()):
        self.data, self.entries, self.removable, self.fstatfs_code = data, entries, removable, fstatfs_code
        self.attributes = b"".join(name.encode() + bytes(1) for name in attributes)
        self.calls: list[str] = []

    def namespace(self) -> SimpleNamespace:
        return SimpleNamespace(fstatfs=self.fstatfs, acl_get_fd_np=self.acl_get_fd_np, acl_get_entry=self.acl_get_entry,
                               acl_init=self.acl_init, acl_set_fd_np=self.acl_set_fd_np, acl_free=self.acl_free,
                               flistxattr=self.flistxattr)

    def flistxattr(self, _descriptor, buffer, size, options):
        assert options == 0
        if buffer is None:
            return len(self.attributes)
        ctypes.memmove(buffer, self.attributes, min(size, len(self.attributes)))
        return len(self.attributes)

    def fstatfs(self, _descriptor, buffer):
        ctypes.memmove(buffer, self.data, len(self.data))
        return self.fstatfs_code

    def acl_get_fd_np(self, _descriptor, kind):
        assert kind == runtime._ACL_TYPE_EXTENDED
        self.calls.append("get")
        if self.entries < 0:
            ctypes.set_errno(errno.EACCES)
            return None
        if self.entries == 0:
            ctypes.set_errno(errno.ENOENT)
            return None
        return 1001

    def acl_get_entry(self, acl, which, _entry):
        assert which == runtime._ACL_FIRST_ENTRY
        if self.entries > 0:
            return 0
        ctypes.set_errno(errno.EINVAL)  # what macOS sets for a list without a first entry
        return -1

    def acl_init(self, count):
        assert count == 0
        return 2002

    def acl_set_fd_np(self, _descriptor, acl, kind):
        assert acl == 2002 and kind == runtime._ACL_TYPE_EXTENDED
        self.calls.append("set")
        if self.removable:
            self.entries = 0
        return 0

    def acl_free(self, _acl):
        return 0


class Case(unittest.TestCase):
    def use(self, libc: FakeLibc) -> None:
        for patcher in (mock.patch.object(runtime, "_mac_libc", libc.namespace),
                        mock.patch.object(runtime.os, "fstatvfs", create=True,
                                          return_value=SimpleNamespace(f_frsize=4096))):
            patcher.start()
            self.addCleanup(patcher.stop)


class FileSystemTests(Case):
    def test_apfs_and_hfs_are_admitted(self):
        for name in (b"apfs", b"hfs"):
            with self.subTest(name):
                self.use(FakeLibc(statfs(name)))
                runtime._mac_file_system(PATH, 7)

    def test_other_file_systems_refuse(self):
        for name in (b"msdos", b"exfat", b"smbfs", b"nfs", b""):
            with self.subTest(name):
                self.use(FakeLibc(statfs(name)))
                with self.assertRaises(NotPrivate) as caught:
                    runtime._mac_file_system(PATH, 7)
                self.assertIn("cannot be proved private", str(caught.exception))

    def test_a_volume_that_ignores_ownership_refuses(self):
        self.use(FakeLibc(statfs(flags=runtime._MNT_IGNORE_OWNERSHIP | 0x1000)))
        with self.assertRaises(NotPrivate) as caught:
            runtime._mac_file_system(PATH, 7)
        self.assertIn("ignores ownership", str(caught.exception))

    def test_an_unexpected_layout_refuses(self):
        self.use(FakeLibc(statfs(bsize=512)))
        with self.assertRaises(NotPrivate) as caught:
            runtime._mac_file_system(PATH, 7)
        self.assertIn("unexpected layout", str(caught.exception))

    def test_an_unterminated_name_and_a_failed_call_refuse(self):
        for libc in (FakeLibc(statfs(b"a" * 16)), FakeLibc(fstatfs_code=-1)):
            with self.subTest(libc.fstatfs_code):
                self.use(libc)
                with self.assertRaises(NotPrivate) as caught:
                    runtime._mac_file_system(PATH, 7)
                self.assertIn("cannot be read", str(caught.exception))

    def test_the_fields_are_read_at_their_offsets(self):
        self.assertEqual(runtime._mac_statfs_fields(statfs(b"apfs", 0x4000, 8192)), (8192, 0x4000, "apfs"))


class AccessListTests(Case):
    def test_no_access_list_passes_and_changes_nothing(self):
        libc = FakeLibc()
        self.use(libc)
        runtime._mac_lists(PATH, 7, change=True)
        self.assertEqual(libc.calls, ["get"])

    def test_an_access_list_refuses_the_proof_alone(self):
        self.use(FakeLibc(entries=2))
        with self.assertRaises(NotPrivate) as caught:
            runtime._mac_lists(PATH, 7, change=False)
        self.assertIn("has an access list", str(caught.exception))

    def test_an_access_list_is_removed_and_proved_gone(self):
        libc = FakeLibc(entries=2)
        self.use(libc)
        runtime._mac_lists(PATH, 7, change=True)
        self.assertEqual(libc.calls, ["get", "set", "get"])
        self.assertEqual(libc.entries, 0)

    def test_an_access_list_that_stays_refuses(self):
        self.use(FakeLibc(entries=1, removable=False))
        with self.assertRaises(NotPrivate) as caught:
            runtime._mac_lists(PATH, 7, change=True)
        self.assertIn("still there", str(caught.exception))

    def test_an_access_list_that_cannot_be_read_refuses(self):
        self.use(FakeLibc(entries=-1))
        with self.assertRaises(NotPrivate) as caught:
            runtime._mac_lists(PATH, 7, change=True)
        self.assertIn(f"error {errno.EACCES}", str(caught.exception))

    def test_an_attribute_named_for_an_access_list_refuses(self):
        self.use(FakeLibc(attributes=["com.apple.provenance", "com.apple.acl.text"]))
        with self.assertRaises(NotPrivate) as caught:
            runtime._mac_lists(PATH, 7, change=True)
        self.assertIn("com.apple.acl.text", str(caught.exception))

    def test_ordinary_attributes_pass(self):
        self.use(FakeLibc(attributes=["com.apple.macl", "com.apple.provenance", "com.apple.quarantine"]))
        runtime._mac_lists(PATH, 7, change=False)

    def test_the_attribute_names_are_split_at_their_terminators(self):
        self.use(FakeLibc(attributes=["com.apple.provenance", "com.example.fictional"]))
        self.assertEqual(runtime._mac_attribute_names(PATH, 7), ["com.apple.provenance", "com.example.fictional"])



class RuntimeFolderTests(unittest.TestCase):
    """macOS without XDG_RUNTIME_DIR: which home the runtime folder is under (runtime_base)."""
    REAL = PurePosixPath("/", "Users", "fictional")  # built from parts: a written path reads as personal data

    def home(self, home: PurePosixPath) -> PurePosixPath:
        return runtime._outside_the_sandbox(self.REAL, home)

    def test_a_sandboxed_app_uses_the_real_home(self):
        self.assertEqual(self.home(self.REAL.joinpath("Library", "Containers", "com.example.app", "Data")), self.REAL)

    def test_any_other_home_is_kept(self):
        for home in (self.REAL, PurePosixPath("/", "private", "tmp", "rehearsal", "pc1", "home"),
                     self.REAL / "Library"):
            with self.subTest(str(home)):
                self.assertEqual(self.home(home), home)

if __name__ == "__main__":
    unittest.main()
