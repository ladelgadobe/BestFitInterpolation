# -*- coding: utf-8 -*-
"""Provision third-party Python deps not bundled with QGIS, matching the
running interpreter.

Best Fit Interpolator needs the scikit-learn stack (scikit-learn, joblib,
threadpoolctl) for its machine-learning methods. Those are NOT shipped with
QGIS and compiled wheels are ABI-locked to the Python version, so a single
bundle breaks when QGIS ships a different Python. numpy/scipy/pandas/
matplotlib DO come with QGIS and must never be shadowed from extlibs/.

Strategy, in order:
  1. Download a prebuilt zip tagged for this Python+platform
     (``extlibs-<cpXY>-<platform>.zip``) from the GitHub release assets.
     No bundles are published yet — this step misses harmlessly.
  2. Fall back to running the QGIS Python's pip to install into ``extlibs/``.
  3. Otherwise report failure (the UI shows manual instructions).

The active build is recorded in ``extlibs/.ready`` together with its tag, so a
QGIS Python upgrade (different tag) re-provisions automatically.
"""
import hashlib
import importlib
import logging
import os
import shutil
import subprocess
import sys
import sysconfig
import urllib.request
import zipfile

from qgis.PyQt.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

# Prebuilt bundles are published as GitHub Release assets (not committed to the
# repo) so the plugin checkout stays small and the heavy zips never bloat git.
# Bump _EXTLIBS_RELEASE when a tagged release publishes the bundles.
_EXTLIBS_RELEASE = "extlibs-v1"
BASE_URL = (
    "https://github.com/farmanalytica/bestfitinterpolator/releases/download/"
    f"{_EXTLIBS_RELEASE}/"
)
_PLUGIN_DIR = os.path.dirname(__file__)
EXTLIBS_PATH = os.path.join(_PLUGIN_DIR, "extlibs")
_SENTINEL = os.path.join(EXTLIBS_PATH, ".ready")
_REQUIREMENTS = os.path.join(_PLUGIN_DIR, "requirements.txt")

# Deps shipped with QGIS itself — never keep them in extlibs/ (ABI shadowing).
_QGIS_PROVIDED = (
    "numpy", "pandas", "scipy", "matplotlib", "requests", "certifi",
    "urllib3", "idna", "charset_normalizer",
)

# Import names that MUST exist in extlibs/ for the ML methods to work, mapped
# to the pip requirement that supplies each. A prebuilt zip can be stale (deps
# added to requirements.txt after the bundle was built), so provisioning is
# judged by the presence of these packages, not merely by a successful zip
# extraction. Missing any -> the pip fallback fills the gap.
_REQUIRED_PACKAGES = {
    "sklearn": "scikit-learn",
    "joblib": "joblib",
    "threadpoolctl": "threadpoolctl",
}

# Legacy install target of the old ml_bootstrap.py flow: pip --target into the
# active profile's plugin dir. Not ABI-tagged, so a QGIS upgrade could load
# stale compiled wheels from it. Removed once on startup.
_LEGACY_DEPS_DIR = os.path.join(_PLUGIN_DIR, "_deps")

# Suppress the transient console window the pip subprocess would otherwise pop
# on Windows. 0 on POSIX (subprocess ignores it).
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _pkg_present(pkg: str) -> bool:
    """A package counts as present only when importable: a dir with
    __init__.py or a single-module .py. A bare dir is not enough — an
    interrupted upgrade (locked .pyd while QGIS holds the DLL) can leave a
    gutted package where only the compiled extension survived."""
    return (
        os.path.isfile(os.path.join(EXTLIBS_PATH, pkg, "__init__.py"))
        or os.path.isfile(os.path.join(EXTLIBS_PATH, pkg + ".py"))
    )


def _missing_pip_specs():
    """pip requirement strings for the required packages absent from extlibs/."""
    return [
        pip_name
        for pkg, pip_name in _REQUIRED_PACKAGES.items()
        if not _pkg_present(pkg)
    ]


_downloader = None


def current_tag() -> str:
    """e.g. 'cp312-win_amd64' for the running interpreter."""
    plat = sysconfig.get_platform().replace("-", "_").replace(".", "_")
    return f"cp{sys.version_info.major}{sys.version_info.minor}-{plat}"


def _req_fingerprint() -> str:
    """Short hash of requirements.txt so a dependency change re-provisions."""
    try:
        with open(_REQUIREMENTS, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()[:8]  # nosec B324
    except Exception:
        return ""


def _expected_sentinel() -> str:
    return current_tag() + "|" + _req_fingerprint()


def _read_ready_tag():
    try:
        with open(_SENTINEL, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return None


def is_ready() -> bool:
    """Provisioned for THIS interpreter AND this requirements set."""
    if not os.path.isfile(_SENTINEL):
        return False
    return _read_ready_tag() == _expected_sentinel()


def bundle_complete() -> bool:
    """True when every required package is present in extlibs/."""
    if not os.path.isdir(EXTLIBS_PATH):
        return False
    return all(_pkg_present(pkg) for pkg in _REQUIRED_PACKAGES)


def needs_provision() -> bool:
    _remove_legacy_deps()
    if not os.path.isdir(EXTLIBS_PATH):
        return True
    if not is_ready():
        return True
    # Sentinel can match while the bundle is missing newly-added packages.
    if not bundle_complete():
        return True
    return False


def _remove_legacy_deps():
    """One-time cleanup of the old ml_bootstrap _deps dir so stale, untagged
    compiled wheels never shadow the provisioned extlibs."""
    if not os.path.isdir(_LEGACY_DEPS_DIR):
        return
    try:
        shutil.rmtree(_LEGACY_DEPS_DIR)
        logger.info("Removed legacy _deps directory: %s", _LEGACY_DEPS_DIR)
    except Exception:
        logger.debug("Could not remove legacy _deps dir", exc_info=True)


def ensure_on_path():
    if EXTLIBS_PATH not in sys.path:
        sys.path.insert(0, EXTLIBS_PATH)
    # __init__.py may have inserted EXTLIBS_PATH while the dir was still empty
    # (pre-provision), poisoning Python's path-finder cache for that directory.
    importlib.invalidate_caches()


def get_downloader():
    return _downloader


def start_download():
    global _downloader
    if _downloader is not None and _downloader.isRunning():
        return _downloader
    _downloader = ExtlibsDownloader()
    _downloader.start()
    return _downloader


def _python_executable():
    """Best-effort path to the QGIS Python interpreter (not the GUI binary)."""
    cands = []
    base_exe = getattr(sys, "_base_executable", None)
    if base_exe:
        cands.append(base_exe)
    if os.name == "nt":
        cands.append(os.path.join(sys.base_exec_prefix, "python.exe"))
        cands.append(os.path.join(sys.exec_prefix, "python.exe"))
    else:
        cands.append(os.path.join(sys.base_exec_prefix, "bin", "python3"))
        cands.append(os.path.join(sys.exec_prefix, "bin", "python3"))
    for name in ("python3", "python"):
        w = shutil.which(name)
        if w:
            cands.append(w)
    for c in cands:
        if c and os.path.basename(c).lower().startswith("python") and os.path.exists(c):
            return c
    return None


def _strip_qgis_provided(target):
    """Remove QGIS-provided packages from a target dir (avoid ABI shadowing)."""
    try:
        for entry in os.listdir(target):
            low = entry.lower()
            if any(low == p or low.startswith(p + "-") or low.startswith(p + ".")
                   for p in _QGIS_PROVIDED):
                path = os.path.join(target, entry)
                shutil.rmtree(path, ignore_errors=True) if os.path.isdir(path) else os.remove(path)
    except Exception:
        logger.debug("Failed to remove QGIS-provided package from extlibs", exc_info=True)


class ExtlibsDownloader(QThread):
    download_done = pyqtSignal(bool, str)  # success, message

    def run(self):
        try:
            if bundle_complete():
                self._finish_ok()
                return
            # Step 1: fetch the prebuilt bundle (the ABI-locked compiled deps).
            self._try_tagged_zip()
            if bundle_complete():
                self._finish_ok()
                return
            # Step 2: the zip was unavailable for this tag, or it predates a
            # dependency added to requirements.txt. Fill the gaps with pip.
            self._try_pip()
            if bundle_complete():
                self._finish_ok()
                return
            self.download_done.emit(
                False,
                "Could not provision dependencies automatically for "
                f"{current_tag()}. Install the packages from requirements.txt "
                "in the QGIS Python environment manually.")
        except Exception as e:
            self.download_done.emit(False, str(e))

    # -- step 1: tagged prebuilt zip ------------------------------------
    def _try_tagged_zip(self) -> bool:
        url = BASE_URL + f"extlibs-{current_tag()}.zip"
        if not url.startswith("https://"):
            return False
        zip_path = os.path.join(_PLUGIN_DIR, "_extlibs_dl.zip")
        try:
            with urllib.request.urlopen(url) as resp, open(zip_path, "wb") as f:  # nosec B310
                f.write(resp.read())
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()
                if names and names[0].startswith("extlibs/"):
                    zf.extractall(_PLUGIN_DIR)
                else:
                    os.makedirs(EXTLIBS_PATH, exist_ok=True)
                    zf.extractall(EXTLIBS_PATH)
            return True
        except Exception:
            return False
        finally:
            if os.path.exists(zip_path):
                try:
                    os.remove(zip_path)
                except OSError:
                    pass

    # -- step 2: runtime pip into extlibs/ ------------------------------
    def _try_pip(self) -> bool:
        py = _python_executable()
        if not py or not os.path.exists(_REQUIREMENTS):
            return False
        os.makedirs(EXTLIBS_PATH, exist_ok=True)
        # Top up only the packages still missing rather than reinstalling the
        # whole requirements set on every launch.
        specs = _missing_pip_specs()
        install_args = specs if specs else ["-r", _REQUIREMENTS]
        try:
            subprocess.run(  # nosec B603
                [py, "-m", "pip", "install", "--target", EXTLIBS_PATH,
                 *install_args, "--no-warn-script-location"],
                check=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=_NO_WINDOW,  # don't flash a console on Windows
            )
        except Exception:
            return False
        _strip_qgis_provided(EXTLIBS_PATH)
        return True

    def _finish_ok(self):
        os.makedirs(EXTLIBS_PATH, exist_ok=True)
        with open(_SENTINEL, "w", encoding="utf-8") as f:
            f.write(_expected_sentinel())
        ensure_on_path()
        self.download_done.emit(True, "")
