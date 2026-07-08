"""V1-3 gate: 校准 + 选择性分类指标。"""

from birdbench.calibration import (
    aurc,
    auroc_correctness,
    brier,
    e_aurc,
    overconfidence_gap,
    selective_acc_at,
)


def test_auroc_correctness():
    # 对的都高置信、错的都低 → 完美分开 = 1.0
    assert auroc_correctness([(0.9, True), (0.8, True), (0.2, False), (0.1, False)]) == 1.0
    assert auroc_correctness([(0.1, True), (0.9, False)]) == 0.0  # 反向
    assert auroc_correctness([(0.9, True), (0.8, True)]) == 0.5  # 单类 → 瞎猜


def test_brier():
    assert brier([(1.0, True), (0.0, False)]) == 0.0  # 完美校准
    assert abs(brier([(0.0, True)]) - 1.0) < 1e-9


def test_overconfidence_gap():
    # 置信 0.9 但全错 → gap 0.9（过度自信）
    assert abs(overconfidence_gap([(0.9, False), (0.9, False)]) - 0.9) < 1e-9
    assert abs(overconfidence_gap([(0.5, True), (0.5, False)]) - 0.0) < 1e-9


def test_aurc_and_selective():
    good = [(0.9, True), (0.8, True), (0.2, False)]
    bad = [(0.2, True), (0.9, False), (0.8, False)]  # 排序反了
    assert selective_acc_at(good, 0.5) == 1.0  # 最自信的一半全对
    assert aurc(good) < aurc(bad)  # 好排序 AURC 更低
    assert abs(e_aurc(good)) < 1e-9  # 完美排序 → E-AURC=0


def test_empty_safe():
    assert auroc_correctness([]) == 0.5
    assert aurc([]) == 0.0 and e_aurc([]) == 0.0
