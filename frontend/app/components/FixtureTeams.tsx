import TeamBadge from "./TeamBadge";

type Props = {
  homeTeam: string;
  awayTeam: string;
  className?: string;
  teamClassName?: string;
  separatorClassName?: string;
  homeBadgeSrc?: string | null;
  awayBadgeSrc?: string | null;
  badgeClassName?: string;
  compact?: boolean;
};

export default function FixtureTeams({
  homeTeam,
  awayTeam,
  className = "",
  teamClassName = "",
  separatorClassName = "",
  homeBadgeSrc,
  awayBadgeSrc,
  badgeClassName = "h-12 w-12 sm:h-16 sm:w-16",
  compact = false,
}: Props) {
  if (compact) return (
    <div className={`grid min-w-0 justify-items-center gap-1 text-center ${className}`} aria-label={`${homeTeam} versus ${awayTeam}`}>
      <div className="grid min-w-0 justify-items-center gap-1">
        <TeamBadge src={homeBadgeSrc} className={badgeClassName} />
        <p className={`tt-display min-w-0 break-words ${teamClassName}`}>{homeTeam}</p>
      </div>
      <span className={`justify-self-center font-extrabold text-[var(--brand-interactive)] ${separatorClassName}`} aria-hidden="true">VS</span>
      <div className="grid min-w-0 justify-items-center gap-1">
        <TeamBadge src={awayBadgeSrc} className={badgeClassName} />
        <p className={`tt-display min-w-0 break-words ${teamClassName}`}>{awayTeam}</p>
      </div>
    </div>
  );

  return (
    <div className={`min-w-0 ${className}`} aria-label={`${homeTeam} versus ${awayTeam}`}>
      <div className="flex min-w-0 items-center gap-3 sm:gap-4">
        <TeamBadge src={homeBadgeSrc} className={badgeClassName} />
        <p className={`tt-display min-w-0 break-words ${teamClassName}`}>{homeTeam}</p>
      </div>
      <p className={`font-extrabold uppercase text-[var(--brand-interactive)] ${separatorClassName}`} aria-hidden="true">VS</p>
      <div className="flex min-w-0 items-center gap-3 sm:gap-4">
        <TeamBadge src={awayBadgeSrc} className={badgeClassName} />
        <p className={`tt-display min-w-0 break-words ${teamClassName}`}>{awayTeam}</p>
      </div>
    </div>
  );
}
