"""Hide noninteractive Windows dependency and CPU-discovery subprocesses."""
import os
import subprocess  # nosec B404 - Used only for Windows startup flags/STARTUPINFO; no commands are constructed here.


def hidden_process_options():
    if os.name != 'nt':
        return {}
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    return dict(creationflags=subprocess.CREATE_NO_WINDOW, startupinfo=startup)


class _QuietCPUProbe:
    """Adapt only loky's subprocess reference, never the global subprocess API."""
    def __init__(self, original):
        self.original = original

    def __getattr__(self, name):
        return getattr(self.original, name)

    def run(self, *args, **kwargs):
        options = hidden_process_options()
        options['creationflags'] = kwargs.get('creationflags', 0) | options.get('creationflags', 0)
        for key, value in options.items():
            kwargs.setdefault(key, value)
        kwargs['creationflags'] |= options['creationflags']
        return self.original.run(*args, **kwargs)


def quiet_windows_cpu_probe():
    if os.name != 'nt':
        return
    try:
        from joblib.externals.loky.backend import context
    except ImportError:
        return
    if hasattr(context, 'subprocess') and not isinstance(context.subprocess, _QuietCPUProbe):
        context.subprocess = _QuietCPUProbe(context.subprocess)
