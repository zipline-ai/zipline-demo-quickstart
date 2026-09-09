# Your First Zipline Feature In Five Minutes

In this tutorial, you will fetch features built from your own activity on the
Zipline demo, inspect how Zipline produced them, and see the same definition
used for historical computation and online serving.

## 1. Create Some Activity

Sign in to [try.zipline.ai](https://try.zipline.ai) with Google and visit a few
pages. The demo converts its Kubernetes access and authentication logs into
privacy-safe feature data. It stores an eight-character SHA-256 prefix of your
normalized email rather than your email address.

From the repository root, calculate your lookup key. Omitting the email keeps it
out of your shell history:

```bash
python3 scripts/email_hash.py
```

You can also pass it directly:

```bash
python3 scripts/email_hash.py you@example.com
```

Save the printed value:

```bash
export MY_EMAIL_HASH="YOUR_8_CHARACTER_HASH"
```

## 2. Fetch Your Features

Set the demo endpoints and move into the config project:

```bash
export HUB_URL="https://try.zipline.ai/services/hub"
export FETCHER_URL="https://try.zipline.ai/services/fetcher"
cd configs
export PYTHONPATH="$(pwd):${PYTHONPATH:-}"
```

Fetch the deployed profile:

```bash
zipline hub fetch \
  compiled/joins/app/email_activity_profile.email_activity_profile__5 \
  --hub-url "$HUB_URL" \
  --fetcher-url "$FETCHER_URL" \
  --key-json "{\"email_hash\":\"$MY_EMAIL_HASH\"}" \
  --format json
```

The response includes when you were first and last seen, your latest
authentication event, whether you are a returning user, and only the final
eight characters of Zipline's opaque user ID. There is no full email or user ID
in the fetch payload.

If the result is empty, wait for the demo's ingestion cycle after signing in and
try again.

## 3. Follow The Data

Open `app.email_activity_profile.email_activity_profile__5` in the Zipline UI.
Its lineage is deliberately small:

```text
Kubernetes authentication logs
        |
        v
privacy-safe identity snapshots
        |
        v
email_identity GroupBy
        |
        v
email_activity_profile Join
        |
        v
online fetch
```

Three Zipline concepts produce the result:

- A **Source** describes the raw identity snapshots.
- A **GroupBy** builds reusable features keyed by `email_hash`.
- A **Join** assembles those features into the view fetched by an application.

## 4. Add A Feature

Open `configs/joins/app/email_activity_profile.py` from the repository root and
add this item to `derivations`:

```python
Derivation(
    name="identity_age_hours",
    expression=(
        "(profile_email_hash_last_seen_ts - "
        "profile_email_hash_first_seen_ts) / 3600000.0"
    ),
),
```

Increment the Join version before compiling. Online configurations are
immutable because applications may already depend on their schemas.

Then evaluate the new compiled version:

```bash
zipline compile
zipline hub eval \
  compiled/joins/app/email_activity_profile.email_activity_profile__NEW_VERSION \
  --hub-url "$HUB_URL"
```

Eval checks the output schema, dependencies, and lineage without changing the
serving deployment.

## 5. Deploy And Trust The Result

Deploy the evaluated version:

```bash
zipline hub run-adhoc \
  compiled/joins/app/email_activity_profile.email_activity_profile__NEW_VERSION \
  --hub-url "$HUB_URL" \
  --skip-compile \
  --yes
```

After the workflow succeeds, run the fetch command again with the new compiled
path. `identity_age_hours` is now available online using the same feature
definition Zipline uses in historical computation.

That is the core workflow: define a feature once, inspect its lineage, compute
its history, serve it online, and measure whether the online value agrees with
the offline result. The demo's ingestion cadence controls the tradeoff between
freshness and cost, while its freshness features make that tradeoff visible
instead of implicit.
