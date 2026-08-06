from tower_referee.hud_layout import calculate_hud_layout, rectangles_intersect


def test_official_hud_card_stays_in_left_letterbox():
    layout = calculate_hud_layout(1600, 900)

    assert layout.commander_card is not None
    assert not rectangles_intersect(layout.commander_card, layout.playfield)
    assert layout.commander_card.right <= layout.left_letterbox.right
    assert layout.scrollable is True


def test_wide_recording_layouts_keep_card_outside_game_viewport():
    for width, height in ((1920, 1080), (2560, 1440), (1280, 720)):
        layout = calculate_hud_layout(width, height)
        assert layout.commander_card is not None
        assert not rectangles_intersect(layout.commander_card, layout.playfield)


def test_narrow_layout_never_falls_back_to_cover_game_viewport():
    layout = calculate_hud_layout(1024, 768)

    assert layout.commander_card is None
    assert layout.scrollable is False
