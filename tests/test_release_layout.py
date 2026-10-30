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
  self.assertEqual(m['version'],'1.2.0')
  self.assertIn('issue_tracker',m)
  keys=list(m)
  self.assertEqual(keys[:2],['domain','name'])
  self.assertEqual(keys[2:],sorted(keys[2:]),'Hassfest requires alphabetically sorted manifest keys')
 def test_frontend_paths(self):
  m=json.loads((COMP/'manifest.json').read_text())
  card=(COMP/'frontend/luxe-ezviz-card.js').read_text()
  player=(COMP/'frontend/player.html').read_text()
  asset_version=m['version']+'-ezuikit-9.0.24-record-icon-width'
  self.assertIn('/luxe_ezviz/static/player.html?v='+asset_version,card)
  setup=(COMP/'frontend_setup.py').read_text()
  self.assertIn("VERSION='"+m['version']+"'",setup)
  self.assertIn("ASSET_VERSION='"+asset_version+"'",setup)
  self.assertIn('/luxe_ezviz/sdk/ezuikit.js',player)
  self.assertIn("staticPath:'/luxe_ezviz/sdk/ezuikit_static'",player)
  self.assertNotIn('/local/luxe-ezviz/player.html',card)
 def test_v120_recording_and_control_layout(self):
  card=(COMP/'frontend/luxe-ezviz-card.js').read_text()
  player=(COMP/'frontend/player.html').read_text()
  self.assertIn('RECORD_DOWNLOAD_COORDINATOR',card)
  self.assertIn("state==='RECORD_FILE'",card)
  self.assertIn("RECORD_FILE_ACCEPTED",card)
  self.assertIn("waitForRecordFileAccepted",player)
  self.assertIn("recordName:this._config",card)
  self.assertIn("await repairMp4Metadata(blob)",card)
  self.assertIn("luxe-mp4-metadata-repair.js?v=1.2.0",card)
  repair=(COMP/'frontend/luxe-mp4-metadata-repair.js').read_text()
  self.assertIn("export async function repairMp4Metadata",repair)
  self.assertIn("MAX_MOOV_BYTES",repair)
  self.assertIn("'clap'",repair)
  self.assertIn("'pasp'",repair)
  self.assertIn('id="record"',player)
  self.assertIn('id="record-status"',player)
  self.assertIn('M7 9 3 6.8v10.4L7 15',player)
  self.assertEqual(player.count('<rect x="7" y="5" width="14" height="14" rx="2.5"/>'),2)
  self.assertEqual(player.count('cx="14" cy="12" r="2.5"'),4)
  self.assertIn('transform-origin:14px 12px',player)
  self.assertIn('#record svg{width:23px;height:23px;stroke-width:1.98}',player)
  self.assertIn('#screenshot svg{width:23px;height:23px;stroke-width:1.98}',player)
  self.assertIn("recordStatusDot.hidden=state!=='recording'",player)
  self.assertIn('recordStatusSpinner.hidden=!processing',player)
  self.assertIn("recordStatusLabel.hidden=state==='recording'",player)
  self.assertIn("recordTimerLabel.hidden=state!=='recording'",player)
  self.assertIn('fill="#ff515b"',player)
  self.assertIn('#record-status.warning{color:#ffd08a;background:rgba(32,24,12,.56)}',player)
  self.assertIn('#record-status.error{color:#ff858b;background:rgba(34,13,17,.58)}',player)
  self.assertNotIn("state==='recording'?'REC':",player)
  self.assertIn('downloadRecord:false',player)
  self.assertIn('recordOptions:{enabledWatermarkRecord:false}',player)
  self.assertIn('RECORD_MAX_MS = 30 * 60 * 1000',player)
  self.assertIn('RECORD_WARNING_MS = 25 * 60 * 1000',player)
  self.assertIn("signal('RECORD_FILE'",player)
  self.assertIn('#ptz-trigger{position:absolute;left:8px',player)
  self.assertIn('#ptz-panel{position:absolute;top:50%;left:8px',player)
  self.assertIn('#quality-menu{position:fixed;left:8px',player)

 def test_vendor_is_not_distributed(self):
  self.assertFalse((COMP/'frontend/vendor').exists())
  self.assertFalse(any(COMP.rglob('*.wasm')))
  hashes=json.loads((COMP/'sdk_hashes.json').read_text())
  self.assertEqual(hashes['version'],'9.0.24')
  self.assertEqual(len(hashes['files']),12)
  self.assertIn('ezuikit_static/libSystemTransformWASM.js',hashes['files'])
  self.assertFalse(any(name.startswith('ezuikit_static/talk/') for name in hashes['files']))
  self.assertTrue(all(isinstance(pin,dict) and isinstance(pin.get('git_blob_sha'),str) and isinstance(pin.get('size'),int) for pin in hashes['files'].values()))
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
