#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""观察项台账校验（`cases/observations.jsonl`）。

为什么需要：台账没有校验就会退化成垃圾桶。三条准入判据（见
`cases/observations.md`）必须能被机器检查：

  1. 有可复现的现象  → `symptom` 非空且长度 ≥ 10，且含具体量值
  2. 写得出现象来源  → `probe` 非空且提到 example / 参数来源
  3. 写得出现缺什么  → `missing` 非空且不是空话

另校验：id 唯一且格式 `OB-YYYYMMDD-NN`、status 在枚举内、
`dismissed` 必须写理由、memcheck 类线索必须声明是否做过 K427 排除。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LEDGER = ROOT / 'cases' / 'observations.jsonl'

STATUSES = {'open', 'probing', 'promoted', 'dismissed'}
ID_RE = re.compile(r'^OB-\d{8}-\d{2}$')
# 「空话」黑名单：写了等于没写
VAGUE = ('需要进一步分析', '待定', '待查', '进一步确认', 'TBD', 'todo')


def check() -> int:
    if not LEDGER.exists():
        print('[observations] 台账不存在，跳过（不算错）')
        return 0

    errors: list[str] = []
    seen: set[str] = set()
    n = 0

    for lineno, raw in enumerate(LEDGER.read_text(encoding='utf-8').splitlines(), 1):
        raw = raw.strip()
        if not raw:
            continue
        n += 1
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append('第 %d 行 JSON 不可解析：%s' % (lineno, exc))
            continue

        rid = rec.get('id', '')
        if not ID_RE.match(rid):
            errors.append('第 %d 行 id 格式非法：%r（应为 OB-YYYYMMDD-NN）' % (lineno, rid))
        if rid in seen:
            errors.append('第 %d 行 id 重复：%s' % (lineno, rid))
        seen.add(rid)

        for f in ('date', 'op', 'repo', 'symptom', 'probe', 'missing', 'status'):
            if not str(rec.get(f, '')).strip():
                errors.append('%s 缺必填字段 %s' % (rid, f))

        st = rec.get('status')
        if st not in STATUSES:
            errors.append('%s status 非法：%r（允许：%s）'
                          % (rid, st, '/'.join(sorted(STATUSES))))

        # 判据 1：symptom 得含具体量值
        sym = str(rec.get('symptom', ''))
        if len(sym) < 10:
            errors.append('%s symptom 太短，写不出可复现现象（准入判据 1）' % rid)
        elif not re.search(r'\d', sym):
            errors.append('%s symptom 无具体量值（应含条数 / size / 地址特征）' % rid)

        # 判据 2：probe 得写参数来源
        probe = str(rec.get('probe', ''))
        if not re.search(r'example|\.cpp|params|shape|原值', probe):
            errors.append('%s probe 写不出参数来源（准入判据 2）' % rid)

        # 判据 3：missing 不能是空话
        missing = str(rec.get('missing', ''))
        if len(missing) < 8 or any(v in missing for v in VAGUE):
            errors.append('%s missing 写得太空（准入判据 3）' % rid)

        # memcheck 类线索必须声明 K427
        if re.search(r'illegal (read|write)|out of bounds', sym):
            if 'K427' not in missing and '哨兵' not in missing:
                errors.append('%s 是 memcheck OOB 线索但未声明是否做过 K427 排除'
                              '（防固仪：未排除前不得当越界）' % rid)

        # dismissed 必须写理由
        if st == 'dismissed' and len(str(rec.get('note', ''))) < 10:
            errors.append('%s 已标 dismissed 但 note 没写排除理由' % rid)

    if errors:
        print('[observations] %d 条错误：' % len(errors))
        for e in errors:
            print('  - ' + e)
        return 1

    print('[observations] OK | 条目=%d | 全部满足三条准入判据' % n)
    return 0


if __name__ == '__main__':
    sys.exit(check())
