"""Follow-up plan N2 (Sol round 10, medium): each static field carries its kind in the object's
encrypted payload, every writer and every partial update writes or keeps it, and at rollback that
kind is the only authority. A field with no recorded kind (an object written before N2) reads as
before and fails closed at rollback, naming the fix; malformed or unknown kind data is refused
before use. Temporary folders, an in-process agent and fictional values only."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from secret_store import oauth_ops, static_fields  # noqa: E402
from secret_store.store_ops import build_put  # noqa: E402
from test_secret_store_broker import FIELD, PASS, SECRET, StoreFixture, setUpModule, tearDownModule  # noqa: E402,F401
from test_secret_store_rollback_static import MigratedStore  # noqa: E402


def raw_static(store, entry, payload):
    """A static object with exactly this payload, as a store made before N2 (or a hostile writer) has it."""
    store._write(lambda: build_put(store.policy, store.checkpoint.objects, store._index(None), entry, payload,
                                   "static", store._identity().ed25519, store._group(None)))


class RollbackUsesTheRecordedKind(MigratedStore):
    def test_the_migration_records_the_old_vaults_kinds(self):
        self.assertEqual(self.a.get_typed("plain")[1], {"api_key": "text", "shaped": "text", "options": "json",
                                                        "extra": "text", "config": "json"})

    def test_a_migrated_json_field_replaced_by_text_that_is_valid_json_comes_back_as_text(self):
        canonical = json.dumps({"mode": "typed"}, sort_keys=True)
        self.ba.set_text("plain", "options", canonical)
        code, text = self.run_it()
        self.assertEqual(code, 0, text)
        self.assertEqual(self.vault.get("plain", "options", PASS), canonical)
        self.assertEqual(self.vault.load(PASS)["entries"]["plain"]["fields"]["options"]["kind"], "text")

    def test_a_migrated_text_field_replaced_by_json_comes_back_as_json(self):
        self.ba.set_json("plain", "api_key", {"rotated": "fictional"})
        code, text = self.run_it()
        self.assertEqual(code, 0, text)
        self.assertEqual(self.vault.get("plain", "api_key", PASS), {"rotated": "fictional"})

    def test_a_field_with_no_recorded_kind_fails_closed_and_names_the_fix(self):
        raw_static(self.a, "legacy", {"api_key": "fictional-legacy", "blob": '{"a": 1}'})  # written before N2
        self.assertEqual(self.ba.get_fields("legacy", ["api_key"]), {"api_key": "fictional-legacy"})  # as today
        self.ba.set_text("legacy", "extra", "fictional-later")  # a later write records only its own kind
        self.assertEqual(self.a.get_typed("legacy")[1], {"extra": "text"})
        code, text = self.run_it()
        self.assertEqual(code, 5, text)
        named = text.split("could not be restored", 1)[1]
        self.assertIn("legacy (api_key, blob)", named)
        self.assertIn("store the entry again", named)
        self.assertNotIn("legacy", self.vault.load(PASS)["entries"])
        self.assertTrue(self.marker.exists())

    def test_malformed_or_unknown_kind_data_is_refused_before_use(self):
        raw_static(self.a, "bad-kind", {"schema": 2, "values": {"k": "v"}, "kinds": {"k": "yaml"}})
        raw_static(self.a, "bad-form", {"schema": 2, "values": {"k": "not json"}, "kinds": {"k": "json"}})
        for entry in ("bad-kind", "bad-form"):
            with self.assertRaisesRegex(Exception, "kinds are malformed"):
                self.a.get_record(entry)
        code, text = self.run_it()
        self.assertEqual(code, 5, text)
        named = text.split("could not be restored", 1)[1]
        self.assertIn("bad-kind", named)
        self.assertIn("bad-form", named)
        self.assertTrue(self.marker.exists())


class SchemaIsTheWrapperOnlyWhenAnInteger(MigratedStore):
    """Plan R11, rule 4 (Sol round 11, medium): only an integer, non-boolean schema marks the wrapper;
    a text field named schema in an object written before N2 is an ordinary legacy field."""

    def test_a_legacy_text_field_named_schema_is_read_written_and_named_like_any_legacy_field(self):
        raw_static(self.a, "legacy-schema", {"schema": "v1", "api_key": "fictional-legacy"})
        self.assertEqual(self.ba.get_fields("legacy-schema", ["schema", "api_key"]),
                         {"schema": "v1", "api_key": "fictional-legacy"})
        self.ba.set_text("legacy-schema", "extra", "fictional-later")
        values = {"schema": "v1", "api_key": "fictional-legacy", "extra": "fictional-later"}
        self.assertEqual(self.a.get_typed("legacy-schema"), (values, {"extra": "text"}))
        self.assertEqual(self.a.static_payload("legacy-schema"),
                         {"schema": static_fields.SCHEMA, "values": values, "kinds": {"extra": "text"}})
        code, text = self.run_it()
        self.assertEqual(code, 5, text)
        named = text.split("could not be restored", 1)[1]
        self.assertIn("legacy-schema (api_key, schema)", named)
        self.assertNotIn("legacy-schema", self.vault.load(PASS)["entries"])

    def test_an_integer_or_boolean_schema_that_is_not_the_wrapper_is_refused(self):
        values = {"k": "fictional"}
        refused = {"int-3": {"schema": 3, "values": values, "kinds": {}},
                   "bool-wrapper": {"schema": True, "values": values, "kinds": {}},
                   "bool-legacy": {"schema": True, "k": "fictional"},
                   "too-many": {"schema": 2, "values": values, "kinds": {}, "extra": "fictional"},
                   "too-few": {"schema": 2, "values": values}}
        for entry, payload in refused.items():
            with self.assertRaisesRegex(Exception, "kinds are malformed", msg=entry):
                static_fields.split(payload)
            raw_static(self.a, entry, payload)
            with self.assertRaisesRegex(Exception, "kinds are malformed", msg=entry):
                self.a.get_record(entry)
        self.assertEqual(static_fields.split({"schema": 2, "values": values, "kinds": {"k": "text"}}),
                         (values, {"k": "text"}))


class EveryWriterKeepsTheKind(StoreFixture):
    def test_a_partial_update_keeps_the_kinds_of_the_other_fields(self):
        self.ba.set_json("keep", "settings", {"a": 1})
        self.ba.set_text("keep", "note", "fictional-note")
        self.ba.set_json("keep", FIELD, {})  # a placeholder that the sign-in below takes over
        oauth_ops.put_signin(self.a, "keep", FIELD, self.token())
        self.assertEqual(self.a.get_typed("keep"), ({"settings": '{"a": 1}', "note": "fictional-note"},
                                                    {"settings": "json", "note": "text"}))

    def test_put_fields_records_the_kinds_it_is_given(self):
        oauth_ops.put_fields(self.a, "pf", {"note": "fictional", "cfg": "{}"}, {"client_secret": SECRET},
                             plain_kinds={"note": "text", "cfg": "json"})
        self.assertEqual(self.a.get_typed("pf")[1], {"note": "text", "cfg": "json"})
        oauth_ops.put_fields(self.a, "pf", {"more": "fictional"}, {"client_secret": SECRET})
        self.assertEqual(self.a.get_typed("pf")[1], {"note": "text", "cfg": "json", "more": "text"})

    def test_a_kind_that_disagrees_with_its_value_is_refused_at_write(self):
        with self.assertRaisesRegex(Exception, "kinds are malformed"):
            self.a.put_entry("w", {"k": "not json"}, field_kinds={"k": "json"})
        with self.assertRaisesRegex(Exception, "needs its kind"):
            self.a.put_entry("w", {"k": "v", "j": "w"}, field_kinds={"k": "text"})
        self.assertNotIn("w", self.a.list_entries())


if __name__ == "__main__":
    unittest.main()
