import itertools
import os
from pathlib import Path
import unittest

import numpy as np
import pandas as pd
from transformers import AutoTokenizer

from trainer.core import RowEncoder
from trainer.memory_probe import SelectedRows, longest_rows


class MemoryProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tok = AutoTokenizer.from_pretrained(
            Path(os.environ.get("GPT2_WEIGHTS", "/opt/gpt2")), local_files_only=True)
        frame = pd.DataFrame({"amount": [0.0, 123456.789, 17.5],
                              "category": ["A", "A long merchant category with spaces", "Travel"],
                              "flag": [True, False, None]})
        cls.encoder = RowEncoder(tok, frame, list(frame))

    def test_length_bound_covers_all_orders_labels_and_serializers(self):
        for source in (False, True):
            indices, bound = longest_rows(self.encoder, 100, source=source)
            self.assertEqual(set(indices), {0, 1, 2})
            self.assertEqual(int(indices[0]), 1)
            for row, label, order in itertools.product(
                    range(3), (0, 1), itertools.permutations(range(3 + int(source)))):
                self.assertLessEqual(len(self.encoder.build(row, label, order,
                                                           source=source, eos=True)), bound)

    def test_selected_rows_reuses_full_encoder_and_preserves_row_mapping(self):
        indices, _ = longest_rows(self.encoder, 2)
        selected = SelectedRows(self.encoder, indices)
        self.assertIs(selected.encoder, self.encoder)
        self.assertEqual(len(selected.encoder.frame), 3)
        for local, original in enumerate(indices):
            for source in (False, True):
                order = np.arange(3 + int(source))[::-1]
                self.assertEqual(selected.build(local, 1, order, source=source, eos=True),
                                 self.encoder.build(int(original), 1, order,
                                                    source=source, eos=True))


if __name__ == "__main__":
    unittest.main()
