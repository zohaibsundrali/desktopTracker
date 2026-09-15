import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import httpx
import desktop_updates as u


def release_data(version='1.2.0'):
    base=f'https://github.com/{u.REPOSITORY}/releases/'
    return {'draft':False,'prerelease':False,'tag_name':'v'+version,'html_url':base+'tag/v'+version,
            'assets':[{'name':name,'size':size,'browser_download_url':base+'download/v'+version+'/'+name}
                      for name,size in [('DeveloperTracker-Setup.exe',9),('SHA256SUMS.txt',100)]]}


class DesktopUpdateTests(unittest.TestCase):
    def test_only_newer_stable_complete_release_is_offered(self):
        self.assertEqual(u.parse_release(release_data()).version,'1.2.0')
        self.assertIsNone(u.parse_release(release_data('1.0.0')))
        for change in ({'prerelease':True},{'draft':True},{'tag_name':'v01.2.0'},
                       {'html_url':'https://evil.test'},{'assets':[]}):
            with self.subTest(change=change),self.assertRaises(u.UpdateError):
                u.parse_release({**release_data(),**change})

    def test_rejects_replaced_or_oversize_assets(self):
        for change in ({'browser_download_url':'https://evil.test/setup.exe'},{'size':True},{'size':u.MAX_INSTALLER+1}):
            value=release_data();value['assets'][0].update(change)
            with self.assertRaises(u.UpdateError):u.parse_release(value)

    def test_unknown_redirect_never_contacted_and_no_auth_header(self):
        visited=[]
        def response(request):
            visited.append(str(request.url));self.assertNotIn('authorization',request.headers)
            return httpx.Response(302,headers={'location':'https://evil.test/file'})
        client=httpx.Client(transport=httpx.MockTransport(response))
        with patch.object(u.httpx,'Client',return_value=client),self.assertRaises(u.UpdateError):
            u._read(u.API,100)
        self.assertEqual(visited,[u.API])

    def test_network_size_and_bad_json_fail_without_raw_errors(self):
        client=httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,content=b'x'*20)))
        with patch.object(u.httpx,'Client',return_value=client),self.assertRaises(u.UpdateError):u._read(u.API,10)
        with patch.object(u,'_read',return_value=b'not-json'),self.assertRaises(u.UpdateError):u.check_for_update()

    def test_signature_and_checksum_required_before_file_is_promoted(self):
        binary=b'installer';digest=hashlib.sha256(binary).hexdigest()
        def reader(url,limit,sink=None):
            if sink is None:return (digest+'  DeveloperTracker-Setup.exe\n').encode()
            sink.write(binary);return len(binary)
        with tempfile.TemporaryDirectory() as directory,patch.object(u,'TRUSTED_SIGNERS',('A'*40,)):
            seen=[]
            path=u.download_update(u.parse_release(release_data()),directory,reader,lambda p:seen.append(p.read_bytes()))
            self.assertEqual(path.read_bytes(),binary);self.assertEqual(seen,[binary])
            path.unlink()
            with self.assertRaises(u.UpdateError):
                u.download_update(u.parse_release(release_data()),directory,reader,
                                  lambda _:(_ for _ in ()).throw(u.UpdateError('untrusted')))
            self.assertEqual(list((Path(directory)/'updates').iterdir()),[])

    def test_unsigned_build_never_downloads_executable(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(u,'TRUSTED_SIGNERS',()),self.assertRaises(u.UpdateError):
            u.download_update(u.parse_release(release_data()),directory,
                              lambda *args:self.fail('must not contact network'))

    def test_checksum_rejects_wrong_and_duplicate_filename(self):
        for content in (b'x', ('a'*64+'  other.exe').encode(),(('a'*64+'  DeveloperTracker-Setup.exe\n')*2).encode()):
            with self.assertRaises(u.UpdateError):u.checksum_value(content)

    def test_mismatched_download_never_calls_signature_verifier(self):
        for content,count in [(b'wrongdata',9),(b'installer',8)]:
            with tempfile.TemporaryDirectory() as directory,patch.object(u,'TRUSTED_SIGNERS',('A'*40,)):
                def reader(url,limit,sink=None):
                    if sink is None:return (hashlib.sha256(b'installer').hexdigest()+'  DeveloperTracker-Setup.exe').encode()
                    sink.write(content);return count
                with self.assertRaises(u.UpdateError):
                    u.download_update(u.parse_release(release_data()),directory,reader,lambda _:self.fail('unverified bytes'))
                self.assertEqual(list((Path(directory)/'updates').iterdir()),[])

    def test_signature_requires_both_valid_chain_and_pinned_publisher(self):
        from types import SimpleNamespace
        for status,thumb,accepted in [('Valid','A'*40,True),('Valid','B'*40,False),('HashMismatch','A'*40,False)]:
            fake_os=SimpleNamespace(name='nt',environ={})
            response=SimpleNamespace(stdout=json.dumps({'status':status,'thumbprint':thumb}))
            with patch.object(u,'os',fake_os),patch.object(u.subprocess,'run',return_value=response) as run:
                if accepted:u.verify_signature('fixture.exe',('A'*40,))
                else:
                    with self.assertRaises(u.UpdateError):u.verify_signature('fixture.exe',('A'*40,))
                self.assertEqual(run.call_args.kwargs['timeout'],30)
                self.assertNotIn('fixture.exe',run.call_args.args[0][-1])
