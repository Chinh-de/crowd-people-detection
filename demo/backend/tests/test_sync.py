from crowd_demo.sync import MAX_DELAY_S, OverlaySync


def run(sync, n, fps=10, lag=0.4, every=5):
    """Giả lập: cứ `every` frame có một kết quả phân tích của frame cách đó `lag` giây."""
    shown = []
    for i in range(n):
        t = i / fps
        if i % every == 0 and t >= lag:
            sync.add_layers(round(t - lag, 3), f"L{t - lag:.1f}", newest_t=t, interval=every / fps)
        out = sync.push(t, i)
        if out is not None:
            shown.append((t, *out))
    return shown


def test_frames_are_delayed_and_matched_to_nearest_layers():
    sync = OverlaySync()
    shown = run(sync, 300)
    for now, frame, layers in shown[-50:]:
        ft = frame / 10
        assert now - ft >= 0.4 + 0.25                       # trễ đủ độ trễ phân tích + nửa chu kỳ
        assert abs(float(layers[1:]) - ft) <= 0.25 + 1e-6   # lớp phủ lệch tối đa nửa chu kỳ phân tích
    frames = [f for _, f, _ in shown]
    assert frames == sorted(set(frames))                    # không lặp, không lùi


def test_delay_is_capped_and_buffer_bounded():
    sync = OverlaySync()
    run(sync, 600, lag=30.0, every=1)
    sync.add_layers(0.0, "x", newest_t=100.0, interval=10.0)
    for i in range(600):
        sync.push(100 + i / 10, i)
    assert sync.delay <= MAX_DELAY_S
    assert len(sync._frames) <= MAX_DELAY_S * 10 + 2


def test_without_analysis_frames_still_flow():
    sync = OverlaySync()
    out = [sync.push(i / 10, i) for i in range(50)]
    assert out[-1] is not None and out[-1][1] is None
