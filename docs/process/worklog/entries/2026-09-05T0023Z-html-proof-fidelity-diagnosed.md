# 1. HTML proof fidelity diagnosed

The Navigator reported missing visual styling in the proof HTML. The
[capture investigation](../../../project/debt/items/html-proof-captures-omit-assets-and-root-attributes.md)
confirmed that all 33 PR80/PR83 HTML files omit the outer document element and
reference remote assets. A network-disabled browser reproduced missing styling
and 19 broken images on the final PR83 page. Enabling networking restored fonts
and images; restoring the missing theme attributes separately restored the dark
background. This isolates two independent defects in the capture path.

Proof narratives and manifest limitations now distinguish serialized DOM from
self-contained visual evidence. Original artifacts and archive hashes remain
unchanged. No production or GitHub operation was needed. Asset packaging and
historical recovery remain open, with network-disabled visual verification
required for a future correction.
