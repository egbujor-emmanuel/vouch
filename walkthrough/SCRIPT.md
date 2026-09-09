# Vouch demo, voiceover script

Every line below is on screen as a caption while the video plays, and each word
lights up as it is meant to be spoken. Read along with the highlight and you stay
in time without watching a clock. The small grey line under each caption is a
section marker for your own place keeping, do not read it out.

This is the full walkthrough, `vouch-demo.mp4`. Use it for the hackathon
submission form. It is too long for an X account without Premium.

22 lines, 568 words, 4 minutes 58 seconds. Paced at 152 words a minute.

**1. the problem**

Agents are hiring other agents now. It is happening on Base today. One agent posts a job, another one takes it, money moves, and no person checks any of it.

**2. the standard**

So they run into the question you get on eBay. Can I trust this one. There is a standard for that, ERC-8004, and it puts a reputation score for every agent on chain.

**3. the gap**

But I read the spec and found two fields at the end. One holds a link to what actually happened. The other holds a fingerprint that proves the account was not edited later. Both are optional. Both are empty, everywhere I looked.

**4. memory is load-bearing**

Before I show you any of that, the hackathon has one test. Take the memory layer out, and if your project still works, you are out. I turned that test into a switch.

**5. fresh session**

Memory is on right now. This agent has never dealt with newcomer, but two other agents filed reports about them, so it says no.

**6. the test**

Watch what happens when I switch the memory off.

**7. memory deleted**

Same code. Same counterparty. Same request. Now it quotes the standard price, because with no memory there is nothing to score, nothing to seal and nothing to publish. A fraudster and a saint get the same quote.

**8. the gate**

Switch it back on and it refuses again. That is the point. It does not get worse without memory. It stops existing.

**9. no local state**

This browser has never seen any of these agents before. Everything on this page is read off the chain and checked on your own machine.

**10. coordination**

These are filings other agents published about the same counterparty. Two of them, from two separate wallets that cannot read each other's memory.

**11. verified in your browser**

For each one your browser downloads the file and hashes it again. The seal on chain, and the seal computed here. They match, so the filing is admitted. Nothing here asks you to take my word for it.

**12. appendresponse**

The standard also ships a right of reply. As far as I can tell, nobody uses it. So I did. The accused agent files its own account, sealed the same way.

**13. both sides**

Now both sides are on the record. A record with only the accuser on it is a rumour. With both of them sealed, it is evidence.

**14. tamper check**

Which raises the obvious question. Could someone just fake this?

**15. seal broken**

So I take a real filing, edit it in the browser to erase the dispute, and hash it again. One field changed and the seal moves. It gets thrown out. Your browser computed both of those hashes.

**16. try it yourself**

You can run this against any agent id on the registry.

**17. live, nothing cached**

It is querying the registry now. Pulling the logs, fetching each evidence file, and hashing it here.

**18. live query**

Two raters, two filings, two seals verified, and the testimony pulled back out of them. Not a score. The account behind it.

**19. sibyl memory**

All of this sits on Sibyl Memory. Five tiers, one row for each counterparty, duplicates blocked by the schema itself, and a journal that only ever gets added to.

**20. append only**

So when the agent cites a dispute, it is quoting a record. It is not making one up.

**21. base and virtuals acp**

Every filing you just saw is a real transaction on Base. And Vouch sells this as a live service on Virtuals ACP, so any agent can buy a counterparty check instead of running one.

**22. vouch**

Everyone here is building agents that remember. I built the layer that lets them tell each other.
