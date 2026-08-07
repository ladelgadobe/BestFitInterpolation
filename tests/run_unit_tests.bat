@echo off
REM Run the headless unit tier in any Python that has requirements_test.txt
REM installed (numpy, scipy, scikit-learn, matplotlib, pytest).
setlocal
cd /d "%~dp0.."
python -m pytest tests\unit -q %*
