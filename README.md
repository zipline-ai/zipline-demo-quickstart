# Zipline Demo Quickstart

Learn to build features, train models, and compare experiments in the Zipline public demo.
The tutorials use ready-to-use datasets and example configs.

New here? Start with [your first Zipline feature in five minutes](docs/tutorials/quickstart.md).

For follow-up exercises, see the other [tutorials](docs/tutorials/).

For model training, follow [compare two models in a trial](docs/tutorials/model-experiment-comparison.md)
to track the two prepared models in a trial and compare measured results.

Using a coding assistant? Install the Zipline CLI and initialize its agent context
from the repository root:

```bash
python -m pip install --upgrade zipline-ai
zipline init-agent
```

Choose your assistant when prompted, then ask it to help you explore the data,
follow lineage, and work through the tutorials.

See [demo data sources](docs/data_sources.md) for dataset schemas, feature lineage, and freshness behavior.

The live public demo endpoints are:

- UI: [https://try.zipline.ai](https://try.zipline.ai)

By using the public demo, you agree to its [Terms of Service](TERMS.md). See the
[Privacy Policy](PRIVACY.md) for details about Google sign-in, access logs, Demo
datasets, retention, and your choices.

Online features update as new activity arrives, while offline features refresh
periodically. Compare their freshness to understand how delayed data affects
feature values and model inputs.
