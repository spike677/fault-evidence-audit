"""The second round uses discriminating functions/conditions, not extra evidence types."""
import json
import re
from pathlib import Path
from urllib.parse import quote

P = Path(__file__).resolve().parents[1] / 'reports/rc128-actual-rework-20261113'
TERMS = '''001|cann/ascend-transformer-boost|rms_norm
004|Ascend/MindIE-LLM|ring
005|Ascend/MindIE-LLM|长稳
006|Ascend/pytorch|npu_rms_norm
007|Ascend/MindSpeed|低精
011|cann/ops-nn|conv 精度
012|cann/ops-transformer|负载均衡
013|Ascend/MindIE-LLM|GLM-4-32B
014|cann/ops-transformer|310B
015|Ascend/MindIE-LLM|B050
016|cann/ops-nn|B080
019|cann/hccl|BIOS
020|Ascend/MindIE-SD|bf16
028|cann/hccl|9.1.0
033|Ascend/pytorch|310P setitem
035|Ascend/MindSpeed|Ling
037|Ascend/MindIE-SD|qwen-image-edit
038|Ascend/pytorch|backward nan
039|Ascend/pytorch|cat
040|Ascend/MindSpeed|spike
041|Ascend/MindSpeed|M12
042|Ascend/op-plugin|segment_reduce
043|cann/hccl|deterministic
044|Ascend/MindSpeed-LLM|grpo
046|Ascend/pytorch|setitem
047|cann/ops-math|ReduceSum
048|cann/ops-nn|scatter
050|Ascend/pytorch|1230
052|Ascend/MindSpeed|step7
054|vllm-project/vllm-ascend|log_prob
055|Ascend/MindIE-LLM|HY
056|Ascend/MindIE-LLM|GLM
057|cann/hccl|HY
059|Ascend/MindSpeed|gnorm
061|cann/ops-transformer|FIA 同步
068|Ascend/MindSpeed-LLM|Qwen3.5
070|Ascend/MindSpeed|mul dtype
072|Ascend/MindSpeed-LLM|attention_head
073|Ascend/MindSpeed|TELayerNormColumnParallelLinear
076|vllm-project/vllm-ascend|hc_pre
078|Ascend/MindSpeed-MM|Qwen3
080|Ascend/MindSpeed-MM|step_embedder
081|vllm-project/vllm-ascend|Telechat
084|cann/ops-math|TopKV2
085|Ascend/MindIE-LLM|Codellama
087|Ascend/MindIE-LLM|attention_mask
088|Ascend/MindIE-LLM|llama70B
089|Ascend/MindIE-LLM|MedBench
090|cann/ops-math|transdata 精度
091|mindspore/mindspore|AIR
092|cann/ops-math|310P
093|Ascend/MindIE-LLM|rope_scaling
095|Ascend/MindIE-LLM|distill
096|vllm-project/vllm-ascend|DSR1
097|Ascend/msit|onnx
098|vllm-project/vllm-ascend|LiveCodeBench
101|cann/hccl|训练
103|cann/ops-math|ReduceSum 精度
104|Ascend/MindSpeed-LLM|pack
106|Ascend/MindSpeed-MM|matmul
107|Ascend/MindSpeed|确定性
109|Ascend/MindSpeed|fa 反向
112|cann/ops-nn|matmul tiling
113|Ascend/MindSpeed|dataloader
114|cann/ops-nn|mm349
116|Ascend/MindSpeed|FlashAttention backward
118|Ascend/MindSpeed-LLM|epoch
119|cann/hccl|FastGatherSyncBatchNorm
120|Ascend/MindSpeed|optimizer
121|cann/ops-transformer|useBufferType
124|Ascend/MindSpeed-MM|tp
125|cann/ops-nn|blockdim'''


def main():
    jobs=[]
    for line in TERMS.splitlines():
        number,repo,term=line.split('|')
        for endpoint in ['issues','pulls']:
            jobs.append({'job_id':f'P1R2-{number}-{endpoint}','task_ids':[f'RC-{number}'],
                         'round':2,'kind':'SEARCH','repository':repo,'query':term,
                         'url':f'https://gitcode.com/{repo}/{endpoint}?state=all&search={quote(term)}'})
    (P/'plans/phase1_round2.json').write_text(json.dumps(jobs,ensure_ascii=False,indent=2),encoding='utf-8')
    jobs=[]
    data=json.loads((P/'collection/phase1_bodies.json').read_bytes())
    for x in data:
        if x['kind']!='PATCH': continue
        text=(P/x['text_file']).read_text(encoding='utf-8')
        commit=re.search(r'^From ([0-9a-f]{40}) ',text,re.M)
        if not commit: continue
        diff=next(d for d in data if d['url']==x['url'].removesuffix('.patch')+'.diff')
        content=(P/diff['text_file']).read_text(encoding='utf-8')
        paths=re.findall(r'^diff --git a/(.*?) b/',content,re.M)
        production=[p for p in paths if not any(v in p.lower() for v in ['tests/','test/','readme','docs/','.md','.csv','build.sh'])]
        repo='/'.join(x['url'].split('/')[3:5])
        for path in production[:2]:
            jobs.append({'job_id':f'SRC-{len(jobs):03d}','task_ids':x['task_ids'],'round':1,'kind':'SOURCE',
                         'parent_url':x['url'].removesuffix('.patch'),'commit':commit.group(1),'path':path,
                         'url':f'https://raw.gitcode.com/{repo}/raw/{commit.group(1)}/{path}'})
    # Explicit Issue references have an immutable source anchor; not a claim about the private event.
    for ids,repo,commit,path in [
        (['RC-048'],'cann/ops-nn','d1efef7c30ca124dc30787a7db3c4479c8ffcc05','index/embedding_bag/op_api/aclnn_embedding_bag.cpp'),
        (['RC-039'],'cann/ops-math','454733904ae6a350a64deb33df720eebcc52da99','conversion/concat_v2/op_host/concat_v2_infershape.cpp'),
        (['RC-098'],'cann/ops-transformer','8011a1cd18390e9bad9567cdb6f51d1c38f40b0a','posembedding/kv_rms_norm_rope_cache/op_host/kv_rms_norm_rope_cache_infershape.cpp')]:
        jobs.append({'job_id':f'SRC-{len(jobs):03d}','task_ids':ids,'round':1,'kind':'SOURCE','commit':commit,'path':path,
                     'url':f'https://raw.gitcode.com/{repo}/raw/{commit}/{path}'})
    (P/'plans/phase1_sources.json').write_text(json.dumps(jobs,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__': main()
