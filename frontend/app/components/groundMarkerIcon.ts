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
      d="M5 10H12M8.5 10V21M15 10H22M18.5 10V21"
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
