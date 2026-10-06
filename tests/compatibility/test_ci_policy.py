"""No-QGIS tests for discovery, version identity and truthful compatibility gates."""
import importlib.util
import json
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]


def load(name):
    spec=importlib.util.spec_from_file_location(name,str(ROOT/'ci'/(name+'.py')))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


class PolicyTests(unittest.TestCase):
    def test_discovery_authentication_is_limited_to_github_https_api(self):
        resolver=load('resolve_images')
        response=MagicMock()
        response.__enter__.return_value.read.return_value=b'{}'
        urls=(
            'https://api.github.com/repos/qgis/QGIS/tags',
            'https://hub.docker.com/v2/repositories/qgis/qgis/tags',
            'https://api.github.com.example.org/tags',
            'http://api.github.com/repos/qgis/QGIS/tags',
        )
        with patch.dict(resolver.os.environ,{'GH_TOKEN':'test-only-token'},clear=True):
            for url in urls:
                with self.subTest(url=url), patch.object(resolver,'urlopen',return_value=response) as opened:
                    resolver.get_json(url)
                    auth=opened.call_args[0][0].get_header('Authorization')
                    self.assertEqual(auth, 'Bearer test-only-token' if url==urls[0] else None)

    def test_discovery_without_token_remains_usable_locally(self):
        resolver=load('resolve_images')
        response=MagicMock()
        response.__enter__.return_value.read.return_value=b'{"results":[]}'
        with patch.dict(resolver.os.environ,{},clear=True), patch.object(resolver,'urlopen',return_value=response) as opened:
            self.assertEqual(resolver.get_json('https://api.github.com/repos/qgis/QGIS/tags'),{'results':[]})
            self.assertIsNone(opened.call_args[0][0].get_header('Authorization'))

    def test_full_matrix_includes_every_stable_intermediate_qgis3(self):
        config=json.loads((ROOT/'ci/qgis_targets.json').read_text())
        labels=load('resolve_images').target_labels(config,'full','4.2')
        self.assertTrue(set('3.{}'.format(v) for v in range(14,45,2)).issubset(labels))

    def test_future_stable_qgis4_adds_intermediate_versions_automatically(self):
        config=json.loads((ROOT/'ci/qgis_targets.json').read_text())
        labels=load('resolve_images').target_labels(config,'full','4.8')
        self.assertTrue(set(('4.0','4.2','4.4','4.6','4.8','latest4')).issubset(labels))
        self.assertNotIn('4.10',labels)
        self.assertNotIn('4.4',load('resolve_images').target_labels(config,'fast','4.8'))

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

    def test_archived_distribution_suffix_is_resolved(self):
        resolver=load('resolve_images')
        self.assertEqual(resolver.version_from_tag('final-3_14_15_focal'),(3,14,15))
        tags=[dict(name='final-3_14_15',digest='sha256:'+'a'*64,images=[dict(architecture='amd64',os='linux')]),
              dict(name='final-3_14_15_focal',digest='sha256:'+'b'*64,images=[dict(architecture='amd64',os='linux')])]
        self.assertEqual(resolver.resolve(tags,'3.14')['tag'],'qgis/qgis:final-3_14_15_focal')

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
