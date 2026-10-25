from __future__ import annotations

from frame_server.device.wol import broadcast_targets, magic_packet


def test_magic_packet() -> None:
    packet = magic_packet("aa:bb:cc:dd:ee:ff")
    assert packet[:6] == b"\xff" * 6 and packet[6:12] == bytes.fromhex("aabbccddeeff")
    assert len(packet) == 102


def test_targets_include_the_panel_itself() -> None:
    # The unicast copy is the one a router forwards from another subnet.
    assert broadcast_targets("192.168.1.152") == [
        "255.255.255.255",
        "192.168.1.255",
        "192.168.1.152",
    ]
    assert broadcast_targets(None) == ["255.255.255.255"]
