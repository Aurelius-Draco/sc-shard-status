# Roadmap

## v2: community shard status

- Opt-in sharing. Every minute or so the app sends one shard reading (`community.shard_report`): shard id, server
  node number, server fps and range, hitches, restarts, shard and server population, ping rounded to 10 ms, packet
  loss, known issue ids seen. Never the handle, other players' names, account numbers, session ids or IP addresses.
  The exact payload is already built in v1 and shown on request.
- Public board: live health for every shard, built from the median of everyone reporting on it, outliers dropped, so
  one bad or fake reading can't sink a shard. History resets with each patch (shard ids include the build).
- Shard hop advice: your shard against the others in your region right now.
- Known issues pages: plain-English explanation, the main Issue Council report and duplicates under it, related
  links (patch notes, Spectrum, wiki), how many players hit it today and this week, and "not seen since build X,
  likely fixed" when it stops turning up.
- Link suggestions from players, limited to RSI (Issue Council, Spectrum, patch notes) and the Star Citizen wiki,
  reviewed before they show; trusted contributors later.
- Review queue for unrecognised errors: deduplicated by signature, checked in batches, turned into library entries;
  the app tells the player their ticket was answered next time it starts. Optional private screenshot with chat and
  the QR code blurred, deleted once identified.
- Hardware comparison: your fps against players with a similar CPU and GPU benchmark at the same location.
- Live bug board: contracts failing for most players right now.

Hosting: small enough to start on a free tier (text payloads only, no public images).

## Later

- Single-file exe.
- Linux (Wine/Proton) screen capture.
- Shared theme and code with SC Inventory Tracker as a small common package.
