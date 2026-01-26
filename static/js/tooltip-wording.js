document.addEventListener("DOMContentLoaded", () => {
  const quantTooltips = Array.from(document.querySelectorAll("[data-tooltip]"));
  const quantInfoButtons = Array.from(document.querySelectorAll(".quant-info-btn"));

  function closeTooltips(exceptId) {
    quantTooltips.forEach(tip => {
      if (tip.id !== exceptId) {
        tip.classList.remove("is-open");
      }
    });
  }

  quantInfoButtons.forEach(btn => {
    btn.addEventListener("click", (event) => {
      event.stopPropagation();
      const targetId = btn.getAttribute("data-tooltip-target");
      if (!targetId) return;
      const tooltip = document.getElementById(targetId);
      if (!tooltip) return;
      const isOpen = tooltip.classList.contains("is-open");
      closeTooltips(targetId);
      tooltip.classList.toggle("is-open", !isOpen);
    });
  });

  quantTooltips.forEach(tip => {
    const closeBtn = tip.querySelector(".quant-close-btn");
    if (closeBtn) {
      closeBtn.addEventListener("click", (event) => {
        event.stopPropagation();
        tip.classList.remove("is-open");
      });
    }
  });

  document.addEventListener("click", () => {
    closeTooltips();
  });

  const quantVolEl = document.getElementById("quantVolatility");
  const quantDdEl = document.getElementById("quantMaxDrawdown");
  const quantBetaEl = document.getElementById("quantBeta");
  const quantTopSectorEl = document.getElementById("quantTopSector");
  const quantHHIEl = document.getElementById("quantHHI");
  const quantDiversificationEl = document.getElementById("quantDiversification");
  const quantVolTipBody = document.getElementById("quantVolatilityTipBody");
  const quantDdTipBody = document.getElementById("quantMaxDrawdownTipBody");
  const quantBetaTipBody = document.getElementById("quantBetaTipBody");
  const quantTopSectorTipBody = document.getElementById("quantTopSectorTipBody");
  const quantHHITipBody = document.getElementById("quantHHITipBody");
  const quantDiversificationTipBody = document.getElementById("quantDiversificationTipBody");
  const quantUpdatedEl = document.getElementById("quantLastUpdated");

  if (
    quantVolEl && quantDdEl && quantBetaEl && quantUpdatedEl &&
    quantTopSectorEl && quantHHIEl && quantDiversificationEl &&
    quantVolTipBody && quantDdTipBody && quantBetaTipBody &&
    quantTopSectorTipBody && quantHHITipBody && quantDiversificationTipBody
  ) {
    fetch("/quant/risk_summary")
      .then(response => response.json())
      .then(data => {
        if (data.error) {
          quantVolEl.innerText = "—";
          quantDdEl.innerText = "—";
          quantBetaEl.innerText = "—";
          quantTopSectorEl.innerText = "—";
          quantHHIEl.innerText = "—";
          quantDiversificationEl.innerText = "—";
          quantVolTipBody.innerText = "Annualized standard deviation of daily returns. Value: —";
          quantDdTipBody.innerText = "Worst peak-to-trough decline over the period. Value: —";
          quantBetaTipBody.innerText = "Sensitivity vs SPY (1.0 ≈ market). Value: —";
          quantTopSectorTipBody.innerText = "Largest sector weight after ETF decomposition. Value: —";
          quantHHITipBody.innerText = "Concentration score (higher = more concentrated). Value: —";
          quantDiversificationTipBody.innerText = "Portfolio volatility / weighted avg single-stock volatility. Value: —";
          quantUpdatedEl.innerText = "Last updated: —";
          quantUpdatedEl.className = "badge bg-secondary-subtle text-secondary-emphasis";
          console.error("Quant risk summary error:", data.error);
          return;
        }
        const volText = data.volatility_pct !== null ? `${data.volatility_pct}%` : "—";
        const ddText = data.max_drawdown_pct !== null ? `${data.max_drawdown_pct}%` : "—";
        const betaText = data.beta !== null ? data.beta : "—";
        quantVolEl.innerText = volText;
        quantDdEl.innerText = ddText;
        quantBetaEl.innerText = betaText;
        if (data.top_sector && data.top_sector_pct !== null) {
          quantTopSectorEl.innerText = `${data.top_sector} (${data.top_sector_pct}%)`;
        } else {
          quantTopSectorEl.innerText = "—";
        }
        const topSectorText = quantTopSectorEl.innerText;
        const hhiText = data.hhi !== null ? data.hhi : "—";
        const divText = data.diversification_ratio !== null ? data.diversification_ratio : "—";
        quantHHIEl.innerText = hhiText;
        quantDiversificationEl.innerText = divText;
        const volValue = data.volatility_pct;
        const ddValue = data.max_drawdown_pct;
        const betaValue = data.beta;
        const hhiValue = data.hhi;
        const divValue = data.diversification_ratio;
        const topSectorValue = data.top_sector_pct;

        const volInterp = Number.isFinite(volValue)
          ? (volValue < 15
            ? "This is relatively calm for equities; day-to-day swings are modest."
            : volValue < 30
              ? "This is moderate volatility; expect noticeable swings."
              : volValue < 50
                ? "This is high volatility; large swings are common."
                : "This is very high volatility; results may be dominated by big moves or short samples.")
          : "Not enough data to interpret volatility yet.";

        const ddInterp = Number.isFinite(ddValue)
          ? (ddValue > -5
            ? "The worst dip was mild; drawdowns have been shallow."
            : ddValue > -15
              ? "The worst dip was moderate; typical for equity portfolios."
              : ddValue > -30
                ? "The worst dip was sizable; risk is meaningfully elevated."
                : "The worst dip was severe; this indicates a rough drawdown period.")
          : "Not enough data to interpret drawdown yet.";

        const betaInterp = Number.isFinite(betaValue)
          ? (betaValue < 0.7
            ? "This is defensive relative to SPY; it moves less than the market."
            : betaValue < 1.2
              ? "This is market-like; it moves roughly in line with SPY."
              : betaValue < 1.8
                ? "This is aggressive; it tends to move more than SPY."
                : "This is very aggressive; market moves are amplified.")
          : "Not enough data to interpret beta yet.";

        const topSectorInterp = Number.isFinite(topSectorValue)
          ? (topSectorValue < 25
            ? "Your largest sector is below 25%, suggesting broad exposure."
            : topSectorValue < 40
              ? "Your largest sector is meaningful but not dominant."
              : topSectorValue < 60
                ? "Your largest sector is dominant and could drive results."
                : "Your largest sector heavily dominates the portfolio.")
          : "Not enough data to interpret sector concentration yet.";

        const hhiInterp = Number.isFinite(hhiValue)
          ? (hhiValue >= 0.9
            ? "HHI is near 1.0, which means you are effectively fully concentrated."
            : hhiValue >= 0.3
              ? "This indicates high concentration across sectors."
              : hhiValue >= 0.15
                ? "This indicates moderate concentration."
                : "This indicates broad diversification across sectors.")
          : "Not enough data to interpret HHI yet.";

        const divInterp = Number.isFinite(divValue)
          ? (divValue < 1.05
            ? "Diversification benefits are limited; holdings move together."
            : divValue < 1.2
              ? "Some diversification benefit is present."
              : divValue < 1.5
                ? "Strong diversification benefit is present."
                : "Very strong diversification benefit; holdings offset each other.")
          : "Not enough data to interpret diversification ratio yet.";

        quantVolTipBody.innerText = `Volatility is the annualized standard deviation of daily returns. It captures how widely your portfolio tends to swing over a year and is a common proxy for overall risk.\n\nValue: ${volText}. ${volInterp}`;
        quantDdTipBody.innerText = `Max drawdown is the worst peak-to-trough decline in portfolio value over the selected period. It answers how deep the worst loss was before recovery.\n\nValue: ${ddText}. ${ddInterp}`;
        quantBetaTipBody.innerText = `Beta measures how sensitive your portfolio is to market moves, using SPY as the benchmark. A beta of 1.0 means market-like movement, below 1.0 is defensive, and above 1.0 is more aggressive.\n\nValue: ${betaText}. ${betaInterp}`;
        quantTopSectorTipBody.innerText = `Top sector shows the largest sector exposure after decomposing ETFs and mutual funds into their underlying sector weights. It highlights where your portfolio is most concentrated by industry.\n\nValue: ${topSectorText}. ${topSectorInterp}`;
        quantHHITipBody.innerText = `HHI (Herfindahl-Hirschman Index) is a concentration score computed from sector weights. Higher values mean fewer sectors dominate; lower values indicate broader diversification.\n\nValue: ${hhiText}. ${hhiInterp}`;
        quantDiversificationTipBody.innerText = `Diversification ratio compares portfolio volatility to the weighted average volatility of its holdings. Higher values indicate stronger diversification benefits across positions.\n\nValue: ${divText}. ${divInterp}`;

        if (data.last_updated) {
          const isFresh = data.fresh === true;
          quantUpdatedEl.innerText = `Last updated: ${data.last_updated}`;
          if (isFresh) {
            quantUpdatedEl.className = "badge bg-info-subtle text-info-emphasis";
            quantUpdatedEl.innerText = `Last updated: ${data.last_updated} ✓`;
          } else {
            quantUpdatedEl.className = "badge bg-warning text-dark";
            quantUpdatedEl.innerText = `Last updated: ${data.last_updated} ✕`;
          }
        } else {
          quantUpdatedEl.innerText = "Last updated: —";
          quantUpdatedEl.className = "badge bg-secondary-subtle text-secondary-emphasis";
        }
      })
      .catch(error => {
        quantVolEl.innerText = "—";
        quantDdEl.innerText = "—";
        quantBetaEl.innerText = "—";
        quantTopSectorEl.innerText = "—";
        quantHHIEl.innerText = "—";
        quantDiversificationEl.innerText = "—";
        quantUpdatedEl.innerText = "Last updated: —";
        quantUpdatedEl.className = "badge bg-secondary-subtle text-secondary-emphasis";
        console.error("Quant risk fetch error:", error);
      });
  }
});
