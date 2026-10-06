"""Shared QGIS3 profiles must not mix Python or 32/64-bit binary wheels."""
import tempfile
from pathlib import Path
from unittest.mock import patch
from bestfitinterpolator import ml_bootstrap as ml


def test_dependency_directories_preserve_matching_legacy_wheels_and_isolate_other_abis():
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)
        for name in ('numpy','scipy','scikit_learn'):
            info=root/(name+'-1.0.dist-info');info.mkdir()
            (info/'WHEEL').write_text('Wheel-Version: 1.0\nTag: cp37-cp37m-win32\n',encoding='utf-8')
        pure=root/'joblib-1.0.dist-info';pure.mkdir()
        (pure/'WHEEL').write_text('Tag: py2.py3-none-any\n',encoding='utf-8')
        assert ml.dependency_directory(root,(3,7),'win32')==str(root)
        assert ml.dependency_directory(root,(3,7),'win-amd64')==str(root/'cp37_win_amd64')
        assert ml.dependency_directory(root,(3,12),'win-amd64')==str(root/'cp312_win_amd64')
        assert ml.dependency_directory(root,(3,14),'win-amd64')==str(root/'cp314_win_amd64')
        # A newer scoped installation wins without moving or deleting legacy files.
        scoped=root/'cp37_win32';scoped.mkdir()
        assert ml.dependency_directory(root,(3,7),'win32')==str(scoped)
        assert (root/'numpy-1.0.dist-info/WHEEL').is_file()


def test_working_qgis_sklearn_is_used_before_adding_local_dependencies():
    with patch.object(ml,'_is_sklearn_available',return_value=(True,'')), patch.object(ml,'_add_deps_to_sys_path',side_effect=AssertionError('Do not add incompatible local packages')):
        assert ml.ensure_ml_ready()
        assert ml.install_ml_dependencies()==(True,'')
