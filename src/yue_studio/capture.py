"""Record one Windows process tree to a PCM16 WAV, then hand it to 识谱."""
from __future__ import annotations

import array
import ctypes
import sys
import threading
import time
import wave
from ctypes import POINTER, Structure, byref, c_void_p
from ctypes.wintypes import BOOL, DWORD, HANDLE, HWND, LPARAM, WORD
from dataclasses import dataclass
from pathlib import Path

SILENCE_PEAK = 16
MIN_SECONDS = 0.3
SILENCE_NOTE = "录音峰值接近静音。这个程序可能禁止回环采集，识谱结果可能没有声音。"

_CAPTURE_LOCK = threading.Lock()
_API = None


class CaptureError(RuntimeError):
    pass


@dataclass(frozen=True)
class SessionInfo:
    pid: int
    process_name: str
    display_name: str = ""


# DWMWA_CLOAKED. Shell cloak is how Windows hides a window on another virtual desktop.
DWM_CLOAKED_APP = 0x00000001
DWM_CLOAKED_SHELL = 0x00000002


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    pid: int
    title: str
    on_current_desktop: bool = True


@dataclass(frozen=True)
class CaptureTarget:
    pid: int
    label: str
    process_name: str
    value: str


@dataclass(frozen=True)
class Recording:
    path: Path
    pid: int
    label: str
    process_name: str
    duration: float
    silent: bool


def target_pid(value) -> int:
    text = str(value or "").strip()
    head = text.split(":", 1)[0]
    if not head.isdigit() or int(head) <= 0:
        raise CaptureError("请选择正在播放的窗口。")
    return int(head)


def window_listed(visible: bool, cloaked: int) -> bool:
    """Keep windows on other virtual desktops. Drop windows the app itself cloaked."""
    if not visible:
        return False
    return not (int(cloaked) & DWM_CLOAKED_APP)


def on_current_desktop(cloaked: int) -> bool:
    return not (int(cloaked) & DWM_CLOAKED_SHELL)


def capture_targets(sessions, windows, parents, stop_pids=()) -> list[CaptureTarget]:
    """One row per visible window. The recorded pid stays the audio session's."""
    by_pid: dict[int, list[WindowInfo]] = {}
    for window in windows:
        title = (window.title or "").strip()
        if not title:
            continue
        by_pid.setdefault(window.pid, []).append(
            WindowInfo(
                int(window.hwnd), int(window.pid), title, bool(window.on_current_desktop),
            ))
    for pid, items in by_pid.items():
        by_pid[pid] = sorted(items, key=lambda item: not item.on_current_desktop)
    targets = []
    seen = set()
    for session in _dedupe_sessions(sessions):
        if session.pid in seen or session.pid <= 0:
            continue
        seen.add(session.pid)
        name = session.process_name or f"pid {session.pid}"
        found = _display_windows(session.pid, by_pid, parents, stop_pids)
        if not found:
            targets.append(CaptureTarget(
                session.pid, f"{name} ({session.pid})", name, str(session.pid)))
            continue
        for window in found:
            title = window.title
            if not window.on_current_desktop:
                title = f"{title}（其他桌面）"
            label = f"{title} — {name}"
            if window.pid != session.pid:
                label = f"{label} ({session.pid})"
            value = str(session.pid) if len(found) == 1 else f"{session.pid}:{window.hwnd}"
            targets.append(CaptureTarget(session.pid, label, name, value))
    return targets


def floats_to_pcm16(samples) -> bytes:
    out = array.array("h")
    for value in samples:
        clamped = max(-1.0, min(1.0, float(value)))
        scaled = int(round(clamped * 32767))
        if scaled > 32767:
            scaled = 32767
        elif scaled < -32767:
            scaled = -32767
        out.append(scaled)
    return out.tobytes()


def pcm_from_mix(data: bytes, format_tag: int, bits: int, channels: int,
                 subformat: str | None = None) -> bytes:
    kind = _sample_kind(format_tag, bits, subformat)
    if kind == "pcm16":
        width = max(1, channels) * 2
        return data[: len(data) - (len(data) % width)]
    if kind == "float32":
        count = len(data) // 4
        floats = array.array("f")
        floats.frombytes(data[: count * 4])
        return floats_to_pcm16(floats)
    if kind == "pcm32":
        count = len(data) // 4
        ints = array.array("i")
        ints.frombytes(data[: count * 4])
        out = array.array("h")
        for sample in ints:
            shifted = int(sample) >> 16
            out.append(max(-32768, min(32767, shifted)))
        return out.tobytes()
    raise CaptureError(f"无法转换音频格式 tag={format_tag} bits={bits}")


def write_pcm16_wav(path: Path, sample_rate: int, channels: int, pcm: bytes) -> None:
    if sample_rate <= 0 or channels <= 0:
        raise CaptureError("无法写入 WAV：采样率或声道无效。")
    width = channels * 2
    if width <= 0 or len(pcm) % width:
        raise CaptureError("无法写入 WAV：采样数据长度和声道不一致。")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm)


def assess_pcm16(sample_rate: int, channels: int, pcm: bytes):
    width = channels * 2
    if sample_rate <= 0 or channels <= 0 or len(pcm) < width:
        return 0.0, 0, True
    frames = len(pcm) // width
    peak = pcm16_peak(pcm[: frames * width])
    return frames / sample_rate, peak, peak < SILENCE_PEAK


def pcm16_peak(pcm: bytes) -> int:
    even = len(pcm) - (len(pcm) % 2)
    if even <= 0:
        return 0
    samples = array.array("h")
    samples.frombytes(pcm[:even])
    peak = 0
    for sample in samples:
        value = sample if sample >= 0 else -int(sample)
        if value > peak:
            peak = value
    return peak


def require_usable(duration: float, frames: int) -> None:
    if frames <= 0 or duration < MIN_SECONDS:
        raise CaptureError("录音太短，没有保存。")


def new_capture_path() -> Path:
    from .paths import outputs_dir

    folder = outputs_dir() / "_capture"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = folder / f"capture-{stamp}.wav"
    if path.exists():
        path = folder / f"capture-{stamp}-{time.time_ns()}.wav"
    return path


def discard_capture(path: Path | None) -> None:
    if path is None:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def list_playing_windows() -> list[CaptureTarget]:
    _require_windows()
    sessions = _active_sessions()
    if not sessions:
        return []
    parents = _parent_pids(session.pid for session in sessions)
    return capture_targets(
        sessions, _visible_windows(), parents, _shell_pids(parents))


class Recorder:
    """One process-loopback capture. ``start`` returns after the device is open."""

    def __init__(self):
        self._lock = threading.Lock()
        self._thread = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._error = None
        self._result = None
        self._started = None
        self._label = ""
        self._process_name = ""
        self._pid = 0
        self._path = None
        self._frames = 0
        self._peak = 0

    def start(self, pid: int, process_name: str, label: str, dest: Path) -> None:
        _require_windows()
        if int(pid) <= 0:
            raise CaptureError("请选择正在播放的窗口。")
        _load_api()
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise CaptureError("已经在录音。")
            self._stop = threading.Event()
            self._ready = threading.Event()
            self._error = None
            self._result = None
            self._started = None
            self._label = label or process_name or str(pid)
            self._process_name = process_name or f"pid {pid}"
            self._pid = int(pid)
            self._path = Path(dest)
            self._frames = 0
            self._peak = 0
            self._thread = threading.Thread(
                target=self._run, args=(int(pid),), name="yue-capture", daemon=True)
            self._thread.start()
        if not self._ready.wait(timeout=8):
            self._stop.set()
            raise CaptureError("录音设备没有在时限内就绪。")
        if self._error is not None and self._started is None:
            self._thread.join(timeout=2)
            raise self._error

    def stop(self) -> Recording:
        with self._lock:
            thread = self._thread
            if thread is None or (
                    not thread.is_alive() and self._result is None and self._error is None
                    and self._started is None):
                raise CaptureError("当前没有在录音。")
            self._stop.set()
        thread.join(timeout=15)
        if thread.is_alive():
            raise CaptureError("录音线程没有及时结束。")
        with self._lock:
            result = self._result
            error = self._error
            self._thread = None
            self._result = None
            self._error = None
            self._started = None
        if result is not None:
            return result
        raise error or CaptureError("录音失败。")

    def status(self) -> str | None:
        with self._lock:
            if self._started is None or self._stop.is_set():
                return None
            elapsed = time.monotonic() - self._started
            label = self._label
        total = max(0, int(elapsed))
        minutes, secs = divmod(total, 60)
        return f"正在录制 {minutes}:{secs:02d} · {label}"

    def _run(self, pid: int):
        com_ready = False
        try:
            com_ready = _enter_mta()
            self._capture_loop(pid)
        except CaptureError as exc:
            self._fail(exc)
        except Exception as exc:
            self._fail(CaptureError(f"录音失败：{exc}"))
        finally:
            self._ready.set()
            if com_ready:
                _leave_mta()

    def _fail(self, exc: CaptureError):
        if self._error is None:
            self._error = exc

    def _capture_loop(self, pid: int):
        api = _load_api()
        client, capture, event, rate, channels, kind, subformat, bits, tag = api.open_loopback(pid)
        path = Path(self._path)
        block = channels * 2
        source_block = block if kind == "pcm16" else channels * 4
        try:
            try:
                with wave.open(str(path), "wb") as wav:
                    wav.setnchannels(channels)
                    wav.setsampwidth(2)
                    wav.setframerate(rate)
                    api.start(client)
                    with self._lock:
                        self._started = time.monotonic()
                    self._ready.set()
                    while not self._stop.is_set():
                        api.wait(event, 200)
                        self._drain(
                            api, capture, wav, block, source_block,
                            kind, tag, bits, channels, subformat)
                    api.stop(client)
                    self._drain(
                        api, capture, wav, block, source_block,
                        kind, tag, bits, channels, subformat)
            finally:
                api.close(client, event)
            self._finish(path, rate)
        except Exception:
            if self._result is None:
                discard_capture(path)
            raise

    def _drain(self, api, capture, wav, block, source_block, kind, tag, bits, channels, subformat):
        try:
            packets = api.read_packets(capture, source_block)
        except Exception as exc:
            if self._frames <= 0:
                raise CaptureError(f"录音中断：{exc}") from exc
            return
        for flags, raw, frames in packets:
            if frames <= 0:
                continue
            if kind == "pcm16":
                pcm = raw
            else:
                pcm = pcm_from_mix(raw, tag, bits, channels, subformat)
            if len(pcm) < frames * block:
                pcm = pcm + bytes(frames * block - len(pcm))
            pcm = pcm[: frames * block]
            wav.writeframes(pcm)
            self._frames += frames
            if not (flags & 0x2):
                self._peak = max(self._peak, pcm16_peak(pcm))

    def _finish(self, path: Path, rate: int):
        duration = self._frames / rate if rate else 0.0
        try:
            require_usable(duration, self._frames)
        except CaptureError:
            discard_capture(path)
            raise
        self._result = Recording(
            path=path,
            pid=self._pid,
            label=self._label,
            process_name=self._process_name,
            duration=duration,
            silent=self._peak < SILENCE_PEAK,
        )


def _dedupe_sessions(sessions) -> list[SessionInfo]:
    chosen: dict[int, SessionInfo] = {}
    order = []
    for session in sessions:
        current = chosen.get(session.pid)
        if current is None:
            chosen[session.pid] = session
            order.append(session.pid)
        elif not current.display_name and session.display_name:
            chosen[session.pid] = session
    return [chosen[pid] for pid in order]


def _display_windows(pid, windows_by_pid, parents, stop_pids=()) -> list[WindowInfo]:
    stop = {int(item) for item in (stop_pids or ())}
    seen = set()
    current = pid
    while current and current not in seen:
        # explorer's Program Manager is not the app that is playing audio.
        if current != pid and current in stop:
            return []
        seen.add(current)
        found = windows_by_pid.get(current) or []
        if found:
            return list(found)
        if len(seen) >= 8:
            break
        current = (parents or {}).get(current)
    return []


def _sample_kind(format_tag: int, bits: int, subformat: str | None) -> str:
    if format_tag == 0xFFFE:
        if subformat == "float" and bits == 32:
            return "float32"
        if subformat == "pcm" and bits == 16:
            return "pcm16"
        if subformat == "pcm" and bits == 32:
            return "pcm32"
        return "other"
    if format_tag == 3 and bits == 32:
        return "float32"
    if format_tag == 1 and bits == 16:
        return "pcm16"
    if format_tag == 1 and bits == 32:
        return "pcm32"
    return "other"


def _require_windows():
    if sys.platform != "win32":
        raise CaptureError("录音只支持 Windows。")


def _parent_pids(pids) -> dict[int, int | None]:
    import psutil

    mapping: dict[int, int | None] = {}
    pending = [int(pid) for pid in pids if int(pid) > 0]
    while pending:
        pid = pending.pop()
        if pid in mapping:
            continue
        try:
            parent = psutil.Process(pid).parent()
        except psutil.Error:
            mapping[pid] = None
            continue
        parent_pid = int(parent.pid) if parent is not None else None
        mapping[pid] = parent_pid
        if parent_pid and parent_pid not in mapping:
            pending.append(parent_pid)
        if len(mapping) > 64:
            break
    return mapping


def _shell_pids(parents) -> set[int]:
    import psutil

    pids = {int(pid) for pid in parents if int(pid) > 0}
    pids.update(int(parent) for parent in parents.values() if parent)
    shell = set()
    for pid in pids:
        try:
            name = psutil.Process(pid).name()
        except (psutil.Error, OSError, ValueError):
            continue
        if name.lower() == "explorer.exe":
            shell.add(pid)
    return shell


def _visible_windows() -> list[WindowInfo]:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.IsWindowVisible.argtypes = [HWND]
    user32.IsWindowVisible.restype = BOOL
    user32.GetWindowTextLengthW.argtypes = [HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [HWND, ctypes.c_wchar_p, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = [HWND, POINTER(DWORD)]
    user32.GetWindowThreadProcessId.restype = DWORD
    try:
        dwmapi = ctypes.WinDLL("dwmapi")
        dwmapi.DwmGetWindowAttribute.argtypes = [
            HWND, DWORD, c_void_p, DWORD]
        dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long
    except OSError:
        dwmapi = None
    found: list[WindowInfo] = []

    def each(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        cloaked = 0
        if dwmapi is not None:
            cloaked_value = DWORD()
            if dwmapi.DwmGetWindowAttribute(
                    hwnd, 14, byref(cloaked_value), ctypes.sizeof(cloaked_value)) == 0:
                cloaked = int(cloaked_value.value)
        if not window_listed(True, cloaked):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value.strip()
        if not title:
            return True
        pid = DWORD()
        user32.GetWindowThreadProcessId(hwnd, byref(pid))
        if pid.value:
            found.append(WindowInfo(
                int(hwnd), int(pid.value), title, on_current_desktop(cloaked)))
        return True

    callback = ctypes.WINFUNCTYPE(BOOL, HWND, LPARAM)(each)
    user32.EnumWindows(callback, 0)
    return found


def _active_sessions() -> list[SessionInfo]:
    import comtypes
    from pycaw.constants import DEVICE_STATE, AudioSessionState, EDataFlow
    from pycaw.utils import AudioUtilities

    comtypes.CoInitialize()
    try:
        speakers = AudioUtilities.GetSpeakers()
        found = _device_sessions(speakers, AudioSessionState.Active) if speakers is not None else []
        if found:
            return _dedupe_sessions(found)
        for device in AudioUtilities.GetAllDevices(
                EDataFlow.eRender.value, DEVICE_STATE.ACTIVE.value):
            found.extend(_device_sessions(device, AudioSessionState.Active))
        return _dedupe_sessions(found)
    finally:
        comtypes.CoUninitialize()


def _device_sessions(device, active_state) -> list[SessionInfo]:
    from pycaw.api.audiopolicy import IAudioSessionControl2
    from pycaw.utils import AudioSession

    manager = device.AudioSessionManager
    enumerator = manager.GetSessionEnumerator()
    count = int(enumerator.GetCount())
    found = []
    for index in range(count):
        control = enumerator.GetSession(index)
        if control is None:
            continue
        session = AudioSession(control.QueryInterface(IAudioSessionControl2))
        try:
            if int(session.State) != int(active_state):
                continue
            pid = int(session.ProcessId)
            process = session.Process
        except (OSError, ValueError):
            continue
        if pid <= 0 or process is None:
            continue
        try:
            name = process.name()
        except Exception:
            continue
        try:
            display = session.DisplayName or ""
        except Exception:
            display = ""
        found.append(SessionInfo(pid, name, display))
    return found


def _enter_mta() -> bool:
    ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    ole32.CoInitializeEx.argtypes = [c_void_p, DWORD]
    ole32.CoInitializeEx.restype = ctypes.c_long
    hr = int(ole32.CoInitializeEx(None, 0))
    if hr in (0, 1):
        return True
    if hr & 0xFFFFFFFF == 0x80010106:
        raise CaptureError("录音线程的 COM 模式冲突。")
    raise CaptureError(f"无法初始化录音线程（{_hresult_text(hr)}）。")


def _leave_mta():
    ctypes.WinDLL("ole32").CoUninitialize()


def _hresult_text(hr: int) -> str:
    code = int(hr) & 0xFFFFFFFF
    signed = code - 0x100000000 if code >= 0x80000000 else code
    try:
        detail = ctypes.FormatError(signed).strip()
    except (OSError, OverflowError):
        detail = ""
    return f"{code:#010x} {detail}".strip()


def _load_api():
    global _API
    with _CAPTURE_LOCK:
        if _API is None:
            _API = _build_api()
        return _API


def _build_api():
    from _ctypes import COMError
    from ctypes import HRESULT, c_byte, c_uint32, c_uint64

    import comtypes
    from comtypes import COMMETHOD, COMObject, GUID, IUnknown

    from pycaw.api.audioclient import IAudioClient
    from pycaw.api.audioclient.depend import WAVEFORMATEX

    class IAudioCaptureClient(IUnknown):
        _iid_ = GUID("{C8ADBD64-E71E-48a0-A4DE-185C395CD317}")
        _methods_ = (
            COMMETHOD(
                [], HRESULT, "GetBuffer",
                (["out"], POINTER(POINTER(c_byte)), "ppData"),
                (["out"], POINTER(c_uint32), "pNumFramesToRead"),
                (["out"], POINTER(DWORD), "pdwFlags"),
                (["out"], POINTER(c_uint64), "pu64DevicePosition"),
                (["out"], POINTER(c_uint64), "pu64QPCPosition"),
            ),
            COMMETHOD([], HRESULT, "ReleaseBuffer", (["in"], c_uint32, "NumFramesRead")),
            COMMETHOD(
                [], HRESULT, "GetNextPacketSize",
                (["out"], POINTER(c_uint32), "pNumFramesInNextPacket"),
            ),
        )

    class IActivateAudioInterfaceAsyncOperation(IUnknown):
        _iid_ = GUID("{72A22D78-CDE4-431D-B8CC-843A71199B6D}")
        _methods_ = (
            COMMETHOD(
                [], HRESULT, "GetActivateResult",
                (["out"], POINTER(HRESULT), "activateResult"),
                (["out"], POINTER(POINTER(IUnknown)), "activatedInterface"),
            ),
        )

    class IActivateAudioInterfaceCompletionHandler(IUnknown):
        _iid_ = GUID("{41D949AB-9862-444A-80F6-C261334DA5EB}")
        _methods_ = (
            COMMETHOD(
                [], HRESULT, "ActivateCompleted",
                (["in"], POINTER(IActivateAudioInterfaceAsyncOperation), "operation"),
            ),
        )

    class ActivationParams(Structure):
        _fields_ = [
            ("ActivationType", DWORD),
            ("TargetProcessId", DWORD),
            ("ProcessLoopbackMode", DWORD),
        ]

    class Blob(Structure):
        _fields_ = [("cbSize", DWORD), ("pBlobData", c_void_p)]

    class PropVariant(Structure):
        _fields_ = [
            ("vt", WORD),
            ("reserved1", WORD),
            ("reserved2", WORD),
            ("reserved3", WORD),
            ("blob", Blob),
        ]

    iid_marshal = GUID("{00000003-0000-0000-C000-000000000046}")
    iid_agile = GUID("{94EA2B94-E9CC-49E0-C0FF-EE64CA8F5B90}")
    from _ctypes import CopyComPointer

    class ActivateHandler(COMObject):
        _com_interfaces_ = [IActivateAudioInterfaceCompletionHandler]

        def __init__(self):
            super().__init__()
            self.done = threading.Event()
            self.client = None
            self.error = None
            self._ftm = POINTER(IUnknown)()
            # Keep the queried pointer alive. Releasing the last reference
            # clears the COM vtable, and the marshaler must see the raw pointer.
            self._outer = self.QueryInterface(IUnknown)
            hr = int(create_ftm(ctypes.cast(self._outer, c_void_p), byref(self._ftm)))
            if hr < 0 or not self._ftm:
                self._ftm = None
                self.error = CaptureError(
                    f"无法创建自由线程封送（{_hresult_text(hr)}）。")
            elif int(self._refcnt.value) >= 2:
                self._outer.Release()
                self._outer = None

        def IUnknown_QueryInterface(self, this, riid, ppvObj):
            iid = riid[0]
            if iid == iid_agile:
                return CopyComPointer(self._com_pointers_[IUnknown._iid_], ppvObj)
            ftm = getattr(self, "_ftm", None)
            if ftm is not None and iid == iid_marshal:
                marshal = POINTER(IUnknown)()
                code = int(ftm.QueryInterface(riid, byref(marshal)))
                if code < 0:
                    return code
                return CopyComPointer(marshal, ppvObj)
            return COMObject.IUnknown_QueryInterface(self, this, riid, ppvObj)

        def ActivateCompleted(self, operation):
            try:
                activate_hr, unknown = operation.GetActivateResult()
                code = int(activate_hr)
                if code < 0:
                    self.error = CaptureError(
                        f"无法录制该进程（{_hresult_text(code)}）。它可能已经退出，或系统拒绝了回环采集。")
                elif unknown is None:
                    self.error = CaptureError("录音接口没有返回音频客户端。")
                else:
                    self.client = unknown.QueryInterface(IAudioClient)
            except Exception as exc:
                self.error = CaptureError(f"录音接口激活失败：{exc}")
            finally:
                self.done.set()

    mmdevapi = ctypes.WinDLL("mmdevapi", use_last_error=True)
    activate_async = mmdevapi.ActivateAudioInterfaceAsync
    activate_async.argtypes = [
        ctypes.c_wchar_p,
        POINTER(GUID),
        POINTER(PropVariant),
        POINTER(IActivateAudioInterfaceCompletionHandler),
        POINTER(POINTER(IActivateAudioInterfaceAsyncOperation)),
    ]
    activate_async.restype = ctypes.c_long
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateEventW.argtypes = [c_void_p, BOOL, BOOL, ctypes.c_wchar_p]
    kernel32.CreateEventW.restype = HANDLE
    kernel32.WaitForSingleObject.argtypes = [HANDLE, DWORD]
    kernel32.WaitForSingleObject.restype = DWORD
    kernel32.CloseHandle.argtypes = [HANDLE]
    kernel32.CloseHandle.restype = BOOL
    ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    create_ftm = ole32.CoCreateFreeThreadedMarshaler
    create_ftm.argtypes = [c_void_p, POINTER(POINTER(IUnknown))]
    create_ftm.restype = ctypes.c_long

    convert_flags = 0x00020000 | 0x00040000 | 0x80000000

    def open_loopback(pid: int):
        params = ActivationParams()
        params.ActivationType = 1
        params.TargetProcessId = int(pid)
        params.ProcessLoopbackMode = 0
        variant = PropVariant()
        variant.vt = 65
        variant.blob.cbSize = ctypes.sizeof(params)
        variant.blob.pBlobData = ctypes.addressof(params)
        handler = ActivateHandler()
        if handler.error is not None:
            raise handler.error
        handler_ptr = handler.QueryInterface(IActivateAudioInterfaceCompletionHandler)
        async_op = POINTER(IActivateAudioInterfaceAsyncOperation)()
        hr = int(activate_async(
            "VAD\\Process_Loopback",
            byref(IAudioClient._iid_),
            byref(variant),
            handler_ptr,
            byref(async_op),
        ))
        if hr < 0:
            raise CaptureError(f"无法打开进程回环（{_hresult_text(hr)}）。")
        if not handler.done.wait(timeout=8):
            raise CaptureError("录音接口没有完成激活。")
        if handler.error is not None:
            raise handler.error
        client = handler.client
        # Process loopback does not implement GetMixFormat. Ask the engine
        # to convert into 16-bit PCM, as the Application Loopback sample does.
        del params, variant, handler, handler_ptr, async_op
        pcm = WAVEFORMATEX()
        pcm.wFormatTag = 1
        pcm.nChannels = 2
        pcm.nSamplesPerSec = 48000
        pcm.wBitsPerSample = 16
        pcm.nBlockAlign = 4
        pcm.nAvgBytesPerSec = 48000 * 4
        pcm.cbSize = 0
        try:
            client.Initialize(0, convert_flags, 0, 0, byref(pcm), None)
        except (COMError, OSError):
            pcm.nSamplesPerSec = 44100
            pcm.nAvgBytesPerSec = 44100 * 4
            client.Initialize(0, convert_flags, 0, 0, byref(pcm), None)
        channels, rate = int(pcm.nChannels), int(pcm.nSamplesPerSec)
        kind, tag, bits, subformat = "pcm16", 1, 16, None
        unknown = client.GetService(byref(IAudioCaptureClient._iid_))
        capture = unknown.QueryInterface(IAudioCaptureClient)
        event = kernel32.CreateEventW(None, False, False, None)
        if not event:
            raise CaptureError("无法创建录音事件。")
        client.SetEventHandle(event)
        return client, capture, event, rate, channels, kind, subformat, bits, tag

    def read_packets(capture, source_block):
        packets = []
        while True:
            packet = int(capture.GetNextPacketSize() or 0)
            if packet <= 0:
                return packets
            data, frames, flags, _device, _qpc = capture.GetBuffer()
            frames = int(frames)
            flags = int(flags or 0)
            try:
                if flags & 0x2 or frames <= 0:
                    raw = b""
                else:
                    address = ctypes.cast(data, c_void_p).value
                    raw = b"" if not address else ctypes.string_at(
                        address, frames * source_block)
            finally:
                capture.ReleaseBuffer(frames)
            packets.append((flags, raw, frames))

    def start(client):
        client.Start()

    def stop(client):
        try:
            client.Stop()
        except COMError:
            pass

    def wait(event, timeout):
        kernel32.WaitForSingleObject(event, int(timeout))

    def close(client, event):
        try:
            client.Stop()
        except Exception:
            pass
        if event:
            kernel32.CloseHandle(event)

    return type("LoopbackApi", (), {
        "open_loopback": staticmethod(open_loopback),
        "read_packets": staticmethod(read_packets),
        "start": staticmethod(start),
        "stop": staticmethod(stop),
        "wait": staticmethod(wait),
        "close": staticmethod(close),
    })()
