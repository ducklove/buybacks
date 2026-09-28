import { render } from "@testing-library/react";
import { expect, it } from "vitest";
import { PortfolioHeldBadge } from "./PortfolioHeldBadge";

it("keeps shared badge children while React updates the quote or removes it", () => {
  const { container, rerender } = render(<PortfolioHeldBadge code="005930" price={75000} />);
  const host = container.firstElementChild!;
  const badge = document.createElement("span");
  badge.textContent = "보유";
  host.appendChild(badge);
  rerender(<PortfolioHeldBadge code="005930" price={76000} />);
  expect(host.getAttribute("data-portfolio-price")).toBe("76000");
  expect(host.firstElementChild).toBe(badge);
  rerender(<PortfolioHeldBadge code="000660" />);
  expect(host.getAttribute("data-portfolio-code")).toBe("000660");
  expect(host.hasAttribute("data-portfolio-price")).toBe(false);
});
