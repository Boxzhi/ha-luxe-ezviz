"""Offline source-package checks; does not need Home Assistant or third-party SDK."""
from pathlib import Path
import json
import struct
import unittest

ROOT=Path(__file__).resolve().parents[1]
COMP=ROOT/'custom_components'/'luxe_ezviz'

class PackageChecks(unittest.TestCase):
 def test_manifest_and_hacs_metadata(self):
  m=json.loads((COMP/'manifest.json').read_text())
  h=json.loads((ROOT/'hacs.json').read_text())
  self.assertEqual(m['domain'],'luxe_ezviz')
  self.assertEqual(m['name'],h['name'])
  self.assertEqual(m['version'],'1.1.0')
  self.assertIn('issue_tracker',m)
  keys=list(m)
  self.assertEqual(keys[:2],['domain','name'])
  self.assertEqual(keys[2:],sorted(keys[2:]),'Hassfest requires alphabetically sorted manifest keys')
 def test_frontend_paths(self):
  card=(COMP/'frontend/luxe-ezviz-card.js').read_text()
  player=(COMP/'frontend/player.html').read_text()
  self.assertIn('/luxe_ezviz/static/player.html?v=1.1.0-audio-exclusive',card)
  setup=(COMP/'frontend_setup.py').read_text()
  self.assertIn("VERSION='1.1.0'",setup)
  self.assertIn("ASSET_VERSION='1.1.0-audio-exclusive'",setup)
  self.assertIn('/luxe_ezviz/sdk/ezuikit.js',player)
  self.assertIn("staticPath:'/luxe_ezviz/sdk/ezuikit_static'",player)
  self.assertNotIn('/local/luxe-ezviz/player.html',card)
 def test_vendor_is_not_distributed(self):
  self.assertFalse((COMP/'frontend/vendor').exists())
  self.assertFalse(any(COMP.rglob('*.wasm')))
  hashes=json.loads((COMP/'sdk_hashes.json').read_text())
  self.assertEqual(hashes['version'],'9.0.5')
  self.assertEqual(len(hashes['files']),14)
 def test_brand_images(self):
  b=COMP/'brand'
  for stem in ['icon','dark_icon','logo','dark_logo']:
   for suf in ['', '@2x']:
    p=b/(stem+suf+'.png')
    raw=p.read_bytes()
    self.assertEqual(raw[:8],b'\x89PNG\r\n\x1a\n')
    width,height=struct.unpack('>II',raw[16:24])
    if 'icon' in stem:self.assertEqual((width,height),(512,512) if suf else (256,256))
    else:self.assertEqual((width,height),(1024,256) if suf else (512,128))

if __name__=='__main__':unittest.main()
