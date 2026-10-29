"""Source-level regression checks for multi-camera audio exclusivity."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "luxe_ezviz"


class AudioExclusivityChecks(unittest.TestCase):
    def test_shared_coordinator_and_same_origin_mute_control(self):
        card = (COMP / "frontend/luxe-ezviz-card.js").read_text()
        player = (COMP / "frontend/player.html").read_text()
        self.assertIn("__luxeEzvizAudioCoordinator", card)
        self.assertIn("claimFrame(frame,mode='sound')", card)
        self.assertIn("_muteForAudioExclusivity()", card)
        self.assertIn("window.__luxeEzvizAudioControl = {mute:muteForCoordinator}", player)
        self.assertIn("const requestAudioOwnership = mode =>", player)

    def test_sound_button_and_native_volume_are_coordinated(self):
        player = (COMP / "frontend/player.html").read_text()
        self.assertIn("requestAudioOwnership('sound')", player)
        self.assertIn("audio-exclusivity-failed", player)
        self.assertIn("signal('AUDIO_STATE',{soundOn})", player)
        self.assertIn("const syncSdkSoundFromNativeMute", player)

    def test_talk_mutes_peers_and_keeps_them_muted_afterwards(self):
        player = (COMP / "frontend/player.html").read_text()
        self.assertIn("requestAudioOwnership('talk')", player)
        self.assertIn("signal('TALK_STATE',{talkActive:true})", player)
        self.assertIn("signal('TALK_STATE',{talkActive:false})", player)
        # Ending talk releases the lock; it must not unmute other cards.
        self.assertNotIn("unmuteOther", player)
        self.assertIn("talkOwner", (COMP / "frontend/luxe-ezviz-card.js").read_text())

    def test_talk_stop_failure_keeps_exclusivity_lock(self):
        player = (COMP / "frontend/player.html").read_text()
        start = player.index("const stopTalkByUser")
        end = player.index("const stopTalkForPiP", start)
        block = player[start:end]
        failure = block[block.index("}catch(err){"):]
        self.assertIn("talkActive=true", failure)
        self.assertNotIn("signal('TALK_STATE',{talkActive:false})", failure)


if __name__ == "__main__":
    unittest.main()
