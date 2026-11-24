"""Portable Hub waveform validation and non-destructive library append."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time

import pyjson5


def read_document(raw, label):
    try:
        text = raw.decode('utf-8-sig')
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return pyjson5.decode(text)
    except (UnicodeError, pyjson5.Json5Exception, RecursionError) as error:
        raise ValueError(f'{label}不是有效的 UTF-8 JSON / JSON5 文件') from error


def validate_pulses(items):
    if isinstance(items, dict):
        items = [items] if 'pulseData' in items else items.get('pulseList')
    if not isinstance(items, list) or not 1 <= len(items) <= 1000:
        raise ValueError('波形文件须是包含 1～1000 项的 JSON 数组')
    seen, result = set(), []
    for position, item in enumerate(items, 1):
        if not isinstance(item, dict):
            raise ValueError('波形项须为对象')
        pid, name, data = item.get('id'), item.get('name'), item.get('pulseData')
        if 'id' in item and (not isinstance(pid, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', pid)):
            raise ValueError('波形 ID 仅允许字母、数字、点、下划线和连字符')
        label = pid or f'第 {position} 项'
        if not isinstance(name, str) or not name.strip() or len(name) > 128:
            raise ValueError(f'{label}: 名称为空或过长')
        if not isinstance(data, list) or not 1 <= len(data) <= 10000:
            raise ValueError(f'{label}: pulseData 必须是非空数组，最多 10000 帧')
        for index, frame in enumerate(data, 1):
            if not isinstance(frame, str) or not re.fullmatch('[0-9a-fA-F]{16}', frame):
                raise ValueError(f'{label} 第 {index} 帧：需要 16 位十六进制字符串')
            raw = bytes.fromhex(frame)
            if any(not 10 <= v <= 240 for v in raw[:4]) or any(v > 100 for v in raw[4:]):
                raise ValueError(f'{label} 第 {index} 帧：频率编码须为 10～240，幅度须为 0～100')
        frames = [frame.upper() for frame in data]
        if pid is None:
            pid = hashlib.md5(''.join(frames).encode('ascii'), usedforsecurity=False).hexdigest()[:8]
        if pid in seen:
            raise ValueError(f'文件内重复波形 ID: {pid}')
        seen.add(pid)
        result.append({'id': pid, 'name': name.strip(), 'pulseData': frames})
    return result


def append_library(path, incoming):
    path = Path(path)
    original = path.read_bytes()
    existing = read_document(original, '磁盘上的原波形库')
    if not isinstance(existing, list) or any(not isinstance(entry, dict) or not isinstance(entry.get('id'), str) for entry in existing):
        raise ValueError('原库格式异常，已取消导入，未改动文件')
    by_id = {entry['id']: entry for entry in existing}
    if len(by_id) != len(existing):
        raise ValueError('原库含重复 ID，已取消导入，未改动文件')
    added = []
    for item in incoming:
        previous = by_id.get(item['id'])
        if previous is None:
            added.append(item)
        elif not (isinstance(previous.get('pulseData'), list)
                  and all(isinstance(frame, str) for frame in previous['pulseData'])
                  and [frame.upper() for frame in previous['pulseData']] == item['pulseData']):
            raise ValueError(f"ID {item['id']} 已用于不同的波形数据，本次整批未写入")
    if not added:
        return []
    payload = json.dumps(existing + added, ensure_ascii=False, indent=2, allow_nan=False)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        if path.read_bytes() != original:
            raise ValueError('波形库已被其他程序修改，请刷新后重试')
        with path.with_name(f'{path.name}.{time.time_ns()}.bak').open('xb') as backup:
            backup.write(original)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return [item['id'] for item in added]
