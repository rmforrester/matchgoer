import L from "leaflet";

const markerSvg = (visited: boolean) => `
  <svg aria-hidden="true" width="30" height="36" viewBox="0 0 30 36" xmlns="http://www.w3.org/2000/svg">
    <path
      d="M3 2H27L29 5V24L15 35L1 24V5L3 2Z"
      fill="#2146D0"
      stroke="#171717"
      stroke-width="2"
      stroke-linejoin="miter"
    />
    <path
      d="M6 21V10L15 18L24 10V21"
      fill="none"
      stroke="#FCFAF5"
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

export function createGroundMarkerIcon(visited = false): L.DivIcon {
  return L.divIcon({
    className: "tt-ground-marker",
    html: `<span class="tt-ground-marker__visual">${markerSvg(visited)}</span>`,
    iconSize: [44, 44],
    iconAnchor: [22, 40],
    popupAnchor: [0, -38],
  });
}

const attendedGroundMarkerSvg = `
  <svg aria-hidden="true" width="30" height="36" viewBox="0 0 30 36" xmlns="http://www.w3.org/2000/svg">
    <path d="M3 2H27L29 5V24L15 35L1 24V5L3 2Z" fill="#171717" stroke="#171717" stroke-width="2" stroke-linejoin="miter" />
    <circle cx="15" cy="15" r="8" fill="#FCFAF5" />
    <path d="M10.5 15L13.7 18L20 11.5" fill="none" stroke="#2146D0" stroke-width="2.5" stroke-linecap="square" stroke-linejoin="miter" />
  </svg>
`;

export function createAttendedGroundMarkerIcon(): L.DivIcon {
  return L.divIcon({
    className: "tt-attended-ground-marker",
    html: `<span class="tt-attended-ground-marker__visual">${attendedGroundMarkerSvg}</span>`,
    iconSize: [44, 44],
    iconAnchor: [22, 40],
    popupAnchor: [0, -38],
  });
}
