"""Synthetic V4 protocol fixtures only; never used for real-source Agent runs."""
import copy

from faultaudit.trigger_v4 import CLASS_IDS, canonical_conditions


def markdown():
    codes = [["synthetic_code_" + str(i)] for i in range(31)]
    for i in range(24):
        codes[i].append("synthetic_code_" + str(i + 31))
    for i in range(9):
        codes[30 - i].append("synthetic_code_" + str(i))
    lines = ["# 合成V4定义（仅协议测试）", "", "## D 退化输入", ""]
    for i, key in enumerate(CLASS_IDS):
        lines += [f"### {key} 合成类别{key}", "- **条件定义**：合成接口条件" + key,
            "- **检验目的**：合成目的", "- **适用前提（Requires）**：合成语义前提" + key,
            "- **跳过/能力限制（Skip if）**：合成语义排除" + key, ""]
        for code in codes[i]:
            lines += [f"  - `{code}` — **合成构造{code}**：合成构造定义{code}"]
        for n in range(7 if i < 9 else 6):
            lines += [f"{n+1}. **{key}-{n+1:02}**：**合成指导。**合成输入及参考，无实际网站或执行。"]
        lines += [""]
    lines += ["## 同步与状态相关的执行方法", ""]
    for n in range(1, 6):
        lines += [f"### E{n} 合成方法{n}", "合成执行规程；未实机执行。", ""]
    return "\n".join(lines)


def v4_unknown(payload, response):
    out = copy.deepcopy(response)
    rows = []
    for item in payload['v4_taxonomy']['items']:
        construction = {c['id']: c for c in payload['v4_taxonomy']['constructions']}
        rows.append({'trigger_id': item['id'], 'applicability': 'UNKNOWN', 'relation': 'UNKNOWN',
            'evidence_basis': 'UNKNOWN', 'reason': '合成测试未给出该条件',
            'predicate_checks': [{'clause_role': role, 'clause': text, 'result': 'UNKNOWN'}
                for role, text in sorted(canonical_conditions(item))],
            'coverage': {'construction': 'UNKNOWN', 'construction_reason': '未声明执行器能力',
                'path': 'UNKNOWN', 'path_reason': '本阶段仅分类及设计', 'execution': 'NOT_RUN'},
            'construction_checks': [{'construction_id': key, 'applicability': 'UNKNOWN',
                'definition_check': {'clause': construction[key]['definition'], 'result': 'UNKNOWN'},
                'reason': '合成测试无该构造条件'} for key in item['construction_ids']],
            'unknowns': ['未给出输入和具体实现条件']})
    out['v4_rows'] = rows
    return out
