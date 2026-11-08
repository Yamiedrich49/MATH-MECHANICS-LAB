import importlib.util
from pathlib import Path
import unittest

P=Path(__file__).resolve().parents[1]/"run.py"
spec=importlib.util.spec_from_file_location("autolab_run",P)
lab=importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)

class LabTests(unittest.TestCase):
    def test_demo_html(self):
        source=lab.demo_game()
        self.assertEqual(lab.validate_html(source),[])
        self.assertIn("Content-Security-Policy",lab.harden(source))
    def test_no_remote_code(self):
        source=lab.demo_game().replace("<script>","<script src='https://bad.example/x.js'>")
        self.assertTrue(lab.validate_html(source))
    def test_bad_js(self):
        source=lab.demo_game().replace("const g=","const =")
        self.assertTrue(any("JavaScript parse" in x for x in lab.validate_html(source)))
    def test_budget_gate_no_key(self):
        c=lab.LabClient("",lab.CONFIG)
        with self.assertRaises(RuntimeError):
            c.ask("inventor","gpt-6-luna",lab.IDEAS,"give ideas")
    def test_reject_missing_viewport(self):
        self.assertTrue(lab.validate_html(lab.demo_game().replace('name="viewport"','name="none"')))

if __name__=="__main__":
    unittest.main()
