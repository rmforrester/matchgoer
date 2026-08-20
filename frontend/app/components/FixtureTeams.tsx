type Props = {
  homeTeam: string;
  awayTeam: string;
  className?: string;
  teamClassName?: string;
  separatorClassName?: string;
};

export default function FixtureTeams({
  homeTeam,
  awayTeam,
  className = "",
  teamClassName = "",
  separatorClassName = "",
}: Props) {
  return (
    <div className={`min-w-0 ${className}`} aria-label={`${homeTeam} versus ${awayTeam}`}>
      <p className={`tt-display break-words ${teamClassName}`}>{homeTeam}</p>
      <p className={`font-extrabold uppercase text-[var(--tt-blue)] ${separatorClassName}`} aria-hidden="true">VS</p>
      <p className={`tt-display break-words ${teamClassName}`}>{awayTeam}</p>
    </div>
  );
}
