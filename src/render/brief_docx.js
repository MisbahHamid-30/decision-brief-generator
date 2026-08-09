/*
 * Executive brief (.docx)
 * =======================
 * Decision first. Section 2 tells the reader what is being asked of them
 * before any analysis appears; everything after that exists to justify it.
 *
 * The appendix carries the limitations section — what the data cannot
 * support. That is the part most submissions omit, and the part a careful
 * reader looks for.
 *
 *   node brief_docx.js payload.json out.docx
 */

const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle,
  ImageRun, PageBreak, Header, Footer, PageNumber, LevelFormat, convertInchesToTwip,
} = require("docx");

const P = {
  green: "0FA958", deep: "046A38", ink: "1A1A1A", slate: "5C6B73",
  red: "D64545", amber: "E8A33D", mist: "F4F6F5", line: "DCE2E0", white: "FFFFFF",
};

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const OUT = process.argv[3];
const M = payload.meta, H = payload.headline;

// ---------------------------------------------------------------- helpers

const aed = (v) => {
  const a = Math.abs(v), s = v < 0 ? "-" : "";
  if (a >= 1e6) return `${s}AED ${(a / 1e6).toFixed(2)}m`;
  if (a >= 1e3) return `${s}AED ${Math.round(a / 1e3)}k`;
  return `${s}AED ${Math.round(a)}`;
};
const pct = (v, d = 1) => `${(v * 100).toFixed(d)}%`;

const PAGE_W = convertInchesToTwip(6.5); // Letter minus 1" margins

function text(t, o = {}) {
  return new TextRun({
    text: t, font: o.font || "Calibri", size: o.size || 21,
    bold: o.bold, italics: o.italics, color: o.color || P.ink,
  });
}

function para(t, o = {}) {
  return new Paragraph({
    children: Array.isArray(t) ? t : (typeof t === "string" ? [text(t, o)] : [t]),
    spacing: { after: o.after === undefined ? 120 : o.after, before: o.before || 0,
               line: o.line || 276 },
    alignment: o.align,
    heading: o.heading,
    indent: o.indent,
    border: o.border,
  });
}

function h1(t) {
  return new Paragraph({
    children: [text(t, { size: 30, bold: true, color: P.deep, font: "Cambria" })],
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 340, after: 150 },
  });
}
function h2(t) {
  return new Paragraph({
    children: [text(t, { size: 24, bold: true, color: P.ink, font: "Cambria" })],
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 240, after: 110 },
  });
}

// Accepts a string, a TextRun, or an array of runs. Wrapping an already-built
// TextRun in text() silently produces an empty bullet — the run is passed as
// the `text` option, stringifies to nothing, and the document renders a bullet
// with no content. Normalising here rather than at every call site.
function runs(t) {
  if (Array.isArray(t)) return t;
  if (typeof t === "string") return [text(t)];
  return [t];
}

function bullet(t, level = 0) {
  return new Paragraph({
    children: runs(t),
    numbering: { reference: "dots", level },
    spacing: { after: 70, line: 276 },
  });
}

function cell(children, o = {}) {
  return new TableCell({
    children: Array.isArray(children) ? children : [children],
    width: { size: o.w, type: WidthType.DXA },
    shading: o.fill ? { type: ShadingType.CLEAR, fill: o.fill, color: "auto" } : undefined,
    margins: { top: 90, bottom: 90, left: 110, right: 110 },
    columnSpan: o.span,
  });
}

function table(widths, rows) {
  return new Table({
    columnWidths: widths,
    width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA },
    borders: {
      top: { style: BorderStyle.SINGLE, size: 1, color: P.line },
      bottom: { style: BorderStyle.SINGLE, size: 1, color: P.line },
      left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE },
      insideHorizontal: { style: BorderStyle.SINGLE, size: 1, color: P.line },
      insideVertical: { style: BorderStyle.NONE },
    },
    rows,
  });
}

function img(key, widthIn) {
  const p = payload.charts[key];
  if (!p || !fs.existsSync(p)) return para("");
  const w = widthIn * 96, h = w * 0.52;
  return new Paragraph({
    children: [new ImageRun({
      type: "png", data: fs.readFileSync(p),
      transformation: { width: Math.round(w), height: Math.round(h) },
    })],
    spacing: { before: 120, after: 140 },
    alignment: AlignmentType.CENTER,
  });
}

function caption(t) {
  return para(t, { size: 17, color: P.slate, italics: true, after: 200 });
}

// ---------------------------------------------------------------- content

const acts = payload.recommendations.filter((r) => r.stance === "act");
const rejected = payload.recommendations.filter((r) => r.stance !== "act");
const findings = payload.findings;

const doc_children = [];

// ---- cover -------------------------------------------------------------
doc_children.push(
  para("", { after: 900 }),
  para([text("Supply Chain Decision Brief",
             { size: 52, bold: true, color: P.deep, font: "Cambria" })],
       { after: 100 }),
  para([text(M.subtitle, { size: 26, color: P.slate })], { after: 60 }),
  para([text(`${M.period_start} to ${M.period_end}  ·  ${M.days} days  ·  ${M.currency}`,
             { size: 20, color: P.slate })], { after: 500 }),
);

if (M.synthetic) {
  doc_children.push(new Table({
    columnWidths: [PAGE_W],
    width: { size: PAGE_W, type: WidthType.DXA },
    borders: {
      top: { style: BorderStyle.SINGLE, size: 6, color: P.amber },
      bottom: { style: BorderStyle.SINGLE, size: 6, color: P.amber },
      left: { style: BorderStyle.SINGLE, size: 6, color: P.amber },
      right: { style: BorderStyle.SINGLE, size: 6, color: P.amber },
      insideHorizontal: { style: BorderStyle.NONE },
      insideVertical: { style: BorderStyle.NONE },
    },
    rows: [new TableRow({ children: [cell([
      para([text("ILLUSTRATIVE — SYNTHETIC DATA", { bold: true, size: 20 })],
           { after: 60 }),
      para("This brief demonstrates an analytical method. The underlying data is " +
           "generated, not observed. No Careem data of any kind has been used and no " +
           "figure in this document describes a real business.",
           { size: 19, color: P.slate, after: 0 }),
    ], { w: PAGE_W, fill: "FEF7E8" })] })],
  }));
}

doc_children.push(
  para("", { after: 600 }),
  para([text(`Prepared for the ${M.prepared_for}`, { size: 20, color: P.slate })],
       { after: 40 }),
  para([text(`Data-quality gate: ${M.quality_gate}`, { size: 20, color: P.slate })],
       { after: 0 }),
  new Paragraph({ children: [new PageBreak()] }),
);

// ---- 1. the decision ---------------------------------------------------
doc_children.push(h1("The decision"));

doc_children.push(para([
  text("The network converts ", {}),
  text(aed(H.gross_margin), { bold: true }),
  text(" of gross margin a year and gives back ", {}),
  text(aed(H.total_leak), { bold: true, color: P.red }),
  text(" of it through availability failures, write-off and supplier " +
       "shortfalls. This brief identifies where that goes and what recovers it.", {}),
]));

doc_children.push(para([
  text("Six actions are recommended. Together they are worth ", {}),
  text(`${aed(H.net_benefit)} a year`, { bold: true, color: P.deep }),
  text(" net of the cost of doing them, against ", {}),
  text(aed(H.investment), { bold: true }),
  text(" of one-off investment. A seventh — the intuitive fix for the " +
       "network's worst-performing store — is analysed and ", {}),
  text("not recommended", { bold: true }),
  text(", because it costs more than it saves.", {}),
]));

doc_children.push(para([
  text("What is being asked: ", { bold: true }),
  text("approval to proceed with R1 and R5a immediately — both are scheduling " +
       "changes with no incremental headcount — and a mandate to open supplier " +
       "negotiations behind R2 and R3.", {}),
]));

// headline numbers
const Q = PAGE_W / 4;
doc_children.push(table([Q, Q, Q, Q], [
  new TableRow({ children: [
    cell(para("Actions recommended", { size: 17, color: P.slate, bold: true, after: 40 }), { w: Q, fill: P.mist }),
    cell(para("Net annual value", { size: 17, color: P.slate, bold: true, after: 40 }), { w: Q, fill: P.mist }),
    cell(para("One-off investment", { size: 17, color: P.slate, bold: true, after: 40 }), { w: Q, fill: P.mist }),
    cell(para("Identified leakage", { size: 17, color: P.slate, bold: true, after: 40 }), { w: Q, fill: P.mist }),
  ] }),
  new TableRow({ children: [
    cell(para(String(H.n_actions), { size: 32, bold: true, color: P.deep, after: 0 }), { w: Q }),
    cell(para(aed(H.net_benefit), { size: 32, bold: true, color: P.deep, after: 0 }), { w: Q }),
    cell(para(aed(H.investment), { size: 32, bold: true, color: P.ink, after: 0 }), { w: Q }),
    cell(para(aed(H.total_leak), { size: 32, bold: true, color: P.red, after: 0 }), { w: Q }),
  ] }),
]));

// ---- 2. executive summary ---------------------------------------------
doc_children.push(h1("Executive summary"));
doc_children.push(para(
  "Findings are ordered by materiality weighted by confidence. Root causes are " +
  "reported rather than the symptoms they produce, so the same money is not " +
  "counted twice."));

findings.slice(0, 6).forEach((f) => {
  const root = f.caused_by.length ? `symptom of ${f.caused_by.join(", ")}` : "root cause";
  doc_children.push(bullet([
    text(`${f.headline}. `, { bold: false }),
    text(`${aed(f.magnitude_aed)}/yr`, { bold: true, color: P.deep }),
    text(`  ·  ${pct(f.confidence, 0)} confidence  ·  ${root}`,
         { size: 18, color: P.slate }),
  ]));
});

// ---- 3. where the margin goes ------------------------------------------
doc_children.push(h1("Where the margin goes"));
doc_children.push(img("margin_waterfall", 6.4));
doc_children.push(caption(
  "Annualised. Fleet cost is shown as a cost of doing business rather than a " +
  "leak — it is the price of the service, not a failure of it."));

const WF = [5160, 2400, 1800];
const wf = payload.waterfall.map((w) => new TableRow({ children: [
  cell(para(w.item, { size: 19, after: 0 }), { w: WF[0] }),
  cell(para(aed(w.aed_annualised), { size: 19, after: 0, bold: w.kind === "net",
       color: w.kind === "leak" ? P.red : P.ink }), { w: WF[1] }),
  cell(para(w.kind, { size: 18, color: P.slate, after: 0 }), { w: WF[2] }),
] }));
doc_children.push(table(WF, [
  new TableRow({ children: [
    cell(para("Item", { size: 17, bold: true, color: P.slate, after: 0 }), { w: WF[0], fill: P.mist }),
    cell(para("Annualised", { size: 17, bold: true, color: P.slate, after: 0 }), { w: WF[1], fill: P.mist }),
    cell(para("Type", { size: 17, bold: true, color: P.slate, after: 0 }), { w: WF[2], fill: P.mist }),
  ] }),
  ...wf,
]));

// ---- 4. root cause ------------------------------------------------------
doc_children.push(new Paragraph({ children: [new PageBreak()] }));
doc_children.push(h1("What is actually going wrong"));

const byId = Object.fromEntries(payload.all_findings.map((f) => [f.id, f]));
const topThree = findings.filter((f) => !f.caused_by.length).slice(0, 3);

topThree.forEach((f) => {
  doc_children.push(h2(f.headline));
  doc_children.push(para([
    text("Worth ", {}),
    text(`${aed(f.magnitude_aed)} a year`, { bold: true, color: P.deep }),
    text(f.magnitude_low ? ` (range ${aed(f.magnitude_low)} to ${aed(f.magnitude_high)})` : "", { color: P.slate }),
    text(`, at ${pct(f.confidence, 0)} confidence.`, {}),
  ]));
  doc_children.push(para([text("Evidence", { bold: true, size: 20 })], { after: 60 }));
  f.evidence.forEach((e) => {
    const v = typeof e.value === "number"
      ? (Math.abs(e.value) < 1 && e.value !== 0 ? pct(e.value) : e.value.toLocaleString(undefined, { maximumFractionDigits: 2 }))
      : e.value;
    doc_children.push(bullet([
      text(`${e.label}: `, {}),
      text(String(v) + (e.unit ? ` ${e.unit}` : ""), { bold: true }),
      text(e.comparator ? `  (vs ${e.comparator})` : "", { color: P.slate, size: 18 }),
    ]));
  });
  doc_children.push(para([
    text("How the number was derived. ", { bold: true, size: 19 }),
    text(f.magnitude_basis, { size: 19, color: P.slate }),
  ], { after: 80 }));
  doc_children.push(para([
    text("Method. ", { bold: true, size: 19 }),
    text(f.method, { size: 19, color: P.slate }),
  ], { after: 160 }));

  if (f.id.startsWith("FLT")) doc_children.push(img("store_diagnosis", 6.0));
  if (f.id.startsWith("CAD")) doc_children.push(img("fill_rate_by_dow", 6.0));
  if (f.id.startsWith("SUP")) doc_children.push(img("supplier_reliability", 6.0));
  if (f.id.startsWith("LOT")) doc_children.push(img("waste_by_market", 6.0));
  if (f.id.startsWith("AST")) doc_children.push(img("pareto", 6.0));
});

// ---- 5. recommended actions --------------------------------------------
doc_children.push(new Paragraph({ children: [new PageBreak()] }));
doc_children.push(h1("Recommended actions"));

const W = [700, 3660, 2200, 1400, 1400];   // sums to the 6.5" text column
doc_children.push(table(W, [
  new TableRow({ children: [
    cell(para("#", { size: 17, bold: true, color: P.slate, after: 0 }), { w: W[0], fill: P.mist }),
    cell(para("Action", { size: 17, bold: true, color: P.slate, after: 0 }), { w: W[1], fill: P.mist }),
    cell(para("Owner", { size: 17, bold: true, color: P.slate, after: 0 }), { w: W[2], fill: P.mist }),
    cell(para("Net/yr", { size: 17, bold: true, color: P.slate, after: 0 }), { w: W[3], fill: P.mist }),
    cell(para("Payback", { size: 17, bold: true, color: P.slate, after: 0 }), { w: W[4], fill: P.mist }),
  ] }),
  ...acts.map((r) => new TableRow({ children: [
    cell(para(r.id, { size: 18, bold: true, after: 0 }), { w: W[0] }),
    cell(para(r.title, { size: 18, after: 0 }), { w: W[1] }),
    cell(para(r.owner, { size: 18, color: P.slate, after: 0 }), { w: W[2] }),
    cell(para(aed(r.net_annual_aed), { size: 18, bold: true, color: P.deep, after: 0 }), { w: W[3] }),
    cell(para(r.payback_months ? `${r.payback_months.toFixed(1)} mo` : "immediate",
         { size: 18, after: 0 }), { w: W[4] }),
  ] })),
]));

doc_children.push(img("action_value", 6.2));

acts.forEach((r) => {
  doc_children.push(h2(`${r.id} · ${r.title}`));
  doc_children.push(para([
    text(`${r.owner}  ·  ${r.horizon.replace("_", " ")}  ·  ${r.effort} effort  ·  addresses ${r.finding_ids.join(", ")}`,
         { size: 18, color: P.slate }),
  ], { after: 100 }));
  doc_children.push(para(r.action));
  doc_children.push(table([4680, 2340], [
    new TableRow({ children: [
      cell(para("Benefit, after capture rate", { size: 18, after: 0 }), { w: 4680 }),
      cell(para(aed(r.benefit_aed), { size: 18, after: 0 }), { w: 2340 })] }),
    new TableRow({ children: [
      cell(para("Cost of acting", { size: 18, after: 0 }), { w: 4680 }),
      cell(para(aed(r.annual_cost_aed + r.one_off_cost_aed), { size: 18, after: 0 }), { w: 2340 })] }),
    new TableRow({ children: [
      cell(para("Net annual", { size: 18, bold: true, after: 0 }), { w: 4680, fill: P.mist }),
      cell(para(aed(r.net_annual_aed), { size: 18, bold: true, color: P.deep, after: 0 }), { w: 2340, fill: P.mist })] }),
  ]));
  doc_children.push(para([text("Why. ", { bold: true, size: 19 }),
                          text(r.rationale, { size: 19 })], { before: 120 }));
  doc_children.push(para([text("Risk. ", { bold: true, size: 19, color: P.red }),
                          text(r.risk, { size: 19 })]));
  doc_children.push(para([text("Success metric. ", { bold: true, size: 19 }),
                          text(`${r.success_metric}. Reviewed ${r.review_cadence}.`, { size: 19 })]));
  doc_children.push(para([text("Assumptions", { bold: true, size: 19 })], { after: 50 }));
  r.assumptions.forEach((a) => doc_children.push(bullet(text(a, { size: 18, color: P.slate }))));
});

// ---- 6. considered and rejected ----------------------------------------
if (rejected.length) {
  doc_children.push(h1("Considered and not recommended"));
  rejected.forEach((r) => {
    doc_children.push(h2(`${r.id} · ${r.title}`));
    doc_children.push(para([
      text("Benefit ", {}), text(`${aed(r.benefit_aed)}/yr`, { bold: true }),
      text(" against a cost of ", {}),
      text(`${aed(r.annual_cost_aed)}/yr`, { bold: true, color: P.red }),
      text(" — net ", {}),
      text(`${aed(r.net_annual_aed)}/yr`, { bold: true, color: P.red }),
      text(".", {}),
    ]));
    doc_children.push(para(r.rationale));
  });
}

// ---- 7. what we would measure ------------------------------------------
doc_children.push(h1("What we would measure"));
doc_children.push(para(
  "Each action carries a leading indicator that moves before the financial " +
  "result does. If the indicator has not moved by the review point, the action " +
  "is not working and should be stopped rather than extended."));
const MW = [900, 6060, 2400];
doc_children.push(table(MW, [
  new TableRow({ children: [
    cell(para("#", { size: 17, bold: true, color: P.slate, after: 0 }), { w: MW[0], fill: P.mist }),
    cell(para("Leading indicator", { size: 17, bold: true, color: P.slate, after: 0 }), { w: MW[1], fill: P.mist }),
    cell(para("Cadence", { size: 17, bold: true, color: P.slate, after: 0 }), { w: MW[2], fill: P.mist }),
  ] }),
  ...acts.map((r) => new TableRow({ children: [
    cell(para(r.id, { size: 18, bold: true, after: 0 }), { w: MW[0] }),
    cell(para(r.success_metric, { size: 18, after: 0 }), { w: MW[1] }),
    cell(para(r.review_cadence, { size: 18, color: P.slate, after: 0 }), { w: MW[2] }),
  ] })),
]));

// ---- 8. appendix --------------------------------------------------------
doc_children.push(new Paragraph({ children: [new PageBreak()] }));
doc_children.push(h1("Appendix"));

doc_children.push(h2("Method"));
doc_children.push(para(
  "Data was loaded from nine related tables and profiled. A quality gate ran " +
  "eight families of check — key uniqueness, referential integrity, null rates, " +
  "impossible values, ledger balance, three cross-table reconciliations and date " +
  "coverage — before any analysis was permitted. KPIs were computed once, at " +
  "every grain, so that no two sections of this document can disagree. Eight " +
  "detectors then interrogated those KPIs, each returning findings with their own " +
  "evidence, statistical method and confidence."));
doc_children.push(para(
  "Confidence combines three components as a geometric mean: statistical strength, " +
  "sample adequacy, and the quality score of the source tables. The geometric mean " +
  "is deliberate — one weak component drags the result down and no strong component " +
  "can rescue it."));

doc_children.push(h2("Data quality"));
const q = payload.quality;
doc_children.push(para(
  `Gate result: ${q.gate}. ${q.issues.length} issue(s) found and ` +
  `${q.repairs.length} repair(s) applied before analysis. Repairs are ` +
  `deterministic and disclosed; no data was invented.`));
q.repairs.forEach((r) => doc_children.push(bullet(text(r, { size: 18, color: P.slate }))));

doc_children.push(para([text("Checks that ran clean", { bold: true, size: 19 })],
                       { before: 140, after: 60 }));
q.clean.forEach((c) => doc_children.push(
  bullet(text(`${c.check} · ${c.table} — ${c.detail}`, { size: 18, color: P.slate }))));

doc_children.push(h2("Assumptions"));
doc_children.push(para(
  "Every figure converting an operational failure into money rests on one of " +
  "these. They are declared so they can be challenged."));
const A = payload.assumptions;
doc_children.push(bullet(text(
  `Stockout penalty: lost margin × ${A.costs.stockout_margin_multiplier}. The uplift ` +
  `represents basket abandonment and reduced repeat rate. Not derived from this ` +
  `data. Sensitivity 1.0–1.7.`, { size: 18 })));
doc_children.push(bullet(text(
  `Cancelled order cost: AED ${A.costs.cancelled_order_cost_aed} of picking labour ` +
  `and rider time. Sensitivity 8–16.`, { size: 18 })));
doc_children.push(bullet(text(
  `Inventory holding: ${pct(A.costs.inventory_holding_annual_pct, 0)} annually.`,
  { size: 18 })));
doc_children.push(bullet(text(
  `Capture rates run ${pct(Math.min(...Object.values(A.capture_rate)), 0)} to ` +
  `${pct(Math.max(...Object.values(A.capture_rate)), 0)} — never 100%, because ` +
  `some part of every leak is structural.`, { size: 18 })));
doc_children.push(bullet(text(
  `Materiality floor: ${aed(A.materiality.min_annualised_impact_aed)}/yr. ` +
  `Findings below this are recorded but not surfaced.`, { size: 18 })));

doc_children.push(h2("Limitations — what this analysis cannot support"));
doc_children.push(para(
  "Stating the boundary matters as much as stating the result."));
[
  "The supplier premium behind R2 is a placeholder, not a quote. If smaller case " +
  "packs cost more than 1.5% extra per unit, that recommendation weakens quickly " +
  "and should be re-tested before committing.",
  "The 50% demand-migration assumption behind the assortment recommendation is " +
  "unverified. A basket-affinity analysis should precede any delisting, because " +
  "a tail SKU that anchors a basket is not a tail SKU.",
  "Seasonal conclusions rest on two observed cycles. That is enough to establish " +
  "the pattern exists and not enough to fit a reliable category-level uplift factor.",
  "Customer lifetime value is absent from this dataset, so cancellations are " +
  "valued at single-order margin. This almost certainly understates the cost of " +
  "repeated service failure at one store, and it is the assumption most likely to " +
  "change the fleet conclusion if corrected.",
  "No competitor, price or promotional data is present. Demand is treated as " +
  "exogenous, which it is not.",
  "The analysis is observational. None of the causal claims have been tested " +
  "experimentally, and the recommended actions should be piloted before " +
  "network-wide rollout.",
].forEach((t) => doc_children.push(bullet(text(t, { size: 19 }))));

// ---------------------------------------------------------------- document

const doc = new Document({
  creator: "Decision Brief Generator",
  title: "Supply Chain Decision Brief",
  numbering: {
    config: [{
      reference: "dots",
      levels: [
        { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 340, hanging: 200 } } } },
        { level: 1, format: LevelFormat.BULLET, text: "◦", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 700, hanging: 200 } } } },
      ],
    }],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 },
      },
    },
    headers: {
      default: new Header({ children: [para([
        text("Supply Chain Decision Brief", { size: 16, color: P.slate }),
        text(M.synthetic ? "   ·   ILLUSTRATIVE, SYNTHETIC DATA" : "",
             { size: 16, color: P.amber, bold: true }),
      ], { after: 0 })] }),
    },
    footers: {
      default: new Footer({ children: [new Paragraph({
        alignment: AlignmentType.RIGHT,
        children: [
          new TextRun({ text: "Page ", size: 16, color: P.slate }),
          new TextRun({ children: [PageNumber.CURRENT], size: 16, color: P.slate }),
        ],
      })] }),
    },
    children: doc_children,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(OUT, buf);
  console.log(`  ${OUT}  (${(buf.length / 1024).toFixed(0)} KB)`);
});
