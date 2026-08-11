type League = {
  league_id: number;
  league_name: string;
};

type SearchBarProps = {
  leagues: League[];
  selectedLeague: string;
  setSelectedLeague: (league: string) => void;

  radius: number;
  setRadius: (radius: number) => void;

  startDate: string;
  setStartDate: (date: string) => void;

  endDate: string;
  setEndDate: (date: string) => void;

  onSearch: () => void;
  loading: boolean;
};

export default function SearchBar({
  leagues,
  selectedLeague,
  setSelectedLeague,
  radius,
  setRadius,
  startDate,
  setStartDate,
  endDate,
  setEndDate,
  onSearch,
  loading,
}: SearchBarProps) {
  return (
    <div
      style={{
        display: "flex",
        gap: "12px",
        marginBottom: "20px",
        alignItems: "center",
        flexWrap: "wrap",
      }}
    >
      <select
        value={selectedLeague}
        onChange={(e) => setSelectedLeague(e.target.value)}
      >
        <option value="">All Leagues</option>

        {leagues.map((league) => (
          <option
            key={league.league_id}
            value={league.league_name}
          >
            {league.league_name}
          </option>
        ))}
      </select>

      <select
        value={radius}
        onChange={(e) => setRadius(Number(e.target.value))}
      >
        <option value={10}>10 miles</option>
        <option value={25}>25 miles</option>
        <option value={50}>50 miles</option>
        <option value={100}>100 miles</option>
      </select>

      <input
        type="date"
        value={startDate}
        onChange={(e) => setStartDate(e.target.value)}
      />

      <input
        type="date"
        value={endDate}
        onChange={(e) => setEndDate(e.target.value)}
      />

      <button
        onClick={onSearch}
        disabled={loading}
        style={{
          padding: "8px 18px",
          cursor: loading ? "not-allowed" : "pointer",
          fontWeight: "bold",
          opacity: loading ? 0.6 : 1,
        }}
      >
        {loading ? "Searching..." : "🔍 Search Fixtures"}
      </button>
    </div>
  );
}