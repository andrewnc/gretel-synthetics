from pathlib import Path

import faker
import numpy as np
import pandas as pd
import pytest

from gretel_synthetics.utils import stats


@pytest.fixture(scope="module")
def fake():
    fake = faker.Faker("en_US")
    return fake


def test_count_memorized_lines(fake: faker.Faker):
    records1 = []
    records2 = []
    records3 = []
    for _ in range(10):
        records1.append(
            {"foo": fake.lexify(text="????????"), "bar": fake.lexify(text="????????")}
        )
        records2.append(
            {"foo": fake.lexify(text="????????"), "bar": fake.lexify(text="????????")}
        )
        records3.append(
            {"foo": fake.lexify(text="????????"), "bar": fake.lexify(text="????????")}
        )
    df1 = pd.DataFrame(records1 + records2)
    df2 = pd.DataFrame(records2 + records3)
    df_intersection = pd.DataFrame(records2)
    assert stats.count_memorized_lines(df1, df2) == len(
        set(df_intersection.to_csv(header=False, index=False).strip("\n").split("\n"))
    )


def test_get_categorical_field_distribution():
    df = pd.DataFrame(
        [{"foo": "bar"}] * 2 + [{"foo": "baz"}] * 2 + [{"foo": "barf"}] * 4
    )
    distribution = stats.get_categorical_field_distribution(df["foo"])
    assert distribution["bar"] == 25.0
    assert distribution["baz"] == 25.0
    assert distribution["barf"] == 50.0


def test_compute_distribution_distance():
    # Based on examples at
    # https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.distance.jensenshannon.html
    # BUT NOTE that we use base 2 throughout, some examples don't.
    # Mostly want to test that we feed values into this function correctly.
    d1 = {"foo": 1.0, "baz": 0.0}
    d2 = {"bar": 1.0, "baz": 0.0}
    assert abs(stats.compute_distribution_distance(d1, d2) - 1.0) < 0.01

    d1 = {"foo": 1.0, "baz": 0.0}
    d2 = {"foo": 0.5, "baz": 0.5}
    assert abs(stats.compute_distribution_distance(d1, d2) - 0.5579230452841438) < 0.01

    d1 = {"foo": 1.0, "bar": 0.0, "baz": 0.0}
    d2 = {"foo": 1.0}
    assert abs(stats.compute_distribution_distance(d1, d2)) < 0.01


def test_numeric_binning_sanity():
    # walk through the steps that gave us too many bins in CORE-316
    train_path = Path(__file__).parent / "data/train.csv"
    train = pd.read_csv(train_path)

    synth_path = Path(__file__).parent / "data/synth.csv"
    synth = pd.read_csv(synth_path)

    train_rows, train_cols = train.shape
    synth_rows, synth_cols = synth.shape
    max_rows = min(train_rows, synth_rows)
    train_subsample = (
        train.sample(n=max_rows, random_state=333) if train_rows > synth_rows else train
    )
    synth_subsample = (
        synth.sample(n=max_rows, random_state=333) if synth_rows > train_rows else synth
    )

    pca_train = stats.compute_pca(train_subsample)
    pca_synth = stats.compute_pca(synth_subsample)

    found_bad_column = False
    for field in pca_train.columns:
        min_value = min(min(pca_train[field]), min(pca_synth[field]))
        max_value = max(max(pca_train[field]), max(pca_synth[field]))
        # Use ‘fd’ (Freedman Diaconis Estimator), our default binning.
        # We are looking for a "bad" column that will give us too many bins.
        fd_bins = np.histogram_bin_edges(
            pca_train[field], bins="fd", range=(min_value, max_value)
        )
        if len(fd_bins) > 500:
            # We found a bad column. Set the flag and show that 'doane' will give us a more manageable number of bins.
            found_bad_column = True
            bins = stats.get_numeric_distribution_bins(
                pca_train[field], pca_synth[field]
            )
            assert len(bins) < 500

    assert found_bad_column
