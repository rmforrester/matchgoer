type PublicMapboxConfig = {
  token?: string;
  username?: string;
  styleId?: string;
};

export type DiscoverTileLayerConfig = {
  url: string;
  attribution: string;
  crossOrigin?: boolean;
  minZoom?: number;
  tileSize?: number;
  zoomOffset?: number;
};

const OPENSTREETMAP_TILES: DiscoverTileLayerConfig = {
  url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
  attribution: "&copy; OpenStreetMap contributors",
};

export function discoverTileLayerConfig(config: PublicMapboxConfig): DiscoverTileLayerConfig {
  const token = config.token?.trim();
  const username = config.username?.trim();
  const styleId = config.styleId?.trim();

  if (!token || !username || !styleId || !/^[a-zA-Z0-9_-]+$/.test(username) || !/^[a-zA-Z0-9_-]+$/.test(styleId)) {
    return OPENSTREETMAP_TILES;
  }

  return {
    url: `https://api.mapbox.com/styles/v1/${username}/${styleId}/tiles/512/{z}/{x}/{y}?access_token=${encodeURIComponent(token)}`,
    attribution: '<a href="https://www.mapbox.com/about/maps/" target="_blank">&copy; Mapbox</a> <a href="https://www.openstreetmap.org/copyright" target="_blank">&copy; OpenStreetMap contributors</a>',
    crossOrigin: true,
    tileSize: 512,
    zoomOffset: -1,
  };
}

export function configuredDiscoverTileLayer() {
  return discoverTileLayerConfig({
    token: process.env.NEXT_PUBLIC_MAPBOX_TOKEN,
    username: process.env.NEXT_PUBLIC_MAPBOX_USERNAME,
    styleId: process.env.NEXT_PUBLIC_MAPBOX_STYLE_ID,
  });
}
