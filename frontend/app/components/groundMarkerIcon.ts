import L from "leaflet";
import { USER_MARKER_DESIGN, VENUE_MARKER_DESIGN, venueMarkerPresentation } from "../../lib/mapMarkerDesign";
import type { FixtureType } from "../../lib/fixtureType";

const semanticBadge = (fixtureType: FixtureType) => {
  if (fixtureType === "standard") return "";
  const symbol = fixtureType === "cup"
    ? `<path d="M3.5 2.5H8.5V4.2C8.5 6.1 7.5 7.2 6 7.2C4.5 7.2 3.5 6.1 3.5 4.2V2.5ZM3.5 3.2H2.2V4C2.2 5 2.8 5.6 3.8 5.7M8.5 3.2H9.8V4C9.8 5 9.2 5.6 8.2 5.7M6 7.2V9M3.8 9H8.2" fill="none" stroke="#171717" stroke-width="1" stroke-linecap="square" stroke-linejoin="miter" />`
    : `<circle cx="6" cy="6" r="3.6" fill="none" stroke="#171717" stroke-width="1"/><path d="M2.7 6H9.3M6 2.4C7 3.4 7.4 4.6 7.4 6C7.4 7.4 7 8.6 6 9.6M6 2.4C5 3.4 4.6 4.6 4.6 6C4.6 7.4 5 8.6 6 9.6" fill="none" stroke="#171717" stroke-width="0.8"/>`;
  return `<g transform="translate(1 1)"><circle cx="6" cy="6" r="5.3" fill="#FCFAF5" stroke="#171717" stroke-width="1"/>${symbol}</g>`;
};

const markerSvg = (visited: boolean, selected: boolean, highlighted: boolean, fixtureType: FixtureType) => {
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
    ${semanticBadge(fixtureType)}
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

export function createGroundMarkerIcon(visited = false, selected = false, highlighted = false, fixtureType: FixtureType = "standard"): L.DivIcon {
  return L.divIcon({
    className: `tt-ground-marker${selected ? " tt-ground-marker--selected" : ""}`,
    html: `<span class="tt-ground-marker__visual">${markerSvg(visited, selected, highlighted, fixtureType)}</span>`,
    iconSize: [VENUE_MARKER_DESIGN.hitSize, VENUE_MARKER_DESIGN.hitSize],
    iconAnchor: [VENUE_MARKER_DESIGN.hitSize / 2, VENUE_MARKER_DESIGN.hitSize - 2],
    popupAnchor: [0, -32],
  });
}

const attendedGroundMarkerSvg = `
  <svg aria-hidden="true" width="14" height="14" viewBox="0 0 14 14" xmlns="http://www.w3.org/2000/svg">
    <circle cx="7" cy="7" r="6" fill="#2146D0" stroke="#171717" stroke-width="1.5" />
  </svg>
`;

export function createAttendedGroundMarkerIcon(): L.DivIcon {
  return L.divIcon({
    className: "tt-attended-ground-marker",
    html: `<span class="tt-attended-ground-marker__visual">${attendedGroundMarkerSvg}</span>`,
    iconSize: [VENUE_MARKER_DESIGN.hitSize, VENUE_MARKER_DESIGN.hitSize],
    iconAnchor: [VENUE_MARKER_DESIGN.hitSize / 2, VENUE_MARKER_DESIGN.hitSize / 2],
    popupAnchor: [0, -12],
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
