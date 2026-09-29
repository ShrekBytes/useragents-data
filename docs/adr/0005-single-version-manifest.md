# One version manifest serves both synthetic generation and the staleness assertion

A single manifest of currently-shipping browser and OS versions is the input to two
otherwise unrelated jobs:

1. **Generating Synthetic UAs** — versions must be real or the strings are worthless.
2. **Asserting freshness** — the run fails if the maximum browser version in the
   collected Observed UAs falls behind the manifest.

The same artifact serves both because they are the same question asked in two
directions. The manifest describes what is shipping now; synthetic UAs are built
from it, and observed data is checked against it. Keeping two independent lists
would let them disagree, which would reintroduce exactly the class of silent
staleness this work exists to eliminate.

The synthetic output is additionally held to a structural-fidelity bar: every
generated UA must be identified correctly by `uap-core` / `ua-parser`, asserted in
CI, and must not collide with any string in the observed corpus.
