# Review Your Account Activity With Fresh Features

This tutorial builds a small account-activity review from your own traffic in
the public demo. It is designed to explain unusual behavior, not to make an
automated fraud decision.

The access-log source derives the same eight-character email hash used for
self-lookup directly in Spark. The raw email is not selected into the activity
feature GroupBy.

## What The Review Uses

The review joins authenticated UI requests to the privacy-safe `email_hash`,
then computes activity over one-day and six-day windows:

- Request, error, and write counts
- Approximate distinct IP, user-agent, and route counts
- The five most recent IPs, user agents, and paths
- Ten recent activity events
- Latest and worst one-day ingestion freshness lag

The `app.account_activity_review.account_activity_review` Join packages those
signals with identity first-seen and last-seen fields for one online fetch.

## 1. Generate Activity

Sign in to [try.zipline.ai](https://try.zipline.ai), visit a few pages, and run
one or two searches. Authenticated activity reaches the online GroupBy through
Kinesis, while the offline Iceberg table advances on its configured cadence.
That intentional difference is what makes freshness visible in the consistency
view.

## 2. Build And Deploy

From `configs`, evaluate each new layer:

```bash
zipline hub eval compiled/group_bys/app/email_request_activity.email_request_activity
zipline hub eval compiled/joins/app/account_activity_review.account_activity_review
```

Run the chained GroupBy and review Join so their offline results are uploaded
for online fetching:

```bash
zipline hub run-adhoc compiled/group_bys/app/email_request_activity.email_request_activity
zipline hub run-adhoc compiled/joins/app/account_activity_review.account_activity_review
```

Deploy the GroupBy to start its Flink streaming job:

```bash
zipline hub schedule compiled/group_bys/app/email_request_activity.email_request_activity
```

The Join is fetched on demand and does not need a separate streaming job.

## 3. Change A Signal

Edit `configs/group_bys/app/email_request_activity.py`, add or modify a window,
increment the GroupBy version, and then increment the dependent Join version.
Evaluate and run both layers again. The online fetch now returns the evolved
feature payload without embedding feature computation in application code.

## 4. Ask A Coding Agent To Review Your Activity

The coding agent can inspect the repository, derive your lookup key locally,
fetch the Join, and reason about freshness without an additional integration
script or API key. Replace the email placeholder, then paste this prompt into a
coding environment opened at the repository root:

```text
Review the Zipline public-demo account activity for <YOUR_GOOGLE_ACCOUNT_EMAIL>.

Work from this repository and use its Zipline demo skill and teams.py settings.
Find the appropriate account-activity Join, derive the eight-character email
hash locally, and fetch the current online features through the Zipline CLI.
Do not send the plaintext email to Zipline and do not modify or deploy configs.

First assess whether the feature data is fresh enough to interpret. Then classify
the evidence as NORMAL, UNUSUAL, or INSUFFICIENT_DATA. This is investigative
guidance, not a fraud verdict, and must not trigger an automated enforcement
action.

Pay attention to request volume, distinct IP and user-agent counts, write and
error activity, recent paths, and freshness lag. Do not infer identity, physical
location, or intent from an IP address or user agent.

Return:
1. The classification.
2. Two or three concrete observations grounded in the fetched features.
3. A freshness and data-quality caveat.
4. One reasonable next verification step.
```
