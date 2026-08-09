/*
 * Leadership deck (.pptx)
 * =======================
 * Ten slides. Dark cover and close, light content between them.
 * Motif: the numbered chip. It appears on every content slide and nowhere else.
 *
 *   node deck_pptx.js payload.json out.pptx
 */

const fs = require("fs");
const pptxgen = require("pptxgenjs");

const P = {
  green: "0FA958", deep: "046A38", ink: "1A1A1A", slate: "5C6B73",
  red: "D64545", amber: "E8A33D", mist: "F4F6F5", line: "DCE2E0",
  white: "FFFFFF", dark: "03301A",
};

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const OUT = process.argv[3];
const M = payload.meta, H = payload.headline;

const aed = (v) => {
  const a = Math.abs(v), s = v < 0 ? "-" : "";
  if (a >= 1e6) return `${s}AED ${(a / 1e6).toFixed(2)}m`;
  if (a >= 1e3) return `${s}AED ${Math.round(a / 1e3)}k`;
  return `${s}AED ${Math.round(a)}`;
};
const pct = (v, d = 0) => `${(v * 100).toFixed(d)}%`;

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";          // 13.3 x 7.5
pres.author = "Decision Brief Generator";
pres.title = "Supply Chain Decision Brief";

const W = 13.3, HGT = 7.5, MX = 0.7;

// the repeated motif: a numbered chip, never a stripe
function chip(slide, n, y = 0.42) {
  slide.addShape(pres.ShapeType.ellipse, {
    x: MX, y, w: 0.44, h: 0.44, fill: { color: P.green },
  });
  slide.addText(String(n), {
    x: MX, y, w: 0.44, h: 0.44, align: "center", valign: "middle",
    fontSize: 15, bold: true, color: P.white, fontFace: "Calibri", margin: 0,
  });
}

function title(slide, t, n, sub) {
  chip(slide, n);
  slide.addText(t, {
    x: MX + 0.62, y: 0.36, w: W - MX * 2 - 0.62, h: 0.62,
    fontSize: 27, bold: true, color: P.ink, fontFace: "Cambria", margin: 0,
    valign: "middle",
  });
  if (sub) {
    slide.addText(sub, {
      x: MX + 0.62, y: 1.00, w: W - MX * 2 - 0.62, h: 0.38,
      fontSize: 13.5, color: P.slate, fontFace: "Calibri", margin: 0,
    });
  }
}

function synthNote(slide) {
  if (!M.synthetic) return;
  slide.addText("Illustrative — synthetic data", {
    x: MX, y: HGT - 0.48, w: 4.2, h: 0.3, fontSize: 9.5,
    color: P.slate, fontFace: "Calibri", margin: 0,
  });
}

function chart(slide, key, o) {
  const p = payload.charts[key];
  if (!p || !fs.existsSync(p)) return;
  slide.addImage({ path: p, ...o });
}

const acts = payload.recommendations.filter((r) => r.stance === "act");
const rejected = payload.recommendations.filter((r) => r.stance === "reject");
const findings = payload.findings;
const narrative = payload.narrative || {};

// Render a value the way the analysis stored it: fractions below 1 are rates.
function evalue(e) {
  const v = e.value;
  if (typeof v === "number") {
    // A value between -1 and 1 is usually a rate — but not always. A
    // correlation coefficient rendered as "-45.0%" is simply wrong, and it
    // was, until this check existed.
    const notARate = /correlation|coefficient|ratio|index|multiplier/i
      .test(e.label || "");
    if (!notARate && Math.abs(v) > 0 && Math.abs(v) < 1) return pct(v, 1);
    return Number.isInteger(v) ? v.toLocaleString() : v.toFixed(2);
  }
  return String(v);
}
function evline(e) {
  return `${e.label}: ${evalue(e)}${e.unit ? " " + e.unit : ""}`;
}

// ====================================================== 1. cover
{
  const s = pres.addSlide();
  s.background = { color: P.dark };
  s.addText("Supply Chain\nDecision Brief", {
    x: MX, y: 1.9, w: 8.6, h: 2.0, fontSize: 46, bold: true,
    color: P.white, fontFace: "Cambria", lineSpacing: 50, margin: 0,
  });
  s.addText(M.subtitle, {
    x: MX, y: 4.05, w: 9.0, h: 0.42, fontSize: 18, color: P.green,
    fontFace: "Calibri", margin: 0,
  });
  s.addText(`${M.period_start} to ${M.period_end}  ·  ${M.days} days  ·  ${M.currency}`, {
    x: MX, y: 4.52, w: 9.0, h: 0.36, fontSize: 13, color: "9FB3A8",
    fontFace: "Calibri", margin: 0,
  });
  s.addText(`Prepared for the ${M.prepared_for}`, {
    x: MX, y: 6.25, w: 8.0, h: 0.34, fontSize: 12, color: "9FB3A8",
    fontFace: "Calibri", margin: 0,
  });
  if (M.synthetic) {
    s.addShape(pres.ShapeType.roundRect, {
      x: W - MX - 3.5, y: 6.15, w: 3.5, h: 0.55, rectRadius: 0.1,
      fill: { color: P.amber },
    });
    s.addText("ILLUSTRATIVE — SYNTHETIC DATA", {
      x: W - MX - 3.5, y: 6.15, w: 3.5, h: 0.55, align: "center", valign: "middle",
      fontSize: 10.5, bold: true, color: "2B1D00", fontFace: "Calibri", margin: 0,
    });
  }
  s.addNotes("Synthetic data throughout. The purpose is to demonstrate the " +
             "analytical method, not to report on a real business.");
}

// ====================================================== 2. the ask
{
  const s = pres.addSlide();
  title(s, "The decision", 1,
        "What is being asked, before any of the analysis");

  const stats = [
    [String(H.n_actions), "actions recommended", P.deep],
    [aed(H.net_benefit), "net annual value", P.green],
    [aed(H.investment), "one-off investment", P.ink],
    [aed(H.total_leak), "identified leakage", P.red],
  ];
  stats.forEach(([v, l, c], i) => {
    const x = MX + i * 3.03;
    s.addShape(pres.ShapeType.roundRect, {
      x, y: 1.68, w: 2.8, h: 1.95, rectRadius: 0.08,
      fill: { color: P.mist },
    });
    s.addText(v, { x: x + 0.22, y: 2.0, w: 2.36, h: 0.85, fontSize: 29,
      bold: true, color: c, fontFace: "Calibri", margin: 0 });
    s.addText(l, { x: x + 0.22, y: 2.92, w: 2.36, h: 0.42, fontSize: 12,
      color: P.slate, fontFace: "Calibri", margin: 0 });
  });

  const asks = [
    ["Approve now", "R1 and R5a. Both are scheduling changes — no headcount, no capital.", P.green],
    ["Mandate to negotiate", "R2 and R3. Both need supplier agreement before they can move.", P.deep],
    ["Note", "One recommendation is analysed and rejected. The obvious fix for the " +
             "worst-performing store costs more than it saves.", P.red],
  ];
  asks.forEach(([label, body, colour], i) => {
    const y = 4.15 + i * 0.95;
    s.addShape(pres.ShapeType.ellipse, {
      x: MX, y: y + 0.13, w: 0.2, h: 0.2, fill: { color: colour },
    });
    s.addText(label, { x: MX + 0.36, y, w: 3.0, h: 0.42, fontSize: 14,
      bold: true, color: colour, fontFace: "Calibri", margin: 0 });
    s.addText(body, { x: MX + 0.36, y: y + 0.4, w: 11.0, h: 0.5,
      fontSize: 13.5, color: P.ink, fontFace: "Calibri", margin: 0 });
  });

  synthNote(s);
  s.addNotes("Lead with the ask. The rest of the deck justifies it.");
}

// ====================================================== 3. scorecard
{
  const s = pres.addSlide();
  title(s, "Where the network stands", 2,
        "Every headline metric against its declared target");

  const sc = payload.scorecard;
  const cols = 4;
  sc.forEach((m, i) => {
    const col = i % cols, row = Math.floor(i / cols);
    const x = MX + col * 3.03, y = 1.75 + row * 1.95;
    const ok = m.status === "on_target";
    const f = (v) => m.fmt === "pct" ? pct(v, 1) : v.toFixed(1);
    s.addShape(pres.ShapeType.roundRect, {
      x, y, w: 2.8, h: 1.62, rectRadius: 0.08,
      fill: { color: ok ? "F2FBF6" : "FDF3F3" },
    });
    s.addText(m.kpi, { x: x + 0.18, y: y + 0.14, w: 2.44, h: 0.42,
      fontSize: 11, color: P.slate, fontFace: "Calibri", margin: 0 });
    s.addText(f(m.actual), { x: x + 0.18, y: y + 0.55, w: 2.44, h: 0.6,
      fontSize: 25, bold: true, color: ok ? P.green : P.red,
      fontFace: "Calibri", margin: 0 });
    s.addText(`target ${f(m.target)}`, { x: x + 0.18, y: y + 1.15, w: 2.44, h: 0.34,
      fontSize: 10.5, color: P.slate, fontFace: "Calibri", margin: 0 });
  });
  synthNote(s);
}

// ====================================================== 4. waterfall
{
  const s = pres.addSlide();
  title(s, "Where the margin goes", 3,
        `${aed(H.gross_margin)} of gross margin, and what the supply chain gives back`);
  chart(s, "margin_waterfall", { x: 0.85, y: 1.45, w: 11.6, h: 5.3 });
  synthNote(s);
}

// ====================================================== 5. findings
{
  const s = pres.addSlide();
  title(s, "What is going wrong", 4,
        "Ranked by materiality weighted by confidence. Root causes, not symptoms");

  findings.slice(0, 5).forEach((f, i) => {
    const y = 1.62 + i * 1.06;
    s.addShape(pres.ShapeType.ellipse, {
      x: MX, y: y + 0.14, w: 0.34, h: 0.34,
      fill: { color: f.direction === "leak" ? P.red : P.green },
    });
    s.addText(String(i + 1), { x: MX, y: y + 0.14, w: 0.34, h: 0.34,
      align: "center", valign: "middle", fontSize: 12, bold: true,
      color: P.white, fontFace: "Calibri", margin: 0 });
    s.addText(f.headline, {
      x: MX + 0.5, y, w: 9.1, h: 0.92, fontSize: 12.5, color: P.ink,
      fontFace: "Calibri", margin: 0, valign: "middle",
    });
    s.addText(`${aed(f.magnitude_aed)}/yr`, {
      x: 10.0, y, w: 1.7, h: 0.5, fontSize: 14, bold: true,
      color: P.deep, fontFace: "Calibri", margin: 0, align: "right",
      valign: "middle",
    });
    s.addText(`${pct(f.confidence)} conf.`, {
      x: 10.0, y: y + 0.44, w: 1.7, h: 0.36, fontSize: 10,
      color: P.slate, fontFace: "Calibri", margin: 0, align: "right",
    });
  });
  synthNote(s);
}

// ====================================================== 6. the trap
// Built from whichever finding carries the misdiagnosis tag, using that
// finding's own evidence. The framing comes from config; none of the prose
// is hardcoded, so this slide is correct for any domain that declares one.
if (narrative.trap) {
  const cfg = narrative.trap;
  const trap = findings.find((f) => (f.tags || []).includes(cfg.tag));
  if (trap) {
    const s = pres.addSlide();
    title(s, cfg.title, 5, cfg.subtitle);
    chart(s, cfg.chart, { x: 0.6, y: 1.55, w: 7.5, h: 4.9 });

    // Evidence whose comparator argues against the intuitive cause is the
    // ruling-out evidence; the rest describes the symptom.
    const ev = trap.evidence || [];
    const rulesOut = ev.filter((e) => e.role === "rules_out");
    const symptom = ev.filter((e) => e.role !== "rules_out").slice(0, 3);

    s.addShape(pres.ShapeType.roundRect, {
      x: 8.35, y: 1.75, w: 4.25, h: 4.3, rectRadius: 0.08,
      fill: { color: P.mist },
    });

    s.addText("The symptom", { x: 8.6, y: 1.95, w: 3.8, h: 0.3,
      fontSize: 11, bold: true, color: P.slate, fontFace: "Calibri", margin: 0 });
    s.addText(symptom.map((e, i) => ({
      text: evline(e), options: { breakLine: i < symptom.length - 1 } })), {
      x: 8.6, y: 2.28, w: 3.8, h: 1.0, fontSize: 11.5, color: P.ink,
      fontFace: "Calibri", margin: 0, lineSpacing: 15 });

    s.addText(`What rules ${cfg.intuitive_cause} out`,
      { x: 8.6, y: 3.35, w: 3.8, h: 0.3, fontSize: 11, bold: true,
        color: P.slate, fontFace: "Calibri", margin: 0 });
    s.addText(rulesOut.length
      ? rulesOut.map((e, i) => ({
          text: `${evline(e)} — ${e.comparator}`,
          options: { breakLine: i < rulesOut.length - 1 } }))
      : [{ text: "See the evidence panel in the brief.", options: {} }], {
      x: 8.6, y: 3.68, w: 3.8, h: 1.25, fontSize: 11.5, color: P.ink,
      fontFace: "Calibri", margin: 0, lineSpacing: 15 });

    s.addText("The cause", { x: 8.6, y: 4.98, w: 3.8, h: 0.3,
      fontSize: 11, bold: true, color: P.slate, fontFace: "Calibri", margin: 0 });
    s.addText(trap.headline, {
      x: 8.6, y: 5.3, w: 3.8, h: 0.68, fontSize: 11, bold: true, color: P.red,
      fontFace: "Calibri", margin: 0, lineSpacing: 14 });

    synthNote(s);
    s.addNotes(`A tool reasoning from symptoms to ${cfg.intuitive_cause} would ` +
               `get this wrong and spend a quarter fixing something that was ` +
               `never broken.`);
  }
}

// ====================================================== 7. cadence
{
  const s = pres.addSlide();
  title(s, "The largest single leak is a calendar", 6,
        "Orders are reviewed on the two quietest days of the week");
  chart(s, "fill_rate_by_dow", { x: 1.4, y: 1.6, w: 10.5, h: 4.6 });
  synthNote(s);
}

// ====================================================== 8. actions
{
  const s = pres.addSlide();
  title(s, "What to do", 7,
        `${acts.length} actions, ${aed(H.net_benefit)} a year net of the cost of acting`);

  const head = (t) => ({ text: t, options: { bold: true, color: P.slate, fontSize: 10 } });
  const rows = [[head("#"), head("Action"), head("Owner"), head("When"),
                 head("Effort"), head("Net/yr"), head("Payback")]];
  acts.forEach((r) => rows.push([
    { text: r.id, options: { bold: true, fontSize: 11 } },
    { text: r.title, options: { fontSize: 11 } },
    { text: r.owner, options: { fontSize: 10, color: P.slate } },
    { text: r.horizon.replace("_", " "), options: { fontSize: 10, color: P.slate } },
    { text: r.effort, options: { fontSize: 10, color: P.slate } },
    { text: aed(r.net_annual_aed), options: { fontSize: 11, bold: true, color: P.deep } },
    { text: r.payback_months ? `${r.payback_months.toFixed(1)} mo` : "immediate",
      options: { fontSize: 10 } },
  ]));

  s.addTable(rows, {
    x: MX, y: 1.68, w: W - MX * 2, colW: [0.5, 4.15, 2.3, 1.45, 1.0, 1.4, 1.1],
    border: { type: "solid", color: P.line, pt: 0.5 },
    fill: { color: P.white }, fontFace: "Calibri",
    rowH: 0.5, valign: "middle",
  });

  // summary band, so the slide closes rather than trailing off
  const bandY = 1.68 + 0.5 * (acts.length + 1) + 0.45;
  s.addShape(pres.ShapeType.roundRect, {
    x: MX, y: bandY, w: W - MX * 2, h: 1.15, rectRadius: 0.08,
    fill: { color: P.mist },
  });
  const totals = [
    [aed(acts.reduce((a, r) => a + r.benefit_aed, 0)), "gross benefit", P.ink],
    [aed(acts.reduce((a, r) => a + r.annual_cost_aed, 0)), "ongoing cost", P.ink],
    [aed(H.investment), "one-off investment", P.ink],
    [aed(H.net_benefit), "net annual value", P.green],
  ];
  totals.forEach(([v, l, c], i) => {
    const x = MX + 0.35 + i * 2.95;
    s.addText(v, { x, y: bandY + 0.18, w: 2.7, h: 0.48, fontSize: 18,
      bold: true, color: c, fontFace: "Calibri", margin: 0 });
    s.addText(l, { x, y: bandY + 0.66, w: 2.7, h: 0.34, fontSize: 10.5,
      color: P.slate, fontFace: "Calibri", margin: 0 });
  });

  synthNote(s);
}

// ====================================================== 9. rejected
if (rejected.length) {
  const s = pres.addSlide();
  const r = rejected[0];
  title(s, "And one thing not to do", 8,
        "The obvious fix does not pay, and saying so is part of the job");

  s.addShape(pres.ShapeType.roundRect, {
    x: MX, y: 1.75, w: 6.0, h: 3.9, rectRadius: 0.08, fill: { color: "FDF3F3" },
  });
  s.addText(r.title, { x: MX + 0.3, y: 2.0, w: 5.4, h: 0.8,
    fontSize: 17, bold: true, color: P.ink, fontFace: "Cambria", margin: 0 });

  [["Benefit", aed(r.benefit_aed), P.ink],
   ["Cost", aed(r.annual_cost_aed), P.red],
   ["Net", aed(r.net_annual_aed), P.red]].forEach(([l, v, c], i) => {
    s.addText(l, { x: MX + 0.3, y: 2.95 + i * 0.62, w: 2.0, h: 0.4,
      fontSize: 12.5, color: P.slate, fontFace: "Calibri", margin: 0 });
    s.addText(v, { x: MX + 2.4, y: 2.95 + i * 0.62, w: 3.2, h: 0.4,
      fontSize: 15, bold: i === 2, color: c, fontFace: "Calibri", margin: 0 });
  });

  // The alternative is whichever accepted action addresses the same finding.
  const alt = acts.find((a) =>
    a.finding_ids.some((fid) => r.finding_ids.includes(fid)));

  s.addText("Instead", { x: 7.3, y: 1.95, w: 5.2, h: 0.35,
    fontSize: 11, bold: true, color: P.slate, fontFace: "Calibri", margin: 0 });
  s.addText(alt ? alt.title : "See the recommended actions", {
    x: 7.3, y: 2.3, w: 5.2, h: 0.8, fontSize: 16, bold: true, color: P.green,
    fontFace: "Cambria", margin: 0 });
  s.addText(alt ? alt.rationale : r.rationale, {
    x: 7.3, y: 3.15, w: 5.2, h: 1.5, fontSize: 12, color: P.ink,
    fontFace: "Calibri", margin: 0 });
  if (alt) {
    s.addText(`${aed(alt.net_annual_aed)} a year, at ${alt.effort} effort`, {
      x: 7.3, y: 4.75, w: 5.2, h: 0.5, fontSize: 14, bold: true, color: P.deep,
      fontFace: "Calibri", margin: 0 });
  }

  synthNote(s);
  s.addNotes("Knowing that the obvious fix does not work is worth as much as " +
             "knowing which one does.");
}

// ====================================================== 10. close
{
  const s = pres.addSlide();
  s.background = { color: P.dark };
  s.addText("What we would measure", {
    x: MX, y: 0.7, w: 9.0, h: 0.7, fontSize: 30, bold: true,
    color: P.white, fontFace: "Cambria", margin: 0,
  });
  s.addText("Each action has a leading indicator that moves before the money does. " +
            "If it has not moved by the review point, stop the action rather than " +
            "extend it.", {
    x: MX, y: 1.45, w: 11.4, h: 0.6, fontSize: 13, color: "9FB3A8",
    fontFace: "Calibri", margin: 0,
  });

  acts.slice(0, 6).forEach((r, i) => {
    const y = 2.3 + i * 0.72;
    s.addText(r.id, { x: MX, y, w: 0.7, h: 0.5, fontSize: 13, bold: true,
      color: P.green, fontFace: "Calibri", margin: 0, valign: "middle" });
    s.addText(r.success_metric, { x: MX + 0.75, y, w: 9.4, h: 0.62,
      fontSize: 11.5, color: P.white, fontFace: "Calibri", margin: 0,
      valign: "middle" });
    s.addText(r.review_cadence, { x: 10.4, y, w: 2.2, h: 0.5, fontSize: 10.5,
      color: "9FB3A8", fontFace: "Calibri", margin: 0, align: "right",
      valign: "middle" });
  });

  if (M.synthetic) {
    s.addText("Illustrative — synthetic data. No Careem data was used.", {
      x: MX, y: HGT - 0.55, w: 8.0, h: 0.34, fontSize: 10,
      color: "9FB3A8", fontFace: "Calibri", margin: 0,
    });
  }
}

pres.writeFile({ fileName: OUT }).then(() => {
  const kb = (fs.statSync(OUT).size / 1024).toFixed(0);
  console.log(`  ${OUT}  (${kb} KB)`);
});
