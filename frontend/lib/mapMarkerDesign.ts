export const VENUE_MARKER_DESIGN = {
  hitSize: 44,
  visibleWidth: 24,
  visibleHeight: 29,
  selectedWidth: 28,
  selectedHeight: 34,
} as const;

export const USER_MARKER_DESIGN = {
  hitSize: 44,
  visibleSize: 16,
} as const;

export function venueMarkerPresentation(visited: boolean, selected: boolean) {
  return {
    visited,
    selected,
    visibleWidth: selected ? VENUE_MARKER_DESIGN.selectedWidth : VENUE_MARKER_DESIGN.visibleWidth,
    visibleHeight: selected ? VENUE_MARKER_DESIGN.selectedHeight : VENUE_MARKER_DESIGN.visibleHeight,
    hitSize: VENUE_MARKER_DESIGN.hitSize,
  };
}
