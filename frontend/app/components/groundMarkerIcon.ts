import L from "leaflet";
import { USER_MARKER_DESIGN, VENUE_MARKER_DESIGN, venueMarkerPresentation } from "../../lib/mapMarkerDesign";
import type { MarkerSignal } from "../../lib/markerSignal";

const markerSignalSvg = (signal: MarkerSignal, stroke: string) => {
  if (signal === "international") return `<g fill="none" stroke="${stroke}" stroke-linecap="round"><circle cx="15" cy="16" r="7" stroke-width="2"/><path d="M8 16H22M15 9C17.1 11 18 13.3 18 16C18 18.7 17.1 21 15 23M15 9C12.9 11 12 13.3 12 16C12 18.7 12.9 21 15 23" stroke-width="1.4"/></g>`;
  if (signal === "cup") return `<path d="M10 9H20V13C20 17 18.1 19.5 15 19.5C11.9 19.5 10 17 10 13V9ZM10 11H7V13C7 15.4 8.4 16.8 10.7 17M20 11H23V13C23 15.4 21.6 16.8 19.3 17M15 19.5V23M11 24H19" fill="none" stroke="${stroke}" stroke-width="1.8" stroke-linecap="square" stroke-linejoin="miter"/>`;
  if (signal === "rivalry") return `<path d="M15 7C18 11 20 13.2 20 17C20 21 17.8 24 15 24C11.3 24 9 21.3 9 18C9 15.2 10.5 13.2 12.5 11.2C12.6 14.1 13.5 15.2 15 16.5C16.4 14.2 16.8 11.5 15 7Z" fill="none" stroke="${stroke}" stroke-width="2" stroke-linejoin="round"/>`;
  if (signal === "scenic") return `<g fill="none" stroke="${stroke}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="21" cy="10" r="2.5"/><path d="M7 23L12 15L15 19L18 14L23 23M7 23H23"/></g>`;
  if (signal === "classic") return `<g fill="none" stroke="${stroke}" stroke-width="1.8" stroke-linejoin="miter"><path d="M7 14L15 9L23 14V23H7V14Z"/><path d="M10 15V12M20 15V12M11 23V18H19V23M7 15H23"/></g>`;
  return `<g fill="none" stroke="${stroke}" stroke-width="1.5" stroke-linejoin="round"><circle cx="15" cy="16" r="7"/><path d="M15 12L18.4 14.5L17.1 18.5H12.9L11.6 14.5L15 12ZM15 9V12M21.7 13.8L18.4 14.5M19.2 21.7L17.1 18.5M10.8 21.7L12.9 18.5M8.3 13.8L11.6 14.5"/></g>`;
};

const markerSvg = (visited: boolean, selected: boolean, highlighted: boolean, signal: MarkerSignal) => {
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
    ${markerSignalSvg(signal, markStroke)}
  </svg>
`;
};

export function createGroundMarkerIcon(visited = false, selected = false, highlighted = false, signal: MarkerSignal = "standard"): L.DivIcon {
  return L.divIcon({
    className: `tt-ground-marker${selected ? " tt-ground-marker--selected" : ""}`,
    html: `<span class="tt-ground-marker__visual">${markerSvg(visited, selected, highlighted, signal)}</span>`,
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
