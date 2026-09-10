# BTM navigation publication rule

A BTM can publish without Directions. A non-empty `maps_destination` is allowed only when the frozen publication manifest records affirmative evidence that it uniquely identifies the approved physical destination.

Publication tooling must call `validate_btm_navigation(maps_destination=..., unique_target_supported=...)` for every candidate row. Common names, unlocated internal areas and descriptive location context do not establish uniqueness. When support is absent, retain the approved BTM and truthful `location_context`, set `maps_destination` to null, and continue publication.

For a contained destination, the containing venue may be used only when evidence confirms the containment and the venue is the approved navigation target. This rule applies to all future country workflows, including Italy.
