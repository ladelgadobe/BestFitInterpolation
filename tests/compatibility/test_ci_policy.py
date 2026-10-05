"""No-QGIS tests for discovery, version identity and truthful compatibility gates."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]


def load(name):
    spec=importlib.util.spec_from_file_location(name,str(ROOT/'ci'/(name+'.py')))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


class PolicyTests(unittest.TestCase):
    def test_missing_requested_image_is_not_substituted(self):
        resolver=load('resolve_images')
        tags=[dict(name='3.44.8-noble',digest='sha256:'+'a'*64,images=[dict(architecture='amd64',os='linux')])]
        self.assertIsNone(resolver.resolve(tags,'3.14'))
        self.assertIn('@sha256:',resolver.resolve(tags,'3.44')['image'])

    def test_future_and_nightly_names_are_not_stable(self):
        resolver=load('resolve_images')
        self.assertIsNone(resolver.version_from_tag('nightly'))
        self.assertIsNone(resolver.version_from_tag('latest'))
        self.assertEqual(resolver.version_from_tag('final-3_14_15'),(3,14,15))

    def test_report_never_marks_static_as_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            target=dict(requested='3.14',aliases=['3.14'],required=True,pdf=False,resolution=None)
            result=dict(requested='3.14',status='STATICALLY_CHECKED',tests={},actual=None)
            Path(folder,'3.14.json').write_text(json.dumps(result))
            rows,text=load('summarize').summarize({'targets':[target]},Path(folder))
            self.assertEqual(rows[0]['status'],'STATICALLY_CHECKED')
            self.assertIn('Not executed',text)
            self.assertNotIn(' PASS',text)

    def test_missing_artifact_is_unavailable(self):
        with tempfile.TemporaryDirectory() as folder:
            target=dict(requested='4.0',aliases=['4.0'],required=True,pdf=True,resolution=None)
            rows,_=load('summarize').summarize({'targets':[target]},Path(folder))
            self.assertEqual(rows[0]['status'],'UNAVAILABLE')

    def test_actual_failure_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            target=dict(requested='4.0',aliases=['4.0'],required=True,pdf=True,resolution=None)
            Path(folder,'4.0.json').write_text(json.dumps({'status':'FAILED','actual':'4.0.3','tests':{'plugin_import':{'result':'FAIL','category':'IMPORT'}},'errors':['ModuleNotFoundError']}))
            rows,text=load('summarize').summarize({'targets':[target]},Path(folder))
            self.assertEqual(rows[0]['status'],'FAILED')
            self.assertIn('IMPORT',text)


if __name__=='__main__': unittest.main()
