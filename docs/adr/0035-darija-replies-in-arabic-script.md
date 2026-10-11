# ADR-0035: A Darija message gets its reply in Darija or Modern Standard Arabic

- Status: Accepted
- Date: 2026-10-11
- Deciders: Fares
- Refines: Gate 3's rules, [ADR-0020](0020-widget-in-english-french-arabic.md)

## Context

Gate 3 tells the answer model to "reply in the customer's language". For English, French and Arabic that is clear. Darija is not one of the widget's languages ([ADR-0020](0020-widget-in-english-french-arabic.md)), and customers write it in Arabic or Latin script.

The first judged benchmark run (#15) showed what models do without a rule. gemma4 answered Acme Pay's 38 Latin-script Darija questions in French 22 times and in Modern Standard Arabic 16 times. It answered the 38 Arabic-script ones in Modern Standard Arabic 37 times and in Darija once.

## Decision

1. A reply to a Darija message is in the customer's language when it is in Darija or in Modern Standard Arabic, in Arabic script.
2. A reply to Latin-script Darija in French is in the wrong language, even though many Algerians read French.
3. The benchmark scores the share of replies in the customer's language per group, as the judge names each reply's language. It is a score, not a release gate.

## Consequences

- Today 16 of 38 replies to Latin-script Darija are in the customer's language, so Gate 3's rules or prompt need work if this share matters before the beta. That is for the model bake-off (#15) to weigh.
- Modern Standard Arabic is an accepted reply to Darija, so a model needs no Darija generation to pass. Darija replies stay welcome.
- If beta customers show they prefer French replies to Latin-script Darija, this record changes.
