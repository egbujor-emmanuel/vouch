# Submission assets

Drafts for the two required build-in-public posts and the PMF outreach. Nothing
here is posted automatically — copy, edit in your own voice, and post yourself.

Requirements from the rules: a demo video post and at least one build-log post,
both tagging **@sibylcap** and every partner claimed (**@base**, **@virtuals_io**).

---

## Post 1 — build log

> ERC-8004 went live on Base. It stores agent reputation as a number.
>
> Read the spec and there are two fields for the evidence behind that number:
>
> `string feedbackURI`
> `bytes32 feedbackHash`
>
> Both marked OPTIONAL. Both empty, everywhere.
>
> We spent the @sibyl_labs_ hackathon filling them.
>
> Vouch: an agent writes down what a counterparty actually did, seals it with
> keccak-256, and publishes the seal to @base. A different agent — one that has
> never met them — reads it, re-checks the hash itself, and refuses the job.
>
> Two things nobody else is doing:
>
> → the evidence is hash-committed, so a filing edited after publication is
> detectable and gets discarded rather than believed
> → we exercised `appendResponse`, the right of reply that ships in the standard
> and that nobody uses. Both sides of a dispute, both sealed.
>
> Memory is load-bearing by construction. Delete it and there is nothing to
> score, nothing to hash and nothing to publish — the product doesn't degrade,
> it stops existing.
>
> Built on Sibyl Memory, @base, @virtuals_io.
>
> Look up any agent yourself: <LIVE URL>

**Attach:** a screenshot of the lookup panel showing `seal recorded on chain` and
`seal recomputed here` matching, with the VERIFIED pill.

---

## Post 2 — demo video

> Agents have started hiring each other. None of them can check who cheated
> them last week.
>
> 3 minutes on what we built for the @sibyl_labs_ hackathon.
>
> Vouch turns an agent's memory into evidence other agents can verify:
> ERC-8004's `feedbackURI` and `feedbackHash` are specified and empty — we fill
> them, and your browser re-checks every seal so you never have to trust us.
>
> In the video:
> • a counterparty disputes a job and short-pays; the agent writes it down
> • the account is sealed and filed on @base
> • an unrelated agent files its own account of the same counterparty
> • a fresh process that has never met them reads both, verifies both, refuses
> • a forged filing gets caught by the hash
>
> Memory is load-bearing: delete it and it accepts everyone at the same price.
>
> Sibyl Memory + @base + @virtuals_io
> Repo: github.com/egbujor-emmanuel/vouch
> Live: <LIVE URL>

---

## PMF outreach

The rules award up to 10 points for "a named audience with a validated pain
point, a waitlist or design partners, real usage, or pilots", and require the
evidence to be publicly verifiable. **Fabricated evidence is a disqualification**,
so everything below asks for a real reaction and records exactly what was said.

### Who, specifically

Teams building ACP agents on Virtuals, and hackathon teams whose agents take
work from counterparties they cannot check. They have the problem today. From
the public repos in this hackathon alone, several build agents that decide
whether to trust a counterparty using memory that is private to themselves —
which is precisely the gap Vouch closes.

### The message

> Hey — we built something during the Sibyl hackathon that might be useful to
> you rather than competitive with you.
>
> Your agent keeps memory about counterparties. So does ours. Neither of us can
> read the other's, so if a counterparty burns you, my agent still walks into
> it next week.
>
> ERC-8004 has two fields for exactly this — `feedbackURI` and `feedbackHash` —
> and they're empty everywhere because the spec marks them optional. We filled
> them: publish your account of a counterparty, sealed with a hash, and any
> other agent can read and verify it.
>
> Takes four commands and nothing about your stack has to change:
>
> ```
> python -m vouch decide --handle acme --price 25 --agent-id 9178
> python -m vouch record --handle acme --kind dispute --detail "short-paid by 60%"
> python -m vouch rate   --handle acme --publish --network base-sepolia
> python -m vouch network --agent-id 9178
> ```
>
> Every command emits JSON, so it works from any language.
>
> You can check it without installing anything — look up any ERC-8004 agent
> here: <LIVE URL>. Most come back with a score and no evidence attached, which
> is the whole problem.
>
> Would this be useful to you? Happy to wire it into your agent myself.

### The hook that does the work

Ask them to look up **their own agent id**. Almost every agent on the registry
comes back with ratings that carry no evidence at all. Nobody argues with a
demonstration of their own record.

### What counts as evidence, and where to put it

| Evidence | Where it lives |
|---|---|
| A builder replying publicly that they would use it | quote-tweet or Discord permalink |
| Another team filing to the registry | their transaction on Basescan — irrefutable |
| A named design partner | their public agreement, in their own words |
| Waitlist signups | a public form with a visible count |

Put the links in the README under a **Traction** heading and in the submission
notes. Screenshot anything that could be edited later.

**Do not** paraphrase anyone into sounding more committed than they were. A
lukewarm real quote scores; an enthusiastic invented one disqualifies.
