import psutil
import os
import subprocess


def GetUSBInfo(usb_path: str) -> dict:  # [ANNOTATION] Add type hint to parameter.
    try:
        normalized_usb_path = os.path.normpath(usb_path)

        for part in psutil.disk_partitions(all=True):  # [ANNOTATION] Pass all=True for consistency with find_usb/check_file_sig; avoids missing bind-mounted USB volumes.
            if os.path.normpath(part.mountpoint) == normalized_usb_path:
                device_node = part.device
                break
        else:  # [ANNOTATION] Use for/else to eliminate the separate device_node=None initialisation and post-loop None check.
            print(f"Could not find device node for USB path: {usb_path}")
            return {}

        size_output = subprocess.check_output(
            ["lsblk", "-d", "-n", "-b", "-o", "SIZE", device_node],
            text=True,
            timeout=5,
        ).strip()

        usb_size = int(size_output) if size_output.isdigit() else 0  # [ANNOTATION] Inline the digit check; avoids a print on a zero-size result that is handled below.
        if not size_output.isdigit():
            print(f"Warning: could not parse device size: {size_output!r}")

        if usb_size > 32 * 1024**3:
            print(f"USB device is large ({usb_size} bytes); confirm before flashing.")

        label = subprocess.check_output(
            ["lsblk", "-d", "-n", "-o", "LABEL", device_node], text=True, timeout=5
        ).strip()
        if not label:
            label = os.path.basename(usb_path)

        usb_info = {
            "device_node": device_node,
            "label": label,
            "mount_path": normalized_usb_path,  # [ANNOTATION] Return the normalised path so callers comparing with normpath() results get a consistent value.
        }
        print(f"USB Info: {usb_info}")
        return usb_info
    except subprocess.TimeoutExpired as e:  # [ANNOTATION] Catch TimeoutExpired explicitly before the broad Exception so the error message is informative.
        print(f"Timed out getting USB info for {usb_path}: {e}")
        return {}
    except PermissionError:
        print(f"Permission denied when trying to get USB info: {usb_path}")
        return {}
    except subprocess.CalledProcessError as e:
        print(f"Error getting USB info: {e}")
        return {}
    except Exception as err:
        print(f"Unexpected error getting USB info: {err}")
        return {}
