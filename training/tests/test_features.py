from __future__ import annotations

from pathlib import Path

import numpy as np

from grafin_training.data.features import apply_norm, build_codebooks, fit_norm, paper_base_features
from grafin_training.data.load import read_transactions


def test_codebooks_first_appearance(fixture_paths: tuple[Path, Path]) -> None:
    frame = read_transactions(fixture_paths[0])
    books = build_codebooks(frame)
    first_row = frame.sort("row").row(0, named=True)
    assert books.currency[first_row["receiving_currency"]] == 0
    assert books.payment_format[first_row["payment_format"]] == 0
    assert sorted(books.currency.values()) == list(range(len(books.currency)))


def test_base_features(fixture_paths: tuple[Path, Path]) -> None:
    frame = read_transactions(fixture_paths[1])
    base = paper_base_features(frame, build_codebooks(frame))
    assert base.shape == (229, 4)
    assert base[0, 0] == 0 and np.all(np.diff(base[:, 0]) >= 0)
    assert np.all(base[:, 2] == 0)  # localized data: currency is constant IDR


def test_norm_is_fit_on_train_rows_only() -> None:
    rng = np.random.default_rng(0)
    x = rng.normal(size=(100, 3))
    x[:, 2] = 5.0
    train = np.arange(60)
    stats = fit_norm(x, train)
    x2 = x.copy()
    x2[60:] *= 1000  # changing non-train rows must not move the statistics
    stats2 = fit_norm(x2, train)
    assert np.array_equal(stats.mean, stats2.mean) and np.array_equal(stats.std, stats2.std)
    assert stats.std[2] == 1.0
    out = apply_norm(x, stats)
    assert out.dtype == np.float32 and np.allclose(out[:60, :2].mean(axis=0), 0, atol=1e-6)
