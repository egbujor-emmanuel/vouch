# Vouch demo, narration

This is what is spoken in `vouch-demo.mp4`, and it is also what appears as the
caption, one word lit at a time. The voice in the file is a synthesised one
(en-US-AndrewNeural), so if you would rather use your own, record against these
timings and the highlight still lines up.

15 lines, 353 words, 112 seconds of speech in a 2:30 video.

| # | at | section | line |
|---|---|---|---|
| 1 | 0:01.6 | the setup | Agents are hiring other agents on Base. There's a standard for reputation called ERC 8004, and it stores a score for each agent. |
| 2 | 0:10.6 | the gap | There are two fields for the evidence behind that score. A link, and a hash. I went looking, and they're empty everywhere. So you get a number with nothing you can actually check. |
| 3 | 0:21.7 | memory on | So I filled them. This agent has never worked with newcomer, but two other agents filed reports about them, and it can read those. It says no. |
| 4 | 0:30.1 | fresh browser | And this is a fresh browser. It has never seen these agents. Everything you're looking at is read off the chain right here. |
| 5 | 0:36.7 | the test | Now watch. I'm switching its memory off. |
| 6 | 0:41.2 | memory deleted | Same code, same request, and it takes the job at full price. There's nothing to look up, so everybody looks fine. |
| 7 | 0:49.8 | memory back on | Turn it back on and it refuses again. This isn't a feature that gets worse without memory. There's nothing left of it. |
| 8 | 0:58.0 | checked in your browser | Your browser downloads each filing and hashes it itself. The hash that's on chain, and the hash it just worked out. They match, so the filing counts. |
| 9 | 1:07.2 | two wallets | The two reports came from separate wallets that can't see each other's memory. They only line up because both of them are on the registry. |
| 10 | 1:16.3 | both sides | The standard also lets a rated agent reply, and nobody uses it. Here the accused agent files its own answer, sealed the same way, so you get both sides. |
| 11 | 1:30.0 | tamper check | And if someone edits a filing afterwards, say to delete the dispute, the hash changes and it gets dropped. |
| 12 | 1:48.3 | try it yourself | You can put any agent id in here and it queries the registry live. Two raters, two filings, both seals checked, and the statements pulled back out. |
| 13 | 1:59.1 | sibyl memory | Underneath it's Sibyl Memory. Five tiers, one row per counterparty, and a journal that only gets added to. So a dispute it quotes is a record it actually holds. |
| 14 | 2:10.9 | the stack | Every filing is a real transaction on Base, and Vouch sells the check as a service on Virtuals ACP, so another agent can just buy one. |
| 15 | 2:21.6 | vouch | Everyone's building agents that remember. I built the part that lets them tell each other. |
