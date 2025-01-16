import asyncio
import glob
import logging
import os
import signal
import stat
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import flet_desktop
import flet_desktop.version
from flet.utils import (
    get_arch,
    is_linux,
    is_macos,
    is_windows,
    random_string,
    safe_tar_extractall,
)

logger = logging.getLogger(flet_desktop.__name__)

ver = flet_desktop.version.version
if not ver:
    import flet.version
    from flet.version import update_version

    ver = flet.version.version or update_version()


def get_package_bin_dir():
    return str(Path(__file__).parent.joinpath("app"))


def open_flet_view(page_url, assets_dir, hidden):
    args, flet_env, pid_file = __locate_and_unpack_flet_view(
        page_url, assets_dir, hidden
    )
    return subprocess.Popen(args, env=flet_env), pid_file


async def open_flet_view_async(page_url, assets_dir, hidden):
    args, flet_env, pid_file = __locate_and_unpack_flet_view(
        page_url, assets_dir, hidden
    )
    return (
        await asyncio.create_subprocess_exec(args[0], *args[1:], env=flet_env),
        pid_file,
    )


def close_flet_view(pid_file):
    if pid_file is not None and os.path.exists(pid_file):
        try:
            with open(pid_file) as f:
                fvp_pid = int(f.read())
            logger.debug(f"Flet View process {fvp_pid}")
            os.kill(fvp_pid, signal.SIGKILL)
        except Exception:
            pass
        finally:
            os.remove(pid_file)


def __locate_and_unpack_flet_view(page_url, assets_dir, hidden):
    logger.info("Starting Flet View app...")

    args = []

    # pid file - Flet client writes its process ID to this file
    pid_file = str(Path(tempfile.gettempdir()).joinpath(random_string(20)))

    if is_windows():
        exe_pattern = "*.exe"

        logger.info("Try loading Flet client from $PWD/build/windows")
        flet_path = glob.glob(
            os.path.join(os.getcwd(), "build", "windows", exe_pattern)
        )

        if not flet_path:
            logger.info("Check if Flet client exists in package's `bin` directory")
            flet_path = glob.glob(
                os.path.join(get_package_bin_dir(), "flet", exe_pattern)
            )

        if not flet_path:
            logger.info("Check if Flet client can be found at %FLET_VIEW_PATH% path")
            flet_view_path = os.environ.get("FLET_VIEW_PATH")
            if flet_view_path:
                flet_path = glob.glob(os.path.join(flet_view_path, exe_pattern))

        if not flet_path:
            logger.info(
                "Check if Flet client can be found at $HOME/.flet/bin directory"
            )
            temp_flet_dir = Path.home().joinpath(".flet", "bin", f"flet-{ver}")
            if not temp_flet_dir.exists():
                zip_file = __download_flet_client("flet-windows.zip")
                logger.info(f"Extracting flet.exe from archive to {temp_flet_dir}")
                temp_flet_dir.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(zip_file, "r") as zip_arch:
                    zip_arch.extractall(str(temp_flet_dir))
            flet_path = glob.glob(str(temp_flet_dir.joinpath("flet", exe_pattern)))
        logger.info(f"Flet client found at {flet_path[0]}")
        args = [flet_path[0], page_url, pid_file]
    elif is_macos():
        app_pattern = "*.app"

        logger.info("Try loading Flet client from $PWD/build/macos")
        flet_path = glob.glob(os.path.join(os.getcwd(), "build", "macos", app_pattern))

        if not flet_path:
            logger.info("Check if Flet client can be found at $FLET_VIEW_PATH path")
            flet_view_path = os.environ.get("FLET_VIEW_PATH")
            if flet_view_path:
                flet_path = glob.glob(os.path.join(flet_view_path, app_pattern))

        if not flet_path:
            logger.info(
                "Check if Flet client can be found at $HOME/.flet/bin directory"
            )
            temp_flet_dir = Path.home().joinpath(".flet", "bin", f"flet-{ver}")

            if not temp_flet_dir.exists():
                # check if flet.tar.gz exists
                gz_filename = "flet-macos.tar.gz"
                tar_file = os.path.join(get_package_bin_dir(), gz_filename)
                logger.info(f"Looking for Flet.app archive at: {tar_file}")
                if not os.path.exists(tar_file):
                    tar_file = __download_flet_client(gz_filename)

                logger.info(f"Extracting Flet.app from archive to {temp_flet_dir}")
                temp_flet_dir.mkdir(parents=True, exist_ok=True)
                with tarfile.open(str(tar_file), "r:gz") as tar_arch:
                    safe_tar_extractall(tar_arch, str(temp_flet_dir))

            flet_path = glob.glob(str(temp_flet_dir.joinpath(app_pattern)))
        logger.info(f"Flet client found at {flet_path[0]}")
        args = ["open", flet_path[0], "-n", "-W", "--args", page_url, pid_file]
    elif is_linux():

        def find_exe(path):
            result = []
            if os.path.exists(path):
                for f in os.listdir(path):
                    ef = os.path.join(path, f)
                    if os.path.isfile(ef) and stat.S_IXUSR & os.stat(ef)[stat.ST_MODE]:
                        result.append(ef)
            return result

        logger.info("Try loading Flet client from $PWD/build/linux")
        flet_path = find_exe(os.path.join(os.getcwd(), "build", "linux"))

        if not flet_path:
            logger.info("Check if Flet client can be found at $FLET_VIEW_PATH path")
            flet_view_path = os.environ.get("FLET_VIEW_PATH")
            if flet_view_path:
                flet_path = find_exe(os.path.join(flet_view_path))

        if not flet_path:
            logger.info(
                "Check if Flet client can be found at $HOME/.flet/bin directory"
            )
            temp_flet_dir = Path.home().joinpath(".flet", "bin", f"flet-{ver}")

            if not temp_flet_dir.exists():
                # check if flet.tar.gz exists
                gz_filename = f"flet-linux-{get_arch()}.tar.gz"
                tar_file = os.path.join(get_package_bin_dir(), gz_filename)
                logger.info(f"Looking for Flet bundle archive at: {tar_file}")
                if not os.path.exists(tar_file):
                    tar_file = __download_flet_client(gz_filename)

                logger.info(f"Extracting Flet from archive to {temp_flet_dir}")
                temp_flet_dir.mkdir(parents=True, exist_ok=True)
                with tarfile.open(str(tar_file), "r:gz") as tar_arch:
                    safe_tar_extractall(tar_arch, str(temp_flet_dir))

            flet_path = find_exe(str(temp_flet_dir.joinpath("flet")))
        logger.info(f"Flet client found at {flet_path[0]}")
        args = [flet_path[0], page_url, pid_file]

    flet_env = {**os.environ}

    if assets_dir:
        args.append(assets_dir)

    if hidden:
        flet_env["FLET_HIDE_WINDOW_ON_START"] = "true"

    return args, flet_env, pid_file


def __download_flet_client(file_name):
    temp_arch = Path(tempfile.gettempdir()).joinpath(file_name)
    flet_url = f"https://github.com/flet-dev/flet/releases/download/v{ver}/{file_name}"
    logger.info(f"Downloading Flet v{ver} from {flet_url} to {temp_arch}")
    urllib.request.urlretrieve(flet_url, temp_arch)
    return str(temp_arch)
