export type OfficialChannels = {
  official_homepage_url?: string | null;
  official_instagram_url?: string | null;
};

export function officialChannelLinks(channels?: OfficialChannels | null): { label: string; url: string }[] {
  const links: { label: string; url: string }[] = [];
  if (channels?.official_homepage_url) links.push({ label: "Club website", url: channels.official_homepage_url });
  if (channels?.official_instagram_url) links.push({ label: "Instagram", url: channels.official_instagram_url });
  return links;
}
