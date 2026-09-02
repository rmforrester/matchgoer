import L from "leaflet";
import { USER_MARKER_DESIGN, VENUE_MARKER_DESIGN, venueMarkerPresentation } from "../../lib/mapMarkerDesign";

const markerSvg = (visited: boolean, selected: boolean, highlighted: boolean) => {
  const presentation = venueMarkerPresentation(visited, selected);
  const markerFill = highlighted ? "#D6A600" : "#2146D0";
  const markStroke = highlighted ? "#171717" : "#FCFAF5";
  return `
  <svg aria-hidden="true" width="${presentation.visibleWidth}" height="${presentation.visibleHeight}" viewBox="0 0 30 36" xmlns="http://www.w3.org/2000/svg">
    <path
      d="M3 2H27L29 5V24L15 35L1 24V5L3 2Z"
      fill="${markerFill}"
      stroke="#171717"
      stroke-width="2"
      stroke-linejoin="miter"
    />
    <path
      d="M6 21V10H9L15 17L21 10H24V21"
      fill="none"
      stroke="${markStroke}"
      stroke-width="2.5"
      stroke-linecap="square"
    />
    ${visited ? `
      <circle cx="25" cy="6" r="4.5" fill="#FCFAF5" stroke="#171717" stroke-width="1.25" />
      <path
        d="M22.7 6L24.3 7.5L27.3 4.5"
        fill="none"
        stroke="#2146D0"
        stroke-width="1.5"
        stroke-linecap="square"
        stroke-linejoin="miter"
      />
    ` : ""}
  </svg>
`;
};

export function createGroundMarkerIcon(visited = false, selected = false, highlighted = false): L.DivIcon {
  return L.divIcon({
    className: `tt-ground-marker${selected ? " tt-ground-marker--selected" : ""}`,
    html: `<span class="tt-ground-marker__visual">${markerSvg(visited, selected, highlighted)}</span>`,
    iconSize: [VENUE_MARKER_DESIGN.hitSize, VENUE_MARKER_DESIGN.hitSize],
    iconAnchor: [VENUE_MARKER_DESIGN.hitSize / 2, VENUE_MARKER_DESIGN.hitSize - 2],
    popupAnchor: [0, -32],
  });
}

export function createUserLocationIcon(): L.DivIcon {
  return L.divIcon({
    className: "tt-user-location-marker",
    html: '<span class="tt-user-location-marker__visual"><span class="sr-only">You are here</span></span>',
    iconSize: [USER_MARKER_DESIGN.hitSize, USER_MARKER_DESIGN.hitSize],
    iconAnchor: [USER_MARKER_DESIGN.hitSize / 2, USER_MARKER_DESIGN.hitSize / 2],
  });
}
