import builtins
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from faultaudit import review_bundle as bundle

ROOT=Path(__file__).resolve().parents[1]/'reports/expansion-v1-20261110'


class PublicReviewBundleTests(unittest.TestCase):
    def test_public_bundle_passes_all_checks(self):
        result=bundle.validate(ROOT)
        self.assertEqual(result['status'],'PASS',[c for c in result['checks']if c['status']!='PASS'])

    def test_18_19_20_are_distinct_sets(self):
        s=bundle.recompute_api42(bundle.read_bundle(ROOT))
        self.assertEqual((s['original_L1'],s['baseline_plus_new_branch'],s['baseline_plus_context']),(18,19,20))
        self.assertEqual(s['new_branch_ids'],['1.C.3']);self.assertEqual(s['new_context_only_ids'],['1.C.1'])

    def test_modes_relations_and_conditions_have_different_units(self):
        s=bundle.recompute_api42(bundle.read_bundle(ROOT))
        self.assertEqual((s['related_original_modes'],s['original_relation_count'],s['original_L2']),(18,25,3))
        self.assertEqual((s['api42_relation_rows'],s['api42_technical_cases'],s['api42_unique_conditions']),(8,6,6))

    def test_12_unmapped_modes_have_explicit_non_global_reasons(self):
        ms=bundle.read_bundle(ROOT)['baseline']['modes'];missing=[m for m in ms if not m['original_api42_ids']]
        self.assertEqual(len(missing),12)
        self.assertTrue(all(m['reason']and not m['global_not_applicable']for m in missing))

    def test_no_original_mode_definition_or_init_body(self):
        data=bundle.read_bundle(ROOT)['baseline']
        self.assertFalse(data['semantic_source_available_in_public_package'])
        self.assertTrue(all('original_definition'not in m and'original_15_values'not in m for m in data['modes']))

    def test_gather_source_and_dequant_constants(self):
        gather=bundle.load(ROOT/'evidence/gather_1562_diff.json')
        self.assertIn('ge::GetSizeByDataType(index->GetDataType())',gather['old_exact_line'])
        c=bundle.load(ROOT/'evidence/dequant_constants.json')['constants']
        self.assertEqual((c['BLOCK_SIZE'],c['BLOCK_ELEM'],c['MASK_NUM_T32'],c['MASK_BLK_STRIDE']),(32,8,64,8))

    def test_functional_and_hang_not_precision_history(self):
        cs={c['technical_case_id']:c for c in bundle.read_bundle(ROOT)['cases']['cases']}
        self.assertEqual(cs['TC-MATMUL-DISPATCH-DTYPE']['mechanism_relation'],'FUNCTIONAL_OUT_OF_SCOPE')
        self.assertEqual(cs['TC-SFAG-EVENT-ID']['impact_status'],'HANG_REPORTED')
        self.assertTrue(all(not c['weekly_event_confirmed']and not c['hardware_validated']for c in cs.values()))

    def test_shared_dequant_patch_not_two_independent_incidents(self):
        rows=[r for r in bundle.read_bundle(ROOT)['relations']['relations']if r['technical_case_id'].startswith('TC-DEQUANT-')]
        self.assertEqual(len(rows),10)
        self.assertTrue(all(r['support_scope']=='COMBINED_FIX_PUBLISHED_TEST_CONTEXT_NOT_ISOLATED'and not r['independent_causal_validation']for r in rows))

    def test_42_templates_are_not_device_coverage(self):
        rows=bundle.read_bundle(ROOT)['tests']['conditions'];self.assertEqual(len(rows),42)
        self.assertTrue(all(not r['template_is_executable_coverage']and not r['hardware_execution_validated']for r in rows))

    def test_validator_does_not_import_device_libraries(self):
        original_import=builtins.__import__
        def guarded(name,*args,**kwargs):
            if name.startswith(('torch','torch_npu')):raise AssertionError('Device import attempted')
            return original_import(name,*args,**kwargs)
        with patch('builtins.__import__',guarded):self.assertEqual(bundle.validate(ROOT)['status'],'PASS')

    def test_publication_patterns_detect_private_paths_and_hosts(self):
        for sample in ['Z:'+chr(92)+'private'+chr(92)+'state','https://wiki.'+'huawei.com/page','https://dts.example/DTSPortal/ticket/1']:
            self.assertIsNotNone(bundle.FORBIDDEN.search(sample))
        self.assertIsNone(bundle.FORBIDDEN.search('https://github.com/vllm-project/vllm-ascend/pull/12123'))

    def test_validation_leaves_bundle_content_unchanged(self):
        names=list(bundle.DATA_FILES.values())+['manifest.json','README.md','CANN_EXPANSION_CANDIDATE_CATALOG.html']
        before={name:bundle.sha(ROOT/name)for name in names};bundle.validate(ROOT)
        self.assertEqual({name:bundle.sha(ROOT/name)for name in names},before)

    def test_payload_is_lf_canonical_for_git_hashes(self):
        for name in bundle.load(ROOT/'manifest.json')['payload_sha256']:
            self.assertNotIn(b'\r\n',(ROOT/name).read_bytes(),name)

    def test_report_rebuild_needs_only_published_data(self):
        temp_parent=ROOT.parents[1]/'.scratch'
        self.assertTrue(temp_parent.resolve().is_relative_to(ROOT.parents[1].resolve()))
        temp_parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='audit-publication-',dir=temp_parent)as directory:
            target=Path(directory).resolve()
            self.assertEqual(target.parent,temp_parent.resolve())
            for name in bundle.DATA_FILES.values():
                p=target/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/name).read_bytes())
            bundle.render(target)
            for name in ['README.md','CANN_EXPANSION_FULL_RESULTS.html','CANN_EXPANSION_CANDIDATE_CATALOG.html','evidence/STRONGEST_EVIDENCE.md']:
                self.assertEqual((target/name).read_bytes(),(ROOT/name).read_bytes())

    def test_every_case_has_primary_evidence_without_event_upgrade(self):
        data=bundle.read_bundle(ROOT);rows=data['strongest']['entries']
        self.assertEqual({r['technical_case_id']for r in rows},{c['technical_case_id']for c in data['cases']['cases']})
        self.assertEqual(len(rows),19)
        self.assertTrue(all(r['does_not_prove']and not r['formal_mode_adoption']and not r['weekly_event_confirmed']for r in rows))

    def test_gather_primary_uses_rechecked_diff_and_fixed_file(self):
        e=next(e for e in bundle.read_bundle(ROOT)['strongest']['entries']if e['technical_case_id']=='TC-GATHER-SCALAR-COUNT')
        self.assertEqual(e['primary_observation_id'],'OBS:TC-GATHER-SCALAR-COUNT:2')
        self.assertEqual(e['representation'],'EXACT_OBSERVED_DIFF_LINES')
        self.assertIn('/blob/f1359e5fbab5971b2aeeda58e2fdc5ec8e92fab0/',e['pinned_source_url'])

    def test_four_support_contexts_keep_prior_capture_scope(self):
        rows=bundle.read_bundle(ROOT)['contexts']['contexts']
        self.assertEqual({r['source_id']for r in rows},{'CAT-API-BOOL','CAT-TEST-GRAD-DEVICE','CAT-TEST-GRAD-META','CAT-API-GATHER'})
        self.assertTrue(all(r['capture_origin']=='PRIOR_TARGETED_OBSERVATION'and not r['hardware_executed']for r in rows))

    def test_full_html_alias_and_all_public_sections_are_embedded(self):
        import re
        raw=(ROOT/'CANN_EXPANSION_FULL_RESULTS.html').read_bytes()
        self.assertEqual(raw,(ROOT/'CANN_EXPANSION_CANDIDATE_CATALOG.html').read_bytes())
        payload=json.loads(re.search(r'<script type="application/json" id="payload">([\s\S]*?)</script>',raw.decode()).group(1))
        self.assertEqual(payload,bundle.read_bundle(ROOT))
        self.assertTrue({'increments','candidates','gaps','strongest','contexts'}<=set(payload))


if __name__=='__main__':unittest.main(verbosity=2)
