// Keep the shared badge in an empty host so React never reconciles its children.
export function PortfolioHeldBadge({ code, price }: { code: string; price?: number | null }) {
  return <span data-portfolio-code={code} data-portfolio-price={price ?? undefined} />;
}
