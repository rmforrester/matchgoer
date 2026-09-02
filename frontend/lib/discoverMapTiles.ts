type PublicMapTilerConfig = {
  key?: string;
  mapId?: string;
};

export type DiscoverTileLayerConfig = {
  url: string;
  attribution: string;
  crossOrigin?: boolean;
  minZoom?: number;
};

const OPENSTREETMAP_TILES: DiscoverTileLayerConfig = {
  url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
  attribution: "&copy; OpenStreetMap contributors",
};

export function discoverTileLayerConfig(config: PublicMapTilerConfig): DiscoverTileLayerConfig {
  const key = config.key?.trim();
  const mapId = config.mapId?.trim();

  if (!key || !mapId || !/^[a-zA-Z0-9_-]+$/.test(mapId)) {
    return OPENSTREETMAP_TILES;
  }

  return {
    url: `https://api.maptiler.com/maps/${mapId}/256/{z}/{x}/{y}.png?key=${encodeURIComponent(key)}`,
    attribution: '<a href="https://www.maptiler.com/copyright/" target="_blank">&copy; MapTiler</a> <a href="https://www.openstreetmap.org/copyright" target="_blank">&copy; OpenStreetMap contributors</a>',
    crossOrigin: true,
    minZoom: 1,
  };
}

export function configuredDiscoverTileLayer() {
  return discoverTileLayerConfig({
    key: process.env.NEXT_PUBLIC_MAPTILER_KEY,
    mapId: process.env.NEXT_PUBLIC_MAPTILER_MAP_ID,
  });
}
