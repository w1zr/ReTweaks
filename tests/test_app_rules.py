import core.app_rules as R
import core.tweaks as tw
from tests.test_tweaks import FakeReg


def test_gpu_and_fso_keep_other_flags_and_restore(monkeypatch):
    reg = FakeReg()
    monkeypatch.setattr(R, "REG", reg)
    rule = R.new_rule(r"C:\Games\Fortnite\FortniteClient-Win64-Shipping.exe")
    exe = rule["exe"]
    reg.set(R.LAYERS_PATH, exe, tw.REG_SZ, "~ RUNASADMIN")          # user's own compatibility flag
    assert R.set_gpu(rule, "High performance GPU")[0]
    assert reg.get(R.GPU_PATH, exe)[1] == "GpuPreference=2;"
    assert R.get_gpu(rule) == "High performance GPU"
    assert R.set_fso(rule, True)[0]
    assert reg.get(R.LAYERS_PATH, exe)[1] == "~ RUNASADMIN DISABLEDXMAXIMIZEDWINDOWEDMODE"
    assert R.get_fso_off(rule)
    assert R.remove_rule_settings(rule)[0]
    assert reg.get(R.GPU_PATH, exe) is None                         # didn't exist before
    assert reg.get(R.LAYERS_PATH, exe)[1] == "~ RUNASADMIN"         # user's flag kept


def test_fso_off_then_on_removes_value_if_it_was_the_only_flag(monkeypatch):
    reg = FakeReg()
    monkeypatch.setattr(R, "REG", reg)
    rule = R.new_rule(r"C:\x\game.exe")
    R.set_fso(rule, True)
    R.set_fso(rule, False)
    assert reg.get(R.LAYERS_PATH, rule["exe"]) is None
