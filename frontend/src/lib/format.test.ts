import { describe, expect, it } from "vitest";
import { formatCompact, formatMoney, formatPercent, formatTimestamp } from "./format";

describe("market display formatters", () => {
  it("keeps missing observations visibly unavailable", () => {
    expect(formatMoney(null)).toBe("--");
    expect(formatPercent(undefined)).toBe("--");
    expect(formatTimestamp(null)).toBe("No provider timestamp");
  });

  it("formats prices, percentages, and compact volume", () => {
    expect(formatMoney(12.5)).toBe("$12.50");
    expect(formatPercent(-1.25)).toBe("-1.25%");
    expect(formatCompact(1_200_000)).toBe("1.2M");
  });
});