# coding: utf-8
#

import hashlib
from unittest.mock import Mock, mock_open, patch

import pytest

from uiautomator2.core import (
    DEFAULT_SERVER_PORT,
    DEFAULT_U2_JAR_RELATIVE_PATH,
    BasicUiautomatorServer,
    default_u2_jar_path,
    validate_u2_jar_path,
)


def test_default_u2_jar_path_uses_jar_subtree():
    path = default_u2_jar_path()

    if path is not None:
        assert path.name == "app-debug.apk"
        assert path.as_posix().endswith(DEFAULT_U2_JAR_RELATIVE_PATH.as_posix())


def test_validate_u2_jar_path(tmp_path):
    jar_path = tmp_path / "u2.jar"
    jar_path.write_bytes(b"baseline jar")

    assert validate_u2_jar_path(jar_path) == jar_path.resolve()


def test_validate_u2_jar_path_missing(tmp_path):
    with pytest.raises(FileNotFoundError, match="u2.jar not found"):
        validate_u2_jar_path(tmp_path / "missing.jar")


@pytest.fixture
def mock_server():
    """Create a mock BasicUiautomatorServer instance with a mock device"""
    mock_dev = Mock()
    with patch.object(BasicUiautomatorServer, '__init__', return_value=None):
        server = BasicUiautomatorServer(None, DEFAULT_SERVER_PORT)
        server._dev = mock_dev
        server._device_server_port = DEFAULT_SERVER_PORT
        yield server, mock_dev


class TestCheckDeviceFileHash:
    """Test the _check_device_file_hash method with toybox fallback"""
    
    def test_toybox_md5sum_success(self, mock_server):
        """Test when toybox md5sum command works correctly"""
        server, mock_dev = mock_server
        
        # Create a temporary file with known content
        test_content = b"test content for md5"
        local_md5 = hashlib.md5(test_content).hexdigest()
        
        # Mock the shell command to return toybox md5sum output
        # Format: "md5hash  filename"
        mock_dev.shell.return_value = f"{local_md5}  /data/local/tmp/u2.jar"
        
        # Mock the file read to return our test content
        with patch("builtins.open", mock_open(read_data=test_content)):
            result = server._check_device_file_hash("test.jar", "/data/local/tmp/u2.jar")
        
        # Verify the result is True (hash matches)
        assert result is True
        # Verify toybox md5sum was called
        mock_dev.shell.assert_called_once_with(["toybox", "md5sum", "/data/local/tmp/u2.jar"])
    
    def test_toybox_not_found_fallback_to_md5(self, mock_server):
        """Test fallback to md5 command when toybox is not found"""
        server, mock_dev = mock_server
        
        # Create a temporary file with known content
        test_content = b"test content for md5"
        local_md5 = hashlib.md5(test_content).hexdigest()
        
        # Mock the shell command to return different outputs
        # First call: toybox not found
        # Second call: md5 command output (format: "MD5 (filename) = md5hash")
        mock_dev.shell.side_effect = [
            "toybox: not found",
            f"MD5 (/data/local/tmp/u2.jar) = {local_md5}"
        ]
        
        # Mock the file read to return our test content
        with patch("builtins.open", mock_open(read_data=test_content)):
            result = server._check_device_file_hash("test.jar", "/data/local/tmp/u2.jar")
        
        # Verify the result is True (hash matches)
        assert result is True
        # Verify both commands were called
        assert mock_dev.shell.call_count == 2
        assert mock_dev.shell.call_args_list[0][0][0] == ["toybox", "md5sum", "/data/local/tmp/u2.jar"]
        assert mock_dev.shell.call_args_list[1][0][0] == ["md5", "/data/local/tmp/u2.jar"]
    
    def test_hash_mismatch(self, mock_server):
        """Test when the hash doesn't match"""
        server, mock_dev = mock_server
        
        # Create a temporary file with known content
        test_content = b"test content for md5"
        different_md5 = hashlib.md5(b"different content").hexdigest()
        
        # Mock the shell command to return a different hash
        mock_dev.shell.return_value = f"{different_md5}  /data/local/tmp/u2.jar"
        
        # Mock the file read to return our test content
        with patch("builtins.open", mock_open(read_data=test_content)):
            result = server._check_device_file_hash("test.jar", "/data/local/tmp/u2.jar")
        
        # Verify the result is False (hash doesn't match)
        assert result is False


def test_setup_jar_uses_explicit_local_path(tmp_path):
    jar_path = tmp_path / "fixed-u2.jar"
    jar_path.write_bytes(b"fixed jar")

    server = object.__new__(BasicUiautomatorServer)
    server._u2_jar_path = jar_path
    server._dev = Mock()
    server._check_device_file_hash = Mock(return_value=False)

    server._setup_jar()

    server._check_device_file_hash.assert_called_once_with(jar_path, "/data/local/tmp/u2.jar")
    server._dev.sync.push.assert_called_once_with(jar_path, "/data/local/tmp/u2.jar", check=True)


class TestCheckDeviceFileHashFallback:
    def test_md5_command_also_fails(self, mock_server):
        """Test when both toybox and md5 commands fail to find the file"""
        server, mock_dev = mock_server
        
        # Create a temporary file with known content
        test_content = b"test content for md5"
        
        # Mock the shell command to return errors for both commands
        mock_dev.shell.side_effect = [
            "toybox: not found",
            "md5: /data/local/tmp/u2.jar: No such file or directory"
        ]
        
        # Mock the file read to return our test content
        with patch("builtins.open", mock_open(read_data=test_content)):
            result = server._check_device_file_hash("test.jar", "/data/local/tmp/u2.jar")
        
        # Verify the result is False (file not found on device)
        assert result is False
