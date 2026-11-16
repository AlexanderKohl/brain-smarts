"""The unlock dialog: Enter submits, Esc cancels, and the window is tall enough for its buttons."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

if sys.platform == "win32":
    import vault_tray as tray


@unittest.skipUnless(sys.platform == "win32", "the tray is a Windows program")
class DialogKeys(unittest.TestCase):
    def test_enter_stands_for_ok_and_esc_for_cancel(self) -> None:
        self.assertEqual(tray._dialog_key_command(tray._WM_KEYDOWN, tray._VK_RETURN), tray._IDC_OK)
        self.assertEqual(tray._dialog_key_command(tray._WM_KEYDOWN, tray._VK_ESCAPE), tray._IDC_CANCEL)

    def test_other_keys_and_other_messages_stand_for_nothing(self) -> None:
        self.assertIsNone(tray._dialog_key_command(tray._WM_KEYDOWN, ord("A")))
        self.assertIsNone(tray._dialog_key_command(tray._WM_COMMAND, tray._VK_RETURN))

    def test_the_window_is_larger_than_its_inside_by_the_title_bar_and_frame(self) -> None:
        style = tray._WS_POPUP | tray._WS_CAPTION | tray._WS_SYSMENU | tray._DS_MODALFRAME
        ex_style = tray._WS_EX_DLGMODALFRAME | tray._WS_EX_TOPMOST
        width, height = tray._outer_size(372, tray._DIALOG_CLIENT_HEIGHT, style, ex_style)
        self.assertGreater(width, 372)
        self.assertGreater(height, tray._DIALOG_CLIENT_HEIGHT + 20)

    def test_the_inside_reaches_below_the_buttons(self) -> None:
        self.assertGreaterEqual(tray._DIALOG_CLIENT_HEIGHT, 88 + 28 + 12)


if __name__ == "__main__":
    unittest.main()
