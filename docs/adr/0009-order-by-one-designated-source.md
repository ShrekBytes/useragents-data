# Published records are ordered by one designated source's frequency

> The rule, in one line: `pipeline.ORDERING_SOURCE` measures it, or it is not ranked.

## The problem this exists to prevent

Once two sources publish counts, the obvious thing to do to `order_records` is sort
by `count`. That silently asserts a popularity the data does not support.

A count is a property of a sample. 10,000 hits in one site's traffic and 5 in
another's do not mean the first is 2,000 times more common; they mean one site saw
it 10,000 times and the other saw it 5 times. Interleaving the two produces a
ranking whose numbers were never comparable, and every consumer of the file — most
of all the `most_common_*` legacy files, which exist to answer "what do people
actually send" — would read it as one.

Summing is worse and averaging is nonsense. Both invent a number no source measured.

## The rule

1. `ORDERING_SOURCE` is designated in `uadata/pipeline.py`. It is a decision about
   what a published ranking *is*, not a preference.
2. A record is **ranked** only if that source measured it. Its block leads the file,
   in descending count.
3. Every other record follows: measured by someone else, or by no one. They are
   ordered by newest browser version, then by the string. They keep their `count`,
   attributed, but it does not buy them a position.
4. `count` and `percentage` are published with `count_source` naming the source that
   measured them. A count with no attribution is refused at construction, not at
   publication — by then the record has already been filed into the unranked block
   where nobody would notice.

`count_source` is not redundant with `sources`. A source can confirm that a string
exists without saying how often it was seen, and that difference is the whole point:
crawler-user-agents confirms hundreds of strings that no source has measured.

## Consequences, stated rather than discovered later

**The reservation is now a reservation for unranked records.** ADR-0007 reserved 20
slots per category so a flood of measured traffic could not evict every current
browser; the constant is now `RESERVED_UNRANKED` because the boundary moved, not the
rule. A second counting source's traffic does not get to spend that budget on a
ranking the pipeline never made: its records are ordered and capped as unranked, so
they sort by version with everything else and the current strings still win.

**`common/<category>.json` is the ordering source's ranking and nothing else.** It
is a list of plain strings with no numbers attached, read as "the most common".
Publishing another source's measurements there would present two samples as one
ranking. So on a run where the ordering source is down, `common/` publishes an empty
list.

That is the honest result: no source measured anything, so there is no "most common"
to publish. `data/` still carries every current string we do hold, with a null
count, full provenance, and a build that says which source is down. An empty
`common/` for one week is a better outcome than a stale list that looks current —
which is the failure this repository already spent 13 months on.

**Adding a second counting source requires choosing between them.** That is a real
cost and it is the point: the moment counts from two samples are comparable is the
moment the file stops being able to say what it is.
