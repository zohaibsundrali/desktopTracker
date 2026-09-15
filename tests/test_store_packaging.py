import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET
from scripts.prepare_msix import manifest, package_version, stage, ROOT
from store_distribution import is_store_distribution
import desktop_updates

class StorePackagingTests(unittest.TestCase):
    def test_version_rejects_invalid_store_versions(self):
        for value in ('0.1.0','1.1.0.1','1.65536.0','1.0.beta','-1.0.0'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                package_version(value)
        self.assertEqual(package_version('1.1.0'),'1.1.0.0')

    def test_staging_preserves_nested_frozen_payload_and_exact_identity(self):
        identity=json.loads((ROOT/'packaging/store/identity.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'frozen'; source.mkdir()
            (source/'DeveloperTracker.exe').write_bytes(b'test-executable')
            (source/'_internal').mkdir()
            (source/'_internal'/'dependency.dll').write_bytes(b'test-library')
            destination=Path(directory)/'package'
            stage(source,destination,identity)
            self.assertEqual((destination/'_internal'/'dependency.dll').read_bytes(),b'test-library')
            ns={'p':'http://schemas.microsoft.com/appx/manifest/foundation/windows10'}
            doc=ET.parse(destination/'AppxManifest.xml')
            self.assertEqual(doc.find('p:Identity',ns).get('Publisher'),identity['publisher'])
            self.assertTrue((destination/'verisade-store-channel').exists())
            with self.assertRaises(ValueError):stage(source,destination,identity)

    def test_store_update_never_contacts_github_or_downloads_exe(self):
        with patch('store_distribution.is_store_distribution',return_value=True), patch.object(desktop_updates,'_read') as read:
            with self.assertRaisesRegex(desktop_updates.UpdateError,'Microsoft Store'):
                desktop_updates.check_for_update()
            with self.assertRaisesRegex(desktop_updates.UpdateError,'Microsoft Store'):
                desktop_updates.download_update(None,'unused',reader=read)
            read.assert_not_called()

    def test_channel_marker_only_affects_frozen_application(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/'verisade-store-channel').touch()
            with patch('sys.executable',str(Path(directory)/'DeveloperTracker.exe')),patch('sys.frozen',True,create=True):
                self.assertTrue(is_store_distribution())
            with patch('sys.executable',str(Path(directory)/'DeveloperTracker.exe')),patch('sys.frozen',False,create=True):
                self.assertFalse(is_store_distribution())
