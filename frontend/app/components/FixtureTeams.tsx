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
    <div className={`grid min-w-0 grid-cols-[3rem_minmax(0,1fr)_3rem] items-center gap-2 text-center ${className}`} aria-label={`${homeTeam} versus ${awayTeam}`}>
      <span className="flex h-12 w-12 items-center justify-center" aria-hidden="true">
        <TeamBadge src={homeBadgeSrc} className={badgeClassName} />
      </span>
      <div className="grid min-w-0 grid-rows-[1fr_auto_1fr] gap-1">
        <p className={`tt-display flex min-w-0 items-center justify-center break-words ${teamClassName}`}>{homeTeam}</p>
        <span className={`flex min-w-0 items-center gap-2 font-extrabold text-[var(--brand-interactive)] ${separatorClassName}`} aria-hidden="true">
          <span className="h-px min-w-0 flex-1 bg-[var(--tt-rule)]" />
          <span>VS</span>
          <span className="h-px min-w-0 flex-1 bg-[var(--tt-rule)]" />
        </span>
        <p className={`tt-display flex min-w-0 items-center justify-center break-words ${teamClassName}`}>{awayTeam}</p>
      </div>
      <span className="flex h-12 w-12 items-center justify-center" aria-hidden="true">
        <TeamBadge src={awayBadgeSrc} className={badgeClassName} />
      </span>
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
