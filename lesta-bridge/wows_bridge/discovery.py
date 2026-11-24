"""Bounded Windows game discovery. No recursive whole-disk scans."""
import os
from pathlib import Path
import re
from .game_paths import active_build

EXECUTABLES = ('Korabli.exe', 'Korabli64.exe', 'WorldOfWarships.exe', 'WorldOfWarships64.exe')
FOLDER_NAMES = ('Korabli', 'World_of_Warships', 'World of Warships', 'World_of_Warships_RU', 'Мир кораблей')


def inspect_game(value):
    if not isinstance(value, str) or not value.strip():
        return {'valid': False, 'message': '请选择游戏安装目录。'}
    path = Path(os.path.expandvars(value.strip().strip('"'))).expanduser()
    if path.suffix.lower() == '.exe':
        path = path.parent
    # Accept an executable, bin64 or version directory as well as the root.
    for candidate in [path, *list(path.parents)[:5]]:
        try:
            builds = candidate / 'bin'
            if not builds.is_dir() or not any((candidate / name).is_file() for name in EXECUTABLES):
                continue
            latest, version_source = active_build(candidate)
            if latest is None:
                return {'valid': False, 'message': version_source}
            mod = latest / 'res_mods/PnFMods/BattleRecorder/Main.py'
            loader = latest / 'res_mods/PnFModsLoader.py'
            log = mod.with_name('damage_log.txt')
            return {'valid': True, 'path': str(candidate), 'version': latest.name,
                    'version_source': version_source,
                    'edition': 'Lesta / Мир кораблей' if (candidate / 'Korabli.exe').exists() else 'World of Warships',
                    'mod_installed': mod.is_file() and loader.is_file(), 'mod_path': str(mod),
                    'recorder_present': mod.is_file(), 'loader_present': loader.is_file(), 'loader_path': str(loader),
                    'log_exists': log.is_file(), 'log_path': str(log),
                    'message': '游戏目录有效'}
        except OSError:
            continue
    return {'valid': False, 'message': '未找到游戏主程序及 bin 版本目录，请选择包含 Korabli.exe 或 WorldOfWarships.exe 的文件夹。'}


def steam_candidates(steam_path):
    """Read only Steam library/install directory keys; preserve Unicode paths."""
    root = Path(steam_path)
    libraries = {root}
    try:
        text = (root / 'steamapps/libraryfolders.vdf').read_text(encoding='utf-8')
        for value in re.findall(r'"path"\s+"((?:\\.|[^"\\])*)"', text):
            libraries.add(Path(value.replace('\\\\', '\\').replace('\\"', '"')))
    except OSError:
        pass
    for library in libraries:
        manifest = library / 'steamapps/appmanifest_552990.acf'
        try:
            content = manifest.read_text(encoding='utf-8')
            match = re.search(r'"installdir"\s+"([^"\r\n]+)"', content)
            if match and not any(c in match.group(1) for c in ('/', '\\', ':')) and match.group(1) not in ('.', '..'):
                yield library / 'steamapps/common' / match.group(1)
        except OSError:
            pass
        yield library / 'steamapps/common/World of Warships'


def registry_candidates():
    if os.name != 'nt':
        return
    import winreg
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for branch in (r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
                       r'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'):
            try:
                with winreg.OpenKey(hive, branch) as key:
                    count = winreg.QueryInfoKey(key)[0]
                    for i in range(count):
                        try:
                            with winreg.OpenKey(key, winreg.EnumKey(key, i)) as item:
                                name = str(winreg.QueryValueEx(item, 'DisplayName')[0]).lower()
                                if any(t in name for t in ('world of warships', 'world_of_warships', 'korabli', 'мир кораблей', '战舰世界')):
                                    location = str(winreg.QueryValueEx(item, 'InstallLocation')[0])
                                    if location:
                                        yield location, 'Windows 已安装程序'
                        except OSError:
                            continue
            except OSError:
                pass
    for hive, branch, field in [(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam', 'SteamPath'),
            (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath')]:
        try:
            with winreg.OpenKey(hive, branch) as key:
                steam = winreg.QueryValueEx(key, field)[0]
                for candidate in steam_candidates(steam):
                    yield candidate, 'Steam 库'
        except OSError:
            pass


def common_candidates():
    if os.name != 'nt':
        return
    import ctypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetDriveTypeW.argtypes = [ctypes.c_wchar_p]
    mask = kernel.GetLogicalDrives()
    for i in range(26):
        drive = chr(65 + i) + ':\\'
        drive_type = kernel.GetDriveTypeW(drive)
        if not mask & (1 << i) or drive_type not in (3, 4):
            continue
        root = Path(drive)
        # Mapped game drives are common. Check a few conventional folders only;
        # never recurse through a network share or enumerate its whole contents.
        if drive_type == 4:
            for folder in ('', 'Games'):
                for name in FOLDER_NAMES:
                    yield root / folder / name, '映射盘常见目录'
            continue
        for folder in ('', 'Games', 'Lesta Games', 'Wargaming.net', 'Program Files', 'Program Files (x86)'):
            for name in FOLDER_NAMES:
                yield root / folder / name, '常见安装目录'
        for steam in (root / 'Steam', root / 'Program Files (x86)/Steam', root / 'SteamLibrary'):
            for candidate in steam_candidates(steam):
                yield candidate, 'Steam 库'


def discover(configured='', extra_candidates=()):
    candidates = [(configured, '已保存目录')] if configured else []
    candidates.extend(extra_candidates)
    candidates.extend(registry_candidates() or [])
    candidates.extend(common_candidates() or [])
    seen, found = set(), {}
    for candidate, source in candidates:
        key = os.path.normcase(str(candidate))
        if key in seen:
            continue
        seen.add(key)
        info = inspect_game(str(candidate))
        if info['valid']:
            normalized = os.path.normcase(os.path.abspath(info['path']))
            if normalized not in found:
                found[normalized] = dict(info, source=source)
    return list(found.values())


def browse_folder(initial=''):
    if os.name != 'nt':
        raise ValueError('当前系统不支持 Windows 目录选择器，请粘贴安装路径')
    import ctypes
    from ctypes import wintypes
    shell = ctypes.WinDLL('shell32', use_last_error=True)
    ole = ctypes.WinDLL('ole32', use_last_error=True)
    user = ctypes.WinDLL('user32', use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.UINT, wintypes.LPARAM, wintypes.LPARAM)
    class BrowseInfo(ctypes.Structure):
        _fields_ = [('hwndOwner', wintypes.HWND), ('pidlRoot', ctypes.c_void_p),
                    ('pszDisplayName', ctypes.c_wchar_p), ('lpszTitle', ctypes.c_wchar_p),
                    ('ulFlags', wintypes.UINT), ('lpfn', callback_type),
                    ('lParam', wintypes.LPARAM), ('iImage', ctypes.c_int)]
    ole.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole.CoInitializeEx.restype = ctypes.c_long
    ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    shell.SHBrowseForFolderW.argtypes = [ctypes.POINTER(BrowseInfo)]
    shell.SHBrowseForFolderW.restype = ctypes.c_void_p
    shell.SHGetPathFromIDListW.argtypes = [ctypes.c_void_p, wintypes.LPWSTR]
    shell.SHGetPathFromIDListW.restype = wintypes.BOOL
    user.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user.SendMessageW.restype = wintypes.LPARAM
    user.SetForegroundWindow.argtypes = [wintypes.HWND]
    initial_buffer = ctypes.create_unicode_buffer(initial)
    @callback_type
    def callback(hwnd, message, unused, data):
        if message == 1:
            if initial:
                user.SendMessageW(hwnd, 0x467, 1, ctypes.addressof(initial_buffer))
            user.SetForegroundWindow(hwnd)
        return 0
    result = ole.CoInitializeEx(None, 2)
    if result < 0:
        raise RuntimeError('无法初始化系统文件夹选择器，请粘贴路径')
    pidl = None
    try:
        display = ctypes.create_unicode_buffer(260)
        info = BrowseInfo(None, None, ctypes.cast(display, ctypes.c_wchar_p),
                          '选择战舰世界 / Мир кораблей 安装目录', 0x41, callback, 0, 0)
        pidl = shell.SHBrowseForFolderW(ctypes.byref(info))
        if not pidl:
            return ''
        selected = ctypes.create_unicode_buffer(32768)
        if not shell.SHGetPathFromIDListW(pidl, selected):
            raise RuntimeError('无法读取所选文件夹路径')
        return selected.value
    finally:
        if pidl:
            ole.CoTaskMemFree(pidl)
        ole.CoUninitialize()
