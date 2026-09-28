"""Editing the edit buffer outside scene 1 halts the Ampero's firmware (SceneNum == SCENE_1):
the CLI refuses before sending anything. Never opens a real MIDI port."""
import ampero2.cli as cli


class FakeAmpero:
    def __init__(self, scene):
        self.scene, self.sent = scene, []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def request(self, frame, timeout=1.0):
        class F:
            payload = bytes([0] * 64)
        f = F()
        f.payload = bytes(cli.SCENE_REPLY_INDEX) + bytes([self.scene - 1]) + bytes(8)
        return f

    def send(self, frame):
        self.sent.append(frame)


def _run(monkeypatch, scene, argv):
    dev = FakeAmpero(scene)
    monkeypatch.setattr(cli, "Ampero", lambda: dev)
    return cli.main(["ampero2", *argv]), dev


def test_an_edit_on_scene_4_is_refused_and_nothing_is_sent(monkeypatch, capsys):
    code, dev = _run(monkeypatch, 4, ["param", "3", "2", "70"])
    assert code == 4 and dev.sent == []
    assert "scene 1" in capsys.readouterr().err


def test_setting_the_input_source_counts_as_an_edit(monkeypatch):
    code, dev = _run(monkeypatch, 2, ["input-source", "usb34"])
    assert code == 4 and dev.sent == []


def test_edits_on_scene_1_and_scene_changes_go_through(monkeypatch):
    assert _run(monkeypatch, 1, ["param", "3", "2", "70"])[1].sent
    assert _run(monkeypatch, 4, ["scene", "1"])[1].sent
