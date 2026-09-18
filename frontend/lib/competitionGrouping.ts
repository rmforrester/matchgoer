export type Competition = { league_id: number; league_name: string };
export type CompetitionGroup = { country: string; leagues: Competition[] };

function normalized(value: string): string {
  return value.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase().trim();
}

export function supporterCompetitionGroup(storedCountry: string, competitionName: string): string {
  if (storedCountry.toLocaleLowerCase() !== "world") return storedCountry;
  const name = normalized(competitionName);

  if (name.includes("world cup") && name.includes("qualification")) {
    if (name.includes("europe") || name.includes("uefa")) return "Europe";
    if (name.includes("concacaf") || name.includes("north america")) return "North/Central America & Caribbean";
    if (name.includes("conmebol") || name.includes("south america")) return "South America";
    if (name.includes("africa") || /(^|\s)caf(\s|$)/.test(name)) return "Africa";
    if (name.includes("asia") || /(^|\s)afc(\s|$)/.test(name)) return "Asia";
    if (name.includes("oceania") || /(^|\s)ofc(\s|$)/.test(name)) return "Oceania";
  }
  if (name.includes("finalissima") || name.includes("intercontinental") || name.includes("club world cup") || name.includes("fifa world cup") || name === "world cup" || name.startsWith("world cup ")) return "World";
  if (name.includes("uefa") || name.includes("european championship") || name.includes("euro qualification")) return "Europe";
  if (name.includes("concacaf") || name.includes("gold cup")) return "North/Central America & Caribbean";
  if (name.includes("conmebol") || name.includes("libertadores") || name.includes("sudamericana") || name.includes("copa america")) return "South America";
  if (/(^|\s)caf(\s|$)/.test(name) || name.includes("africa cup of nations")) return "Africa";
  if (/(^|\s)afc(\s|$)/.test(name) || name.includes("asian cup")) return "Asia";
  if (/(^|\s)ofc(\s|$)/.test(name)) return "Oceania";

  return storedCountry;
}

export function supporterCompetitionGroups(groups: CompetitionGroup[]): CompetitionGroup[] {
  const grouped = new Map<string, Map<number, Competition>>();
  for (const group of groups) {
    for (const competition of group.leagues) {
      const label = supporterCompetitionGroup(group.country, competition.league_name);
      const competitions = grouped.get(label) ?? new Map<number, Competition>();
      competitions.set(competition.league_id, competition);
      grouped.set(label, competitions);
    }
  }
  return [...grouped.entries()]
    .map(([country, competitions]) => ({ country, leagues: [...competitions.values()].sort((a, b) => a.league_name.localeCompare(b.league_name)) }))
    .sort((a, b) => a.country.localeCompare(b.country));
}

export function matchingCompetitionGroups(groups: CompetitionGroup[], query: string): CompetitionGroup[] {
  const search = normalized(query);
  if (!search) return [];
  return groups
    .map((group) => normalized(group.country).includes(search)
      ? group
      : { ...group, leagues: group.leagues.filter((competition) => normalized(competition.league_name).includes(search)) })
    .filter((group) => group.leagues.length > 0);
}
