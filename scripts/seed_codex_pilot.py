"""Create synthetic semantic-pilot inputs, never model answers or audit state.

The separate expectations file is for the acceptance checker. Do not include it
in model tasks: the executor should judge only the imported source and evidence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
URLS = {
    "allreduce": "https://example.invalid/wiki/sim-allreduce-101",
    "quant": "https://example.invalid/wiki/sim-quant-900",
    "shared_wiki": "https://example.invalid/wiki/sim-attention-rope",
    "shared_dts": "https://example.invalid/dts/sim-rope-303",
    "partial_pr": "https://example.invalid/project/pulls/606",
}


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def source_cases() -> list[dict]:
    return [
        {"统一ID": "SIM-001", "事件编号": "SIM-AR-101", "客户/模型": "合成客户甲 / SYNTH-MODEL-A",
         "问题描述": "SIM-AR-101：PCIe链路、TP6场景下，all_reduce输出产生舍入精度偏差并导致文本乱码。",
         "算子": "all_reduce", "根因/进展": "原始记录：PCIe分段归约使用低精度累加引入舍入偏差；等待证据核验。",
         "触发条件": "PCIe链路，TP6，低精度累加", "wiki": URLS["allreduce"], "相关证据链接": URLS["quant"]},
        {"统一ID": "SIM-002", "事件编号": "SIM-ATTN-202", "客户/模型": "合成客户乙 / SYNTH-MODEL-B",
         "问题描述": "SIM-ATTN-202：FP8 Attention静态量化时首Token乱码，怀疑V scale读取偏移。",
         "算子": "FP8 Attention", "根因/进展": "原始记录：V scale按错误head索引读取；等待证据核验。",
         "触发条件": "FP8静态量化，V scale按head分组", "wiki": URLS["shared_wiki"]},
        {"统一ID": "SIM-003", "事件编号": "SIM-ROPE-303", "客户/模型": "合成客户乙 / SYNTH-MODEL-B",
         "问题描述": "SIM-ROPE-303：RoPE Norm入参H2D后重复推理结果不确定，涉及pin_memory缓冲区生命周期。",
         "算子": "RoPE Norm", "根因/进展": "原始记录：异步H2D尚未完成，pin_memory缓冲区已复用；等待证据核验。",
         "触发条件": "异步H2D，pin_memory缓冲区复用", "wiki": URLS["shared_wiki"], "DTS链接": URLS["shared_dts"]},
        {"统一ID": "SIM-004", "事件编号": "SIM-VERL-404", "客户/模型": "合成客户丙 / SYNTH-MODEL-C",
         "问题描述": "SIM-VERL-404：verl rollout经过sleep/wakeup后出现乱码，排查MLA中的sin/cos cache恢复。",
         "算子": "MLA / RoPE embedding", "根因/进展": "原始记录仅有排查方向：sleep/wakeup后的sin/cos cache；尚无根因确认或修复验证。",
         "触发条件": "verl rollout，sleep/wakeup", "DTS链接": URLS["shared_dts"]},
        {"统一ID": "SIM-005", "事件编号": "SIM-NORM-505", "客户/模型": "合成客户丁 / SYNTH-MODEL-D",
         "问题描述": "SIM-NORM-505：rms_norm在连续输入、BF16长向量归约时出现累加精度偏差。",
         "算子": "rms_norm", "根因/进展": "原始记录：待确认BF16累加路径；尚未取得对应补丁及修复验证。",
         "触发条件": "连续输入，BF16长向量归约", "PR": URLS["partial_pr"]},
    ]


def catalog_rows() -> list[dict]:
    rows = [
        {"item_id": "F-001", "description": "合成模式：AllReduce低精度分段归约舍入偏差", "operator": "all_reduce",
         "mechanism": "PCIe分段归约使用低精度累加，引入舍入偏差", "trigger": "PCIe链路，TP6，低精度累加"},
        {"item_id": "F-002", "description": "合成模式：FP8 Attention读取错误V scale", "operator": "FP8 Attention",
         "mechanism": "V scale按错误head索引读取", "trigger": "FP8静态量化，V scale按head分组"},
        {"item_id": "F-003", "description": "合成模式：RoPE Norm异步H2D缓冲区提前复用", "operator": "RoPE Norm",
         "mechanism": "异步H2D尚未完成，pin_memory缓冲区已复用", "trigger": "异步H2D，pin_memory缓冲区复用"},
        {"item_id": "F-004", "description": "合成模式：sleep/wakeup后sin/cos缓存恢复遗漏", "operator": "MLA / RoPE embedding",
         "mechanism": "sleep/wakeup恢复时遗漏sin/cos cache重建", "trigger": "verl rollout，sleep/wakeup"},
        {"item_id": "F-005", "description": "合成模式：rms_norm连续长向量BF16累加精度偏差", "operator": "rms_norm",
         "mechanism": "连续长向量归约使用BF16累加造成舍入偏差", "trigger": "连续输入，BF16长向量归约"},
    ]
    for index in range(6, 99):
        rows.append({"item_id": f"F-{index:03d}", "description": f"合成独立模式 diagnostic_{index:03d}",
                     "operator": f"synthetic_operator_{index:03d}",
                     "mechanism": f"diagnostic_{index:03d}专用状态寄存器位翻转，仅影响synthetic_operator_{index:03d}",
                     "trigger": f"仅在synthetic_mode_{index:03d}和diagnostic_{index:03d}故障注入同时开启时触发"})
    return rows


def evidence_packages() -> list[dict]:
    wiki_components = {"body": "COMPLETE", "sections": "COMPLETE", "comments": "NOT_APPLICABLE",
                       "attachment_index": "NOT_APPLICABLE", "subpages": "NOT_APPLICABLE"}
    common = {"status": "COMPLETE", "artifact_type": "WIKI", "components": wiki_components,
              "required_components": list(wiki_components), "is_synthetic": True,
              "retrieved_by": "synthetic-fixture-generator", "retrieved_at": "2026-10-30T00:00:00+00:00"}
    packages = [
        {**common, "url": URLS["allreduce"], "title": "[纯合成] SIM-AR-101 AllReduce舍入精度问题",
         "text": """纯合成验收资料，非真实客户或内网记录。
# 事件与环境
事件编号：SIM-AR-101。合成客户甲 / SYNTH-MODEL-A。
症状：PCIe链路、TP6场景下，all_reduce输出产生舍入精度偏差并导致文本乱码。
# 根因
PCIe分段归约使用低精度累加，引入舍入偏差。故障发生在all_reduce通信归约路径，不涉及量化算子输入对齐。
# 修复
将该分段归约路径的累加缓冲区改为FP32，并在归约结束后执行一次类型转换。
# 验证
在同一PCIe链路、TP6输入上重复20次，逐元素比较与FP32参考一致，乱码消失。
以上为本合成事件的验证记录；未验证其他客户、链路或算子。
"""},
        {**common, "url": URLS["quant"], "title": "[纯合成] SIM-Q-900量化输入对齐问题",
         "text": """纯合成验收资料，非真实客户或内网记录。
# 事件与环境
事件编号：SIM-Q-900。合成客户戊 / SYNTH-MODEL-Q，W8A8量化推理。
症状：输入最后一维长度为96时，dequant_swiglu_quant输出乱码。
# 根因
量化输入形状未对齐64，平铺逻辑在尾块读取了错误的scale缓冲区。
这是一条dequant_swiglu_quant量化路径故障，与PCIe all_reduce通信归约无关。
# 修复与验证
为尾块增加正确的scale索引和边界处理。长度96、160的合成输入测试通过。
该资料只记录SIM-Q-900，不提供AllReduce事件的根因支持。
"""},
        {**common, "url": URLS["shared_wiki"], "title": "[纯合成] Attention与RoPE两个独立问题复盘",
         "text": """纯合成验收资料，非真实客户或内网记录。
本页记录两个相互独立的问题；同页收录不表示同一事件或共同根因。
# 问题一：SIM-ATTN-202
事件编号：SIM-ATTN-202。合成客户乙 / SYNTH-MODEL-B。
症状：FP8 Attention静态量化时首Token乱码。
触发条件：FP8静态量化，V scale按head分组。
根因：V scale按错误head索引读取。
修复：按正确的head维度计算V scale索引，保持每个head的缩放值对应其V数据。
验证：同一输入连续运行20次，首Token与参考实现一致，未再出现乱码。
# 问题二：SIM-ROPE-303
事件编号：SIM-ROPE-303。合成客户乙 / SYNTH-MODEL-B。
症状：RoPE Norm入参H2D后，重复推理结果不确定。
触发条件：异步H2D，pin_memory缓冲区复用。
根因：异步H2D尚未完成，pin_memory缓冲区已复用。
修复：延长pin_memory缓冲区生命周期，在H2D完成事件确认后再复用缓冲区。
验证：相同输入重复20次结果逐位一致。
两个问题分别修复和验证，不能互相替代根因证据。
"""},
        {**common, "url": URLS["shared_dts"], "title": "[纯合成] SIM-ROPE-303 H2D确定性工单",
         "artifact_type": "DTS",
         "components": {"body": "COMPLETE", "history": "COMPLETE", "comments": "COMPLETE", "attachment_index": "NOT_APPLICABLE"},
         "required_components": ["body", "history", "comments", "attachment_index"],
         "text": """纯合成验收资料，非真实工单。
工单对应事件编号：SIM-ROPE-303。合成客户乙 / SYNTH-MODEL-B。
简要描述：RoPE Norm入参H2D后，重复推理结果不确定。
复现条件：异步H2D，pin_memory缓冲区复用。
定位结论：异步H2D尚未完成，pin_memory缓冲区已复用。
处理记录：延长pin_memory缓冲区生命周期，等待H2D完成事件后才允许复用。
验证记录：相同输入重复20次结果逐位一致，确定性问题关闭。
最后评论：本工单仅记录上述RoPE Norm与H2D问题；没有verl rollout的复现，
也没有sleep/wakeup、MLA或sin/cos cache的定位、修复和验证结论。
附件：无。
"""},
        {**common, "url": URLS["partial_pr"], "title": "[纯合成] SIM-NORM-606非连续输入索引修复说明",
         "status": "PARTIAL", "artifact_type": "PR",
         "components": {"body": "COMPLETE", "file_list": "NOT_FETCHED", "diff": "NOT_FETCHED", "comments": "NOT_FETCHED"},
         "required_components": ["body", "file_list", "diff", "comments"],
         "expected_file_count": 1, "captured_file_count": 0,
         "text": """纯合成验收资料，当前仅取得PR描述，未取得文件列表、Diff和评论。
PR关联事件编号：SIM-NORM-606。合成客户己 / SYNTH-MODEL-F。
PR描述的症状：rms_norm在FP32、非连续stride=8输入时读取错误行。
PR描述的触发条件：FP32输入，非连续stride=8；连续输入正常。
PR描述的根因：非连续输入的行地址索引未乘实际stride，导致读错地址。
PR描述的修改意图：根据实际stride计算行地址。
页面显示预期变更1个文件，但当前采集到0个文件，Diff尚未读取。
没有取得该补丁的实际实现、测试结果或合并状态，不确认修复生效。
"""},
    ]
    for package in packages:
        package.update(requested_url=package["url"], final_url=package["url"], case_ids=[])
    return packages


def acceptance_expectations() -> dict:
    positive = {"event_relation": "SAME_EVENT", "pattern_relation": "SAME_PATTERN",
                "case_attribution": "CONFIRMED", "support_level": "DIRECT", "root_cause_support": "SUPPORTED"}
    return {
        "fixture_kind": "SYNTHETIC_ONLY",
        "not_model_results": True,
        "model_input_policy": "Do not pass this expectations file to the executor. It is acceptance criteria only.",
        "cases": 5, "evidence_packages": 5, "associations": 7,
        "catalog_scope": "INFERENCE", "catalog_count": 98,
        "associations_expected": [
            {"external_id": "SIM-001", "url": URLS["allreduce"], **positive,
             "criterion": "AllReduce事件必须引用SIM-AR-101及其舍入、PCIe机理，不借用量化资料。"},
            {"external_id": "SIM-001", "url": URLS["quant"], "event_relation": "DIFFERENT_EVENT",
             "pattern_relation": "DIFFERENT_PATTERN", "case_attribution": "MISMATCH", "must_not_be_direct": True,
             "criterion": "相同乱码表象不能把SIM-Q-900量化对齐问题拼接到AllReduce根因。"},
            {"external_id": "SIM-002", "url": URLS["shared_wiki"], **positive,
             "required_issue_anchor": "SIM-ATTN-202", "criterion": "引用V scale子问题，不能引用H2D作为根因。"},
            {"external_id": "SIM-003", "url": URLS["shared_wiki"], **positive,
             "required_issue_anchor": "SIM-ROPE-303", "criterion": "引用pin_memory/H2D子问题，不能与ATTN自动合并。"},
            {"external_id": "SIM-003", "url": URLS["shared_dts"], **positive,
             "criterion": "DTS明确记录SIM-ROPE-303，保留其独立来源与对应故障关系。"},
            {"external_id": "SIM-004", "url": URLS["shared_dts"], "event_relation": "DIFFERENT_EVENT",
             "allowed_pattern_relations": ["DIFFERENT_PATTERN", "UNDETERMINED", "POSSIBLY_RELATED"],
             "must_not_be_direct": True, "must_not_confirm_root_cause": True,
             "criterion": "该DTS没有verl复现与cache定位，不支持SIM-VERL-404的根因或修复验证。"},
            {"external_id": "SIM-005", "url": URLS["partial_pr"], "event_relation": "DIFFERENT_EVENT",
             "pattern_relation": "DIFFERENT_PATTERN", "must_not_be_direct": True,
             "criterion": "同rms_norm算子但输入布局、数据类型与根因不同；PR缺Diff，不确认修复实现。"},
        ],
        "catalog_expected": {
            "SIM-001": {"must_cover": ["F-001"], "must_not_cover": ["F-002", "F-003", "F-004", "F-005"]},
            "SIM-002": {"must_cover": ["F-002"], "must_not_cover": ["F-001", "F-003", "F-004", "F-005"]},
            "SIM-003": {"must_cover": ["F-003"], "must_not_cover": ["F-001", "F-002", "F-004", "F-005"]},
            "SIM-004": {"all_items_must_be": "UNDETERMINED"},
            "SIM-005": {"all_items_must_be": "UNDETERMINED"},
        },
        "global_criteria": [
            "不得合并五条原始故障。",
            "每个模型引文须逐字存在于对应快照与segment。",
            "所有98条库模式必须各出现一次；F-006..098具有独立明确的机理和触发条件。",
            "共享资料的两条原始故障须分别保留判断。",
            "未取得的Diff须作为缺口保留，最终状态不得虚报业务核验完成。",
            "模型建议不得自动变成人工ACCEPT。",
            "本验收仅验证合成输入上的本次模型与工作流，不证明真实内网采集或真实98条库覆盖准确率。",
        ],
    }


def seed(destination: Path) -> dict:
    destination = destination.resolve()
    files = {
        destination / "inputs" / "cases.json": source_cases(),
        destination / "inputs" / "catalog.json": {"sheets": {"INFERENCE": catalog_rows()}},
        destination / "inputs" / "evidence.json": evidence_packages(),
        destination / "expectations.json": acceptance_expectations(),
    }
    # Preserve a previously modified fixture instead of silently replacing it.
    conflicts = [str(path) for path, value in files.items() if path.exists()
                 and path.read_text(encoding="utf-8") != json.dumps(value, ensure_ascii=False, indent=2) + "\n"]
    if conflicts:
        raise ValueError("Existing different fixture files; no changes made: " + ", ".join(conflicts))
    for path, value in files.items():
        write_json(path, value)
    return {"out": str(destination), "files": [str(path) for path in files], "cases": 5,
            "evidence_packages": 5, "associations": 7, "catalog_items": 98,
            "is_synthetic": True, "model_results_generated": False, "sqlite_created": False}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "work" / "codex_pilot")
    args = parser.parse_args()
    print(json.dumps(seed(args.out), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
