# -*- coding: utf-8 -*-
"""
Automatic dependency bootstrap for machine learning modules.
All code comments are in English.
"""
from .compat import enum_value, qt_exec, ml_dependency_requirements

import os
import sys
import site
import subprocess  # nosec B404
import importlib
from pathlib import Path
import sysconfig

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QMessageBox, QApplication
from qgis.core import QgsApplication


PLUGIN_PACKAGE_NAME = "bestfitinterpolator"


def dependency_directory(root, version=None, platform_tag=None):
    """Reuse legacy wheels only for their interpreter; isolate other binary ABIs."""
    root = Path(root)
    version = sys.version_info[:2] if version is None else version
    python_tag = 'cp{}{}'.format(*version[:2])
    platform_tag = (sysconfig.get_platform() if platform_tag is None else platform_tag).replace('-', '_').replace('.', '_')
    scoped = root / (python_tag + '_' + platform_tag)
    if scoped.is_dir():
        return str(scoped)
    wheels = list(root.glob('*.dist-info/WHEEL'))
    compatible = bool(wheels)
    for wheel in wheels:
        tags = [line[5:].strip().split('-') for line in wheel.read_text(encoding='utf-8').splitlines() if line.startswith('Tag: ')]
        accepted = any(len(tag) == 3 and ((tag[1:] == ['none', 'any'] and any(p in ('py3', python_tag) for p in tag[0].split('.')))
                       or (tag[0] == python_tag and tag[2] == platform_tag)) for tag in tags)
        if not accepted:
            compatible = False
            break
    return str(root if compatible else scoped)


def _deps_dir():
    """
    Return a writable directory for third-party Python packages.
    """
    base_dir = QgsApplication.qgisSettingsDirPath()
    deps_dir = os.path.join(
        base_dir,
        "python",
        "plugins",
        PLUGIN_PACKAGE_NAME,
        "_deps"
    )
    deps_dir = dependency_directory(deps_dir)
    os.makedirs(deps_dir, exist_ok=True)
    return deps_dir


def _add_deps_to_sys_path():
    """
    Add dependency directory to sys.path and site dirs.
    """
    deps_dir = _deps_dir()

    if deps_dir not in sys.path:
        sys.path.insert(0, deps_dir)

    if os.path.isdir(deps_dir):
        site.addsitedir(deps_dir)

    importlib.invalidate_caches()


def _candidate_python_paths():
    """
    Build a list of likely Python executable paths for the current QGIS install.
    """
    candidates = []

    if sys.executable and os.path.isfile(sys.executable):
        exe_name = os.path.basename(sys.executable).lower()
        if exe_name.startswith("python"):
            candidates.append(sys.executable)

    qgis_prefix = QgsApplication.prefixPath() or ""
    if qgis_prefix:
        qgis_prefix = os.path.normpath(qgis_prefix)
        app_root = os.path.dirname(qgis_prefix)
        install_root = os.path.dirname(app_root)

        candidates.extend([
            os.path.join(install_root, "bin", "python-qgis-ltr.bat"),
            os.path.join(install_root, "bin", "python-qgis.bat"),
            os.path.join(install_root, "apps", "Python312", "python.exe"),
            os.path.join(install_root, "apps", "Python311", "python.exe"),
            os.path.join(install_root, "apps", "Python310", "python.exe"),
            os.path.join(app_root, "Python312", "python.exe"),
            os.path.join(app_root, "Python311", "python.exe"),
            os.path.join(app_root, "Python310", "python.exe"),
        ])
        # Include the interpreter layout shipped by older supported QGIS builds.
        for python_tag in ("Python37","Python38","Python39"):
            candidates.append(os.path.join(install_root,"apps",python_tag,"python.exe"))
            candidates.append(os.path.join(app_root,python_tag,"python.exe"))

    exe_dir = os.path.dirname(sys.executable) if sys.executable else ""
    if exe_dir:
        candidates.extend([
            os.path.join(exe_dir, "python.exe"),
            os.path.abspath(os.path.join(exe_dir, "..", "python.exe")),
            os.path.abspath(os.path.join(exe_dir, "..", "apps", "Python312", "python.exe")),
            os.path.abspath(os.path.join(exe_dir, "..", "apps", "Python311", "python.exe")),
            os.path.abspath(os.path.join(exe_dir, "..", "apps", "Python310", "python.exe")),
            os.path.abspath(os.path.join(exe_dir, "..", "Python312", "python.exe")),
            os.path.abspath(os.path.join(exe_dir, "..", "Python311", "python.exe")),
            os.path.abspath(os.path.join(exe_dir, "..", "Python310", "python.exe")),
        ])

    seen = set()
    unique_candidates = []
    for path in candidates:
        norm = os.path.normpath(path)
        if norm not in seen:
            seen.add(norm)
            unique_candidates.append(norm)

    return [p for p in unique_candidates if os.path.isfile(p)]


def _find_python_executable():
    """
    Try to locate a Python executable compatible with the QGIS environment.
    """
    candidates = _candidate_python_paths()
    if not candidates:
        return None

    # On Windows, subprocess cannot reliably execute QGIS .bat launchers
    # directly. Prefer the real Python executable and keep launchers only as
    # a fallback for unusual installations.
    for path in candidates:
        if path.lower().endswith(".exe"):
            return path
    return candidates[0]


def _run_subprocess(command, parent=None):
    """
    Run a subprocess and return (success, stdout, stderr).
    """
    app = QApplication.instance()
    cursor_set = False

    try:
        if app is not None:
            app.setOverrideCursor(enum_value(Qt, "CursorShape", "WaitCursor"))
            cursor_set = True

        process = subprocess.run(  # nosec B603
            command,
            capture_output=True,
            text=True,
            check=False
        )
        return process.returncode == 0, process.stdout, process.stderr
    finally:
        if app is not None and cursor_set:
            try:
                app.restoreOverrideCursor()
            except Exception:  # nosec B110
                pass


def _ensure_pip(python_exe):
    """
    Ensure pip is available in the selected Python environment.
    """
    ok, _, _ = _run_subprocess([python_exe, "-m", "pip", "--version"])
    if ok:
        return True, ""

    ok, stdout, stderr = _run_subprocess([python_exe, "-m", "ensurepip", "--upgrade"])
    if not ok:
        return False, f"ensurepip failed.\n\nSTDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"

    ok, stdout, stderr = _run_subprocess([python_exe, "-m", "pip", "--version"])
    if not ok:
        return False, f"pip is still unavailable.\n\nSTDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"

    return True, ""


def _is_sklearn_available():
    """
    Check if scikit-learn can be imported.
    """
    try:
        import sklearn  # noqa: F401
        from sklearn.ensemble import RandomForestRegressor  # noqa: F401
        return True, ""
    except Exception as exc:
        return False, str(exc)


def install_ml_dependencies(parent=None):
    """
    Install machine learning dependencies into the plugin dependency folder.
    """
    # Prefer QGIS's own working scientific stack before adding local wheels.
    ok, _ = _is_sklearn_available()
    if ok:
        return True, ""
    _add_deps_to_sys_path()

    ok, _ = _is_sklearn_available()
    if ok:
        return True, ""

    python_exe = _find_python_executable()
    if not python_exe:
        return False, (
            "Could not locate the Python executable used by QGIS. "
            "Automatic dependency installation cannot continue."
        )

    ok, msg = _ensure_pip(python_exe)
    if not ok:
        return False, msg

    deps_dir = _deps_dir()

    packages = ml_dependency_requirements(sys.version_info)

    command = [
        python_exe,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-warn-script-location",
        "--prefer-binary",
        "--upgrade",
        "--target",
        deps_dir,
    ] + packages

    ok, stdout, stderr = _run_subprocess(command, parent=parent)
    if not ok:
        return False, (
            "Automatic installation of machine learning dependencies failed.\n\n"
            f"Python executable:\n{python_exe}\n\n"
            f"Target folder:\n{deps_dir}\n\n"
            f"STDOUT:\n{stdout}\n\n"
            f"STDERR:\n{stderr}"
        )

    _add_deps_to_sys_path()

    ok, err = _is_sklearn_available()
    if not ok:
        return False, (
            "Dependencies were installed, but scikit-learn still cannot be imported.\n\n"
            f"Import error:\n{err}"
        )

    return True, ""


def ensure_ml_ready(parent=None, method_name="Machine Learning"):
    """
    Ensure ML dependencies are ready. Ask the user once and install automatically.
    """
    ok, _ = _is_sklearn_available()
    if ok:
        return True
    _add_deps_to_sys_path()

    ok, _ = _is_sklearn_available()
    if ok:
        return True

    reply = QMessageBox.question(
        parent,
        f"{method_name} setup",
        (
            f"{method_name} needs additional Python packages the first time it runs.\n\n"
            "Do you want the plugin to install them automatically now?"
        ),
        enum_value(QMessageBox, "StandardButton", "Yes") | enum_value(QMessageBox, "StandardButton", "No"),
        enum_value(QMessageBox, "StandardButton", "Yes")
    )

    if reply != enum_value(QMessageBox, "StandardButton", "Yes"):
        return False

    ok, msg = install_ml_dependencies(parent=parent)
    if not ok:
        QMessageBox.critical(
            parent,
            f"{method_name} setup error",
            msg
        )
        return False

    QMessageBox.information(
        parent,
        f"{method_name} ready",
        (
            "Machine learning dependencies were installed successfully.\n"
            "The process will continue now."
        )
    )
    return True
