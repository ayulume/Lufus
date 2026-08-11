import os
import unittest
from unittest.mock import patch, MagicMock
from lufus.browse_freely import open_url, _resolve_user, ENV_OPEN_AS_USER


class TestResolveUser(unittest.TestCase):
    def setUp(self):
        self.loginuid_patch = patch("builtins.open", side_effect=FileNotFoundError)
        self.loginuid_patch.start()
        for var in ("PKEXEC_UID", "SUDO_UID", ENV_OPEN_AS_USER):
            os.environ.pop(var, None)

    def tearDown(self):
        self.loginuid_patch.stop()

    def test_no_elevation(self):
        self.assertEqual(_resolve_user(), (None, None))

    def test_pkexec_uid(self):
        os.environ["PKEXEC_UID"] = "1000"
        with patch("lufus.browse_freely.pwd.getpwuid") as mock:
            mock.return_value = MagicMock(pw_name="testuser", pw_uid=1000)
            self.assertEqual(_resolve_user(), ("testuser", 1000))
        mock.assert_called_once_with(1000)

    def test_sudo_uid(self):
        os.environ["SUDO_UID"] = "1001"
        with patch("lufus.browse_freely.pwd.getpwuid") as mock:
            mock.return_value = MagicMock(pw_name="sudouser", pw_uid=1001)
            self.assertEqual(_resolve_user(), ("sudouser", 1001))

    def test_pkexec_preferred_over_sudo(self):
        os.environ["PKEXEC_UID"] = "1000"
        os.environ["SUDO_UID"] = "1001"
        with patch("lufus.browse_freely.pwd.getpwuid") as mock:
            mock.return_value = MagicMock(pw_name="pkuser", pw_uid=1000)
            self.assertEqual(_resolve_user(), ("pkuser", 1000))

    def test_manual_override(self):
        os.environ[ENV_OPEN_AS_USER] = "manualguy"
        with patch("lufus.browse_freely.pwd.getpwnam") as mock:
            mock.return_value = MagicMock(pw_name="manualguy", pw_uid=2000)
            self.assertEqual(_resolve_user(), ("manualguy", 2000))
        mock.assert_called_once_with("manualguy")

    def test_manual_override_ignores_pkexec(self):
        os.environ[ENV_OPEN_AS_USER] = "forced"
        os.environ["PKEXEC_UID"] = "1000"
        with patch("lufus.browse_freely.pwd.getpwnam") as mock_pwnam:
            mock_pwnam.return_value = MagicMock(pw_name="forced", pw_uid=3000)
            self.assertEqual(_resolve_user(), ("forced", 3000))
        mock_pwnam.assert_called_once_with("forced")

    def test_invalid_manual_override_falls_through(self):
        os.environ[ENV_OPEN_AS_USER] = "nonexistent"
        with patch("lufus.browse_freely.pwd.getpwnam", side_effect=KeyError):
            result = _resolve_user()
            self.assertEqual(result, (None, None))

    def test_invalid_pkexec_uid_skips(self):
        os.environ["PKEXEC_UID"] = "notanint"
        self.assertEqual(_resolve_user(), (None, None))

    @patch("builtins.open", new_callable=MagicMock)
    def test_loginuid_fallback(self, mock_open):
        mock_open.return_value.__enter__.return_value.read.return_value = "1000\n"
        with patch("lufus.browse_freely.pwd.getpwuid") as mock:
            mock.return_value = MagicMock(pw_name="loginuser", pw_uid=1000)
            self.assertEqual(_resolve_user(), ("loginuser", 1000))
        mock.assert_called_once_with(1000)

    @patch("builtins.open", new_callable=MagicMock)
    def test_loginuid_skips_root(self, mock_open):
        mock_open.return_value.__enter__.return_value.read.return_value = "0\n"
        self.assertEqual(_resolve_user(), (None, None))

    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_loginuid_not_available(self, mock_open):
        self.assertEqual(_resolve_user(), (None, None))

    @patch("builtins.open", new_callable=MagicMock)
    def test_loginuid_unset_4294967295(self, mock_open):
        mock_open.return_value.__enter__.return_value.read.return_value = "4294967295\n"
        self.assertEqual(_resolve_user(), (None, None))

    @patch("builtins.open", new_callable=MagicMock)
    def test_loginuid_precedence(self, mock_open):
        mock_open.return_value.__enter__.return_value.read.return_value = "2000\n"
        os.environ["SUDO_UID"] = "1000"
        with patch("lufus.browse_freely.pwd.getpwuid") as mock:
            mock.return_value = MagicMock(pw_name="sudouser", pw_uid=1000)
            self.assertEqual(_resolve_user(), ("sudouser", 1000))


class TestOpenUrl(unittest.TestCase):
    def setUp(self):
        for var in ("PKEXEC_UID", "SUDO_UID", ENV_OPEN_AS_USER):
            os.environ.pop(var, None)

    @patch("lufus.browse_freely.os.geteuid", return_value=1000)
    @patch("lufus.browse_freely.webbrowser.open", return_value=True)
    def test_not_root_uses_webbrowser(self, mock_web, mock_euid):
        result = open_url("https://example.com")
        self.assertTrue(result)
        mock_web.assert_called_once_with("https://example.com")

    @patch("lufus.browse_freely.os.geteuid", return_value=0)
    @patch("lufus.browse_freely._resolve_user", return_value=(None, None))
    @patch("lufus.browse_freely.webbrowser.open", return_value=True)
    def test_root_no_user_falls_back(self, mock_web, mock_resolve, mock_euid):
        result = open_url("https://example.com")
        self.assertTrue(result)
        mock_web.assert_called_once_with("https://example.com")

    @patch("lufus.browse_freely.os.geteuid", return_value=0)
    @patch("lufus.browse_freely._resolve_user", return_value=("testuser", 1000))
    @patch("lufus.browse_freely.pwd.getpwuid")
    @patch("lufus.browse_freely.subprocess.Popen")
    def test_root_runs_runuser(self, mock_popen, mock_getpwuid, mock_resolve, mock_euid):
        mock_getpwuid.return_value = MagicMock(pw_dir="/home/testuser")
        result = open_url("https://example.com")
        self.assertTrue(result)
        mock_popen.assert_called_once()
        args, kwargs = mock_popen.call_args
        self.assertEqual(args[0], ["runuser", "-u", "testuser", "--", "xdg-open", "https://example.com"])
        self.assertIn("DISPLAY", kwargs["env"])
        self.assertIn("HOME", kwargs["env"])

    @patch("lufus.browse_freely.os.geteuid", return_value=0)
    @patch("lufus.browse_freely._resolve_user", return_value=("testuser", 1000))
    @patch("lufus.browse_freely.pwd.getpwuid")
    @patch("lufus.browse_freely.subprocess.Popen", side_effect=FileNotFoundError)
    @patch("lufus.browse_freely.webbrowser.open", return_value=True)
    def test_runuser_not_found_falls_back(self, mock_web, mock_popen, mock_getpwuid, mock_resolve, mock_euid):
        mock_getpwuid.return_value = MagicMock(pw_dir="/home/testuser")
        result = open_url("https://example.com")
        self.assertTrue(result)
        mock_web.assert_called_once_with("https://example.com")


if __name__ == "__main__":
    unittest.main()
