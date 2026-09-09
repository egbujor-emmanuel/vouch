# Vouch demo, narration

This is what is spoken in `vouch-demo.mp4`, and it is also what appears as the
caption, one word lit at a time. The voice on the file is synthesised
(en-US-AndrewNeural). If you would rather use your own, record against these
timings and the highlight still lines up.

18 lines, 464 words, 144 seconds of speech in a 3:10 video.

| # | at | section | line |
|---|---|---|---|
| 1 | 0:01.5 | who has this problem | If you are running an agent that takes jobs from other agents, on Base or on an ACP marketplace, you have a problem. Your agent is dealing with strangers, and it has no way to check any of them. |
| 2 | 0:12.5 | the standard | There is a standard for this. ERC 8004. It gives every agent a reputation score, stored on chain. |
| 3 | 0:19.6 | the gap | But there are two fields for the evidence behind that score. A link, and a hash. I went looking, and they're empty everywhere. So you get a number with nothing you can actually check. |
| 4 | 0:29.5 | what vouch is | Vouch is the layer that fills them. Your agent writes down what a counterparty actually did, seals that with a hash, and files the seal on Base. Other agents read it and check it themselves. |
| 5 | 0:42.2 | the decision | Here it is deciding. This agent has never worked with newcomer, but two other agents filed reports about them. It reads those, and it says no. |
| 6 | 0:50.8 | fresh session | And this is a fresh session. Nothing was carried over from the last run. It recalls the counterparty out of Sibyl Memory, pulls the filings off the registry, and that is where the refusal comes from. |
| 7 | 1:01.8 | the test | Now watch. I'm switching its memory off. |
| 8 | 1:06.4 | memory deleted | Same code, same request, and it takes the job at full price. There is nothing to recall, so everybody looks fine. |
| 9 | 1:15.2 | memory back on | Turn it back on and it refuses again. This isn't a feature that gets worse without memory. There is nothing left of it. |
| 10 | 1:23.5 | checked in your browser | Your browser downloads each filing and hashes it itself. The hash that's on chain, and the hash it just worked out. They match, so the filing counts. |
| 11 | 1:32.8 | two wallets | The two reports came from separate wallets that can't see each other's memory. They only line up because both of them are on the registry. |
| 12 | 1:41.8 | both sides | The standard also lets a rated agent reply, and nobody uses it. Here the accused agent files its own answer, sealed the same way, so you get both sides. |
| 13 | 1:55.5 | tamper check | And if someone edits a filing afterwards, say to delete the dispute, the hash changes and it gets dropped. |
| 14 | 2:20.3 | try it yourself | You can put any agent id in here and it queries the registry live. Two raters, two filings, both seals checked, and the statements pulled back out. |
| 15 | 2:31.1 | sibyl memory, entities | All the memory here is Sibyl. One row per counterparty in the entity tier, and duplicates are blocked by the schema itself, not by convention. |
| 16 | 2:41.3 | sibyl memory, journal and policy | What happened to them goes in the journal, which only ever gets added to. And the trust rules sit in the reference tier, so I can change policy without touching code. |
| 17 | 2:51.6 | the stack | Every filing is a real transaction on Base, and Vouch sells the check as a service on Virtuals ACP, so another agent can just buy one. |
| 18 | 3:02.3 | vouch | Everyone is building agents that remember. I built the part that lets them tell each other. |
