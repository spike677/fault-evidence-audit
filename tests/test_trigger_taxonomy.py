"""Synthetic taxonomy fixtures; no private user document is copied here."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from faultaudit.store import AuditError
from faultaudit.trigger_taxonomy import EXPECTED_IDS, FAMILY_COUNTS, builtin_user_branches, load_taxonomy


def taxonomy_text(*, escaped=True, preface=True):
    escape = "\\" if escaped else ""
    lines = (["PPT planning notes: 42 = 35 + 7; Branch 2/3 are outside the 42.",
              "`[ / ]` **1.1.1 Preface mention** — not a category definition.",
              "| **1.C.1** | Preface mention | No requirement | — |"] if preface else [])
    lines.extend(["Editorial sentence followed by the actual marker. # Trigger Library",
        f"{escape}## 0. Scope: Input Construction Only", "Only inputs.* call arguments are in scope.",
        f"{escape}## 0.1 Parameter applicability", "Use structure, role and constraints; unknown is not skip.",
        f"{escape}### Role matrix", "Synthetic role details retained.",
        f"{escape}## How to Use", "Coverage needs the complete predicate and preserved concrete arguments.",
        f"{escape}## Trigger Checklist"])
    for family, count in FAMILY_COUNTS.items():
        level = "##" if family == "1.C" else "###"
        lines.extend([f"{escape}{level} {family} Synthetic family {family}",
            "**Requires（hard condition）:**", "", f"{escape}- A synthetic role, or",
            f"{escape}- an explicitly exposed control.",
            "**Skip if:** the synthetic required role is positively absent.", ""])
        if family == "1.C":
            lines.extend(["| ID | Item | Requires | Combined |", "| --- | --- | --- | --- |"])
        for index in range(1, count + 1):
            item_id = f"{family}.{index}"
            if family == "1.C":
                lines.append(f"| **{item_id}** | Synthetic control {index} | `SEM-TEST-{index}` | 1.7 |")
            else:
                lines.extend([f"`[ / ]` **{item_id} Synthetic trigger {item_id}** — specific synthetic predicate {index}.",
                    f"Requires: explicit argument role {index}.",
                    "Skip if: no matching call argument.", "", f"{escape}---", ""])
    lines.extend([f"{escape}## Typical Combination Patterns", "A case may have several labels."])
    return "\n".join(lines) + "\n"


class TriggerTaxonomyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.path = self.directory / "synthetic_trigger_library.md"

    def tearDown(self):
        self.temp.cleanup()

    def source(self, text=None):
        self.path.write_bytes((taxonomy_text() if text is None else text).encode("utf-8"))
        return self.path

    def test_escaped_markdown_and_preface_produce_exactly_42_unique_items(self):
        result = load_taxonomy(self.source())
        self.assertEqual([item["id"] for item in result["items"]], list(EXPECTED_IDS))
        self.assertEqual(result["item_count"], 42)
        self.assertEqual({f["family_id"]: f["item_count"] for f in result["families"]}, FAMILY_COUNTS)
        self.assertNotIn("Preface mention", result["items"][0]["name"])
        self.assertEqual(result["items"][-1]["name"], "Synthetic control 7")
        self.assertEqual(result["items"][-1]["requires"], ["`SEM-TEST-7`"])

    def test_plain_markdown_without_preface_is_also_supported(self):
        result = load_taxonomy(self.source(taxonomy_text(escaped=False, preface=False)))
        self.assertEqual(result["item_count"], 42)
        self.assertEqual(result["items"][0]["requires"], ["explicit argument role 1."])
        self.assertEqual(result["items"][0]["skip_if"], ["no matching call argument."])

    def test_every_quote_matches_its_exact_source_range_and_source_is_unchanged(self):
        path = self.source(taxonomy_text().replace("\n", "\r\n"))
        original = path.read_bytes()
        result = load_taxonomy(path)
        lines = original.decode("utf-8").splitlines(keepends=True)
        for entry in [*result["items"], *result["families"], *result["context"].values()]:
            quote = "".join(lines[entry["line_start"] - 1:entry["line_end"]])
            self.assertEqual(entry["source_quote"], quote)
            self.assertEqual(entry["source_file"], str(path.resolve()))
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(result["source_sha256"], hashlib.sha256(original).hexdigest())

    def test_family_and_global_conditions_remain_source_backed(self):
        result = load_taxonomy(self.source())
        self.assertIn("A synthetic role, or", result["families"][0]["requires"][0])
        self.assertIn("an explicitly exposed control.", result["families"][0]["requires"][0])
        self.assertEqual(set(result["context"]), {"scope", "applicability", "coverage"})
        self.assertIn("Role matrix", result["context"]["applicability"]["source_quote"])
        self.assertIn("complete predicate", result["context"]["coverage"]["source_quote"])

    def test_missing_id_rejected(self):
        text = taxonomy_text().replace("`[ / ]` **1.2.8 Synthetic trigger 1.2.8**", "Omitted item")
        with self.assertRaisesRegex(AuditError, "42 unique.*missing: 1.2.8"):
            load_taxonomy(self.source(text))

    def test_duplicate_id_rejected(self):
        text = taxonomy_text().replace("`[ / ]` **1.2.8 Synthetic trigger 1.2.8**",
                                       "`[ / ]` **1.2.7 Duplicate synthetic item**")
        with self.assertRaisesRegex(AuditError, "Duplicate trigger"):
            load_taxonomy(self.source(text))

    def test_unknown_id_rejected_instead_of_silently_ignoring_it(self):
        text = taxonomy_text().replace("`[ / ]` **1.2.8 Synthetic trigger 1.2.8**",
                                       "`[ / ]` **1.2.9 Unknown synthetic item**")
        with self.assertRaisesRegex(AuditError, "Unknown trigger ID"):
            load_taxonomy(self.source(text))

    def test_missing_family_or_checklist_rejected(self):
        for old, new in (("\\### 1.2 Synthetic family 1.2", "Not a family"),
                         ("\\## Trigger Checklist", "Not a checklist")):
            with self.subTest(old=old), self.assertRaises(AuditError):
                load_taxonomy(self.source(taxonomy_text().replace(old, new)))

    def test_identity_is_content_derived_and_changes_when_source_changes(self):
        first = load_taxonomy(self.source())
        second = load_taxonomy(self.path)
        copy = self.directory / "copy.md"
        copy.write_bytes(self.path.read_bytes())
        self.assertEqual(first["taxonomy_hash"], second["taxonomy_hash"])
        self.assertEqual(first["taxonomy_id"], load_taxonomy(copy)["taxonomy_id"])
        self.source(taxonomy_text().replace("specific synthetic predicate 1.", "revised synthetic predicate 1."))
        self.assertNotEqual(first["taxonomy_hash"], load_taxonomy(self.path)["taxonomy_hash"])

    def test_absent_outside_definitions_are_undefined_and_not_counted_as_triggers(self):
        result = load_taxonomy(self.source())
        self.assertEqual([(b["branch_id"], b["status"]) for b in result["branches"]],
                         [("2", "UNDEFINED"), ("3", "UNDEFINED")])
        self.assertTrue(all(not b["included_in_42"] and not b["definition"] for b in result["branches"]))
        self.assertIsNone(result["branch_source"])

    def test_explicit_branch_json_is_separate_and_missing_branch_stays_unknown(self):
        source = self.directory / "synthetic_branches.json"
        entry = {"branch_id": "2", "name": "Synthetic outside branch",
                 "definition": "An explicitly supplied outside classification.",
                 "source_quote": "An explicitly supplied outside classification."}
        source.write_text(json.dumps({"branches": [entry]}, ensure_ascii=False), encoding="utf-8")
        result = load_taxonomy(self.source(), source)
        self.assertEqual(result["item_count"], 42)
        self.assertEqual(result["branches"][0]["status"], "DEFINED")
        self.assertEqual(result["branches"][0]["definition"], entry["definition"])
        self.assertEqual(result["branches"][1]["status"], "UNDEFINED")
        self.assertNotEqual(result["taxonomy_id"], load_taxonomy(self.path)["taxonomy_id"])

    def test_unstructured_branch_document_is_retained_without_inventing_leaves(self):
        source = self.directory / "synthetic_branches.md"
        text = "# Editorial outside-branch notes\nNo structured authoritative definitions yet.\n"
        source.write_bytes(text.encode("utf-8"))
        result = load_taxonomy(self.source(), source)
        self.assertEqual(result["branch_source"]["source_quote"], text)
        self.assertTrue(all(b["status"] == "UNDEFINED" for b in result["branches"]))
        self.assertEqual(result["branch_source"]["source_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())

    def test_duplicate_or_incomplete_declared_branch_rejected(self):
        source = self.directory / "synthetic_branches.json"
        entry = {"branch_id": "2", "name": "Synthetic", "definition": "Explicit.", "source_quote": "Explicit."}
        for branches in ([entry, entry], [{**entry, "definition": ""}], [{**entry, "branch_id": "4"}]):
            with self.subTest(branches=branches), self.assertRaises(AuditError):
                source.write_text(json.dumps({"branches": branches}), encoding="utf-8")
                load_taxonomy(self.source(), source)

    def test_opt_in_user_branch_categories_have_explicit_user_provenance(self):
        path = self.source()
        before = path.read_bytes()
        result = load_taxonomy(path, user_branch_definitions=builtin_user_branches())
        self.assertEqual(result["item_count"], 42)
        self.assertEqual([item["id"] for item in result["items"]], list(EXPECTED_IDS))
        self.assertEqual([category["id"] for branch in result["branches"] for category in branch["categories"]],
                         ["2.1", "2.2", "2.3", "3.1", "3.2", "3.3"])
        self.assertIn("固定单实例可为0", result["branches"][0]["definition"])
        self.assertIn("同实参、同二进制", result["branches"][1]["definition"])
        for branch in result["branches"]:
            self.assertEqual(branch["status"], "DEFINED")
            self.assertFalse(branch["included_in_42"])
            self.assertEqual(branch["provenance"], "user instruction 2026-11-06")
            self.assertEqual(branch["source_file"], "")
            for category in branch["categories"]:
                self.assertEqual(category["provenance"], branch["provenance"])
                self.assertEqual(category["source_file"], "")
                self.assertIn(category["source_quote"], branch["source_quote"])
        self.assertEqual(result["branch_source"]["format"], "USER_DEFINITIONS")
        self.assertEqual(path.read_bytes(), before)

    def test_user_branch_supplement_is_optional_and_returned_objects_are_independent(self):
        definitions = builtin_user_branches()
        definitions["branches"][0]["categories"][0]["name"] = "Mutated test value"
        self.assertEqual(builtin_user_branches()["branches"][0]["categories"][0]["name"], "平台/SoC")
        path = self.source()
        plain = load_taxonomy(path)
        supplied = load_taxonomy(path, user_branch_definitions=builtin_user_branches())
        self.assertTrue(all(branch["status"] == "UNDEFINED" for branch in plain["branches"]))
        self.assertNotEqual(plain["taxonomy_id"], supplied["taxonomy_id"])
        self.assertEqual(plain["source_sha256"], supplied["source_sha256"])
        definitions = builtin_user_branches()
        definitions["branches"][0]["categories"][0]["definition"] = "Explicit revised definition"
        revised = load_taxonomy(path, user_branch_definitions=definitions)
        self.assertNotEqual(supplied["taxonomy_id"], revised["taxonomy_id"])

    def test_structured_branch_source_preserves_category_ids_and_file_identity(self):
        source = self.directory / "synthetic_branch_categories.json"
        source.write_text(json.dumps({"branches": [{"branch_id": "2", "name": "Synthetic outside branch",
            "definition": "An explicit outside branch.", "source_quote": "An explicit outside branch with one category.",
            "categories": [{"id": "2.1", "name": "Synthetic category", "definition": "An explicit category.",
                            "source_quote": "An explicit category."}]}]}), encoding="utf-8")
        result = load_taxonomy(self.source(), source)
        category = result["branches"][0]["categories"][0]
        self.assertEqual(category["id"], "2.1")
        self.assertEqual(category["source_file"], str(source.resolve()))
        self.assertEqual(category["provenance"], "BRANCH_SOURCE_FILE")
        self.assertEqual(result["branches"][1]["categories"], [])

    def test_invalid_duplicate_or_unattributed_category_rejected(self):
        category = {"id": "2.1", "name": "Synthetic category", "definition": "Explicit.", "source_quote": "Explicit."}
        for categories in ([category, category], [{**category, "id": "3.1"}],
                           [{**category, "source_quote": ""}], [{**category, "id": "2"}]):
            with self.subTest(categories=categories), self.assertRaises(AuditError):
                load_taxonomy(self.source(), user_branch_definitions={"branches": [{
                    "branch_id": "2", "name": "Synthetic", "definition": "Explicit.",
                    "source_quote": "Explicit.", "categories": categories}]})

    def test_conflicting_branch_input_channels_are_rejected(self):
        source = self.directory / "synthetic_branches.json"
        source.write_text(json.dumps(builtin_user_branches()), encoding="utf-8")
        with self.assertRaisesRegex(AuditError, "not both"):
            load_taxonomy(self.source(), source, user_branch_definitions=builtin_user_branches())


if __name__ == "__main__":
    unittest.main()
