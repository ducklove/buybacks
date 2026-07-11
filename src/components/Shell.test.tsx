import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Shell } from "./Shell";

describe("Shell", () => {
  it("renders the Value Compass hub link and the GitHub repository link", () => {
    render(<Shell>본문</Shell>);

    const hubLink = screen.getByRole("link", { name: "Value Compass ↗" });
    expect(hubLink).toHaveAttribute("href", "https://cantabile.tplinkdns.com:3691");

    const githubLink = screen.getByRole("link", { name: "GitHub" });
    expect(githubLink).toHaveAttribute("href", "https://github.com/ducklove/buybacks");
  });
});
