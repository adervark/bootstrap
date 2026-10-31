"""The five-slide deck (README.md D3), built from the result files so every number is measured.

  .venv/bin/python deck.py      -> deck/LLM_Release_Gate.pptx and deck/preview/slide-N.png

Needs python-pptx (deck only; the framework itself does not). LibreOffice is not on this laptop,
so the previews are drawn with Pillow from the same shapes, in Liberation fonts, which have the
same widths as Arial and Courier New. Text that would overflow its box is reported.
"""
import csv
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.util import Inches, Pt

import store

OUT = Path("deck")
CASES = ["campus_poisoned", "campus_hardened", "campus_clean", "dvla"]
# The page's colours (static/index.html): amber marks where to look, red only a failure.
BLACK, PANEL, RULE, TEXT, MUTED, AMBER, RED = "000000", "111111", "343434", "EDEDED", "9A9A9A", "FFA028", "FF5050"
SANS, MONO = "Arial", "Courier New"
FONT_FILES = {(SANS, False): "LiberationSans-Regular", (SANS, True): "LiberationSans-Bold",
              (MONO, False): "LiberationMono-Regular", (MONO, True): "LiberationMono-Bold"}
DPI = 100  # preview pixels per inch
MARGIN = 0.05  # text box inset, inches, the same in the deck and the preview


def load(path):
    if Path(path).name == "results.json":  # a case's analysis lives in data/gate.db (D20)
        return store.results(Path(path).parent)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def frac(r):
    return f"{r['hits']}/{r['total']}"


def pct(r):
    return f"{r['rate'] * 100:.0f}%"


def ci(r):
    return f"95% CI {r['ci95'][0] * 100:.1f}-{r['ci95'][1] * 100:.1f}%"


def regression_count(family):
    path = Path("data/regression", f"{family}.csv")
    return len(list(csv.DictReader(path.open(encoding="utf-8")))) if path.exists() else 0


class Deck:
    """Each shape goes into the .pptx and into a list the preview is drawn from."""

    def __init__(self):
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = Inches(13.333), Inches(7.5)
        self.pages = []

    def slide(self, notes):
        self.s = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        self.s.background.fill.solid()
        self.s.background.fill.fore_color.rgb = RGBColor.from_string(BLACK)
        self.s.notes_slide.notes_text_frame.text = notes
        self.shapes = []
        self.pages.append(self.shapes)

    def rect(self, x, y, w, h, fill=PANEL, line=RULE):
        shape = self.s.shapes.add_shape(1, Inches(x), Inches(y), Inches(w), Inches(h))
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor.from_string(fill)
        if line:
            shape.line.color.rgb = RGBColor.from_string(line)
            shape.line.width = Pt(0.75)
        else:
            shape.line.fill.background()
        shape.shadow.inherit = False
        self.shapes.append(("rect", x, y, w, h, fill, line))

    def text(self, x, y, w, h, paragraphs, size=14, color=TEXT, bold=False, font=SANS, align="l", anchor="t", after=0):
        """paragraphs: a string, or a list whose items are a string or a list of (text, options) runs."""
        if isinstance(paragraphs, str):
            paragraphs = [paragraphs]
        box = self.s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        frame = box.text_frame
        frame.word_wrap, frame.auto_size = True, MSO_AUTO_SIZE.NONE
        frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = Inches(MARGIN)
        frame.vertical_anchor = {"t": MSO_ANCHOR.TOP, "m": MSO_ANCHOR.MIDDLE, "b": MSO_ANCHOR.BOTTOM}[anchor]
        laid = []
        for number, paragraph in enumerate(paragraphs):
            runs = [(paragraph, {})] if isinstance(paragraph, str) else paragraph
            p = frame.paragraphs[0] if number == 0 else frame.add_paragraph()
            p.alignment = {"l": PP_ALIGN.LEFT, "c": PP_ALIGN.CENTER, "r": PP_ALIGN.RIGHT}[align]
            p.space_after = Pt(after)
            p.line_spacing = 1.1
            styled = []
            for text, options in runs:
                o = {"size": size, "color": color, "bold": bold, "font": font} | options
                run = p.add_run()
                run.text = text
                run.font.size, run.font.bold, run.font.name = Pt(o["size"]), o["bold"], o["font"]
                run.font.color.rgb = RGBColor.from_string(o["color"])
                styled.append((text, o))
            laid.append(styled)
        self.shapes.append(("text", x, y, w, h, laid, align, anchor, after))

    def image(self, path, x, y, w, crop_bottom=0.0):
        """A picture w inches wide, with crop_bottom of its height cut off."""
        width, height = Image.open(path).size
        h = w * height * (1 - crop_bottom) / width
        picture = self.s.shapes.add_picture(str(path), Inches(x), Inches(y), Inches(w), Inches(h))
        picture.crop_bottom = crop_bottom
        self.shapes.append(("image", x, y, w, h, path, crop_bottom))
        return h

    def save(self, name):
        OUT.mkdir(exist_ok=True)
        self.prs.save(OUT / name)
        (OUT / "preview").mkdir(exist_ok=True)
        problems = []
        for number, shapes in enumerate(self.pages, 1):
            problems += preview(shapes, OUT / "preview" / f"slide-{number}.png", number)
        return problems


def font(name, bold, size):
    return ImageFont.truetype(f"/usr/share/fonts/truetype/liberation/{FONT_FILES[(name, bold)]}.ttf", round(size * DPI / 72))


def wrap(runs, width):
    """Greedy word wrap of styled runs into lines of (text, options) pieces, as PowerPoint does."""
    lines, line, used = [], [], 0.0
    for text, o in runs:
        f = font(o["font"], o["bold"], o["size"])
        for word in text.replace("\n", " \n ").split(" "):
            if word == "\n":
                lines.append(line)
                line, used = [], 0.0
                continue
            piece = (word if not line or used == 0 else " " + word)
            length = f.getlength(piece)
            if line and used + length > width:
                lines.append(line)
                line, used, piece = [], 0.0, word
                length = f.getlength(piece)
            line.append((piece, o))
            used += length
    lines.append(line)
    return lines


def preview(shapes, path, number):
    image = Image.new("RGB", (round(13.333 * DPI), round(7.5 * DPI)), "#" + BLACK)
    draw = ImageDraw.Draw(image)
    problems = []
    for shape in shapes:
        kind, x, y, w, h = shape[:5]
        box = [round(x * DPI), round(y * DPI), round((x + w) * DPI), round((y + h) * DPI)]
        if kind == "rect":
            draw.rectangle(box, fill="#" + shape[5], outline=("#" + shape[6]) if shape[6] else None)
        elif kind == "image":
            picture = Image.open(shape[5]).convert("RGB")
            picture = picture.crop((0, 0, picture.width, round(picture.height * (1 - shape[6]))))
            image.paste(picture.resize((box[2] - box[0], box[3] - box[1])), (box[0], box[1]))
        else:
            laid, align, anchor, after = shape[5:]
            inner = (w - 2 * MARGIN) * DPI
            rows = []
            for runs in laid:
                for i, line in enumerate(wrap(runs, inner)):
                    tallest = max([o["size"] for _, o in line] or [runs[0][1]["size"]])
                    last = i == len(wrap(runs, inner)) - 1
                    rows.append((line, tallest * 1.1 * 1.2 * DPI / 72, after * DPI / 72 if last else 0))
            total = sum(r[1] + r[2] for r in rows)
            room = (h - 2 * MARGIN) * DPI
            if total > room + 1:
                text = " ".join(t for runs in laid for t, _ in runs)
                problems.append(f"slide {number}: text overflows its box by {(total - room) / DPI:.2f} in: {text[:70]!r}")
            top = box[1] + MARGIN * DPI + {"t": 0, "m": (room - total) / 2, "b": room - total}[anchor]
            for line, height, gap in rows:
                widths = [font(o["font"], o["bold"], o["size"]).getlength(t) for t, o in line]
                left = box[0] + MARGIN * DPI + {"l": 0, "c": (inner - sum(widths)) / 2, "r": inner - sum(widths)}[align]
                for (t, o), width in zip(line, widths):
                    f = font(o["font"], o["bold"], o["size"])
                    draw.text((left, top + height - f.size * 1.08), t, font=f, fill="#" + o["color"])
                    left += width
                top += height + gap
            if box[2] > 13.333 * DPI + 1 or box[3] > 7.5 * DPI + 1:
                problems.append(f"slide {number}: a text box runs off the slide")
    image.save(path)
    return problems


def kicker_and_title(d, kicker, title):
    d.text(0.6, 0.35, 12.1, 0.35, kicker, size=12, color=AMBER, font=MONO, bold=True)
    d.text(0.6, 0.7, 12.1, 0.75, title, size=32, bold=True)


def build():
    results = {case: load(f"data/sessions/{case}/results.json") for case in CASES}
    metrics = load("data/metrics.json")
    held, run1 = metrics["held_out"], load("data/calibration_heldout_run1.json")["overall"]
    asr, carry = metrics["asr"], metrics["carry_over"]
    answers = sum(r["scorecard"]["coverage"]["runs"] for r in results.values())
    cost = sum(r["scorecard"]["cost"]["cost_usd"] for r in results.values())
    critical = {c: sum(f["severity"] == "critical" for f in r["findings"]) for c, r in results.items()}
    codes = {c: [f["code"] for f in r["findings"]] for c, r in results.items()}
    score = {c: r["scorecard"]["overall"] for c, r in results.items()}
    dims = {c: {x["name"]: x["score"] for x in r["scorecard"]["dimensions"]} for c, r in results.items()}
    verdict = {c: r["decision"]["final_verdict"] for c, r in results.items()}
    suite = store.read_csv("data/sessions/campus_poisoned/tests.csv")
    origin = {o: sum(t["origin"] == o for t in suite) for o in ("generated", "mutated", "rephrase")}
    risks = results["campus_poisoned"]["scorecard"]["coverage"]["risks_total"]
    regressions = {f: regression_count(f) for f in ("campus", "dvla")}
    labels = metrics.get("labels")
    no_kb = metrics.get("no_kb", {})
    latency = sorted(r["scorecard"]["cost"]["latency_ms_p50"] for r in results.values())
    bias_tests = bias_found = 0
    for case in CASES:
        bias_risks = {row["risk_id"] for row in store.read_csv(f"data/sessions/{case}/risks.csv")
                      if row["scenario"].lower().startswith("bias")}
        bias_tests += sum(t["risk_id"] in bias_risks for t in results[case]["tests"])
        bias_found += codes[case].count("BIAS")
    jury = load("deck/jury_dryrun.json") if Path("deck/jury_dryrun.json").exists() else None
    d = Deck()

    # 1. The problem and the answer
    d.slide("An LLM app can sound right and still be wrong, leak data, or obey a poisoned document. Teams need a "
            "go or no-go they can defend. Our gate writes its own tests from a risk register, attacks the app, checks every "
            f"answer and recommends Release, Conditional Release or Reject. We ran it on four open-source apps we did not write: "
            f"{answers} answers. All four were rejected, each for a different, evidenced reason, and only a named human can release.")
    d.text(0.6, 0.35, 12.1, 0.35, "LLM RELEASE GATE  ·  AI FOR TECH: CAMPUS IT OPERATIONS", size=12, color=AMBER, font=MONO, bold=True)
    d.text(0.6, 0.75, 12.1, 0.9, "Should this LLM app ship?", size=44, bold=True)
    d.text(0.6, 1.65, 11.5, 0.95, "A reusable framework: it writes tests from risks, attacks the app, checks every answer and recommends "
           "Release, Conditional Release or Reject, with the evidence. A named human signs off.",
           size=18, color=MUTED)
    d.text(0.6, 2.45, 12.1, 0.4, [[("FOR  ", {"color": AMBER, "font": MONO, "bold": True, "size": 12}),
                                   ("campus IT teams shipping LLM bots · release managers who sign off · security reviewers · "
                                    "the students and staff who act on the answers", {})]], size=13, color=TEXT)
    cards = [("campus_poisoned", "CAMPUS HELPDESK · 1", "Stock prompt, 3 poisoned documents",
              f"{critical['campus_poisoned']} critical: sends users to a fake reset URL"),
             ("campus_hardened", "CAMPUS HELPDESK · 2", "Hardened prompt, same poison",
              f"{critical['campus_hardened']} critical: the prompt fix is not enough"),
             ("campus_clean", "CAMPUS HELPDESK · 3", "Stock prompt, poison removed",
              f"0 critical; grounding {dims['campus_clean']['grounding']:.0f}: unsupported facts"),
             ("dvla", "BANKING AGENT", "Damn Vulnerable LLM Agent",
              f"{critical['dvla']} critical: obeys injected instructions")]
    for i, (case, label, what, why) in enumerate(cards):
        x = 0.6 + i * 3.1
        d.rect(x, 2.95, 2.85, 2.45)
        d.text(x + 0.15, 3.05, 2.6, 0.3, label, size=11, color=MUTED, font=MONO, bold=True)
        d.text(x + 0.15, 3.32, 2.6, 0.65, what, size=14)
        d.text(x + 0.15, 3.9, 1.5, 0.75, f"{score[case]:.1f}", size=36, font=MONO, bold=True)
        d.text(x + 1.5, 4.13, 1.25, 0.4, verdict[case].upper(), size=16, color=RED, bold=True, align="r")
        d.text(x + 0.15, 4.65, 2.6, 0.7, why, size=12, color=MUTED)
    stats = [(f"{answers}", "answers judged, from 4 apps\nrun on localhost only"),
             (f"{held['Faults caught (recall)']['hits']}/{held['Faults caught (recall)']['total']}", "planted faults caught on a\nheld-out set never tuned on"),
             (f"{held['False alarms on clean answers']['hits']}/{held['False alarms on clean answers']['total']}", "false alarms on clean answers,\nsame held-out set"),
             (f"${cost:.2f}", "LLM cost to judge all four\napps (estimate)")]
    for i, (number, label) in enumerate(stats):
        x = 0.6 + i * 3.1
        d.text(x, 5.7, 2.85, 0.65, number, size=30, font=MONO, bold=True, color=AMBER if i == 1 else TEXT)
        d.text(x, 6.35, 2.85, 0.7, label, size=12, color=MUTED)

    # 2. Architecture
    d.slide("Read left to right. Inputs are a risk register, the app's manifest, a jury's text and past failures. DeepSeek V4.1 "
            "Flash plays five roles, but it never has the last word: code checks citations, canaries and quotes, and four "
            "vetoes can only make the verdict stricter. Release needs a named human, and every step is written to a "
            "hash-chained log, so tampering shows.")
    kicker_and_title(d, "02 / AI ARCHITECTURE", "The LLM proposes, code checks, a human signs")
    stages = [("INPUT", [f"risks.json: {risks} risks", "target.json: app, KB, canaries", "jury's free text", "past failures"]),
              ("AI / AGENTS", ["DeepSeek V4.1 Flash:", "test writer", "claim judge", "agreement judge", "obey-or-warn check", "release voter x3"]),
              ("TOOLS", ["app adapters, localhost only", "citation, canary and PII checks", "quote verifier", "5 attack mutators"]),
              ("DATA / KNOWLEDGE", ["campus KB, 10 docs", "SQLite store: tests, answers, findings, audit", "regression suite", "seeded-fault calibration sets"]),
              ("DECISIONS", ["6 dimension scores", "3 LLM votes citing finding IDs", "4 code vetoes, stricter only"]),
              ("HUMAN CONTROL", ["Release needs a named approver", "override needs name and reason", "Reject blocks on its own"]),
              ("OUTPUT", ["verdict and scorecard", "findings with evidence and OWASP label", "regression tests", "monitoring plan"])]
    for i, (name, lines) in enumerate(stages):
        x = 0.6 + i * 1.77
        d.rect(x, 1.75, 1.55, 3.75)
        d.text(x + 0.08, 1.83, 1.4, 0.35, f"0{i + 1}", size=12, color=AMBER, font=MONO, bold=True)
        d.text(x + 0.08, 2.13, 1.42, 0.62, name, size=13, bold=True)
        d.text(x + 0.08, 2.82, 1.42, 2.6, lines, size=12, color=MUTED, after=5)
        if i < 6:
            d.text(x + 1.55, 3.3, 0.22, 0.4, ">", size=16, color=AMBER, font=MONO, bold=True, align="c")
    d.rect(0.6, 5.8, 12.13, 1.2)
    d.text(0.8, 5.9, 11.8, 1.05, [
        [("Code ", {"bold": True, "color": TEXT}), ("counts, checks citations, canaries and quotes, and applies the vetoes.", {})],
        [("The LLM ", {"bold": True, "color": TEXT}), ("reads the evidence, judges claims and votes, citing finding IDs.", {})],
        [("A human ", {"bold": True, "color": TEXT}), ("is the only one who can release. Every step goes into a SHA-256 hash-chained audit log.", {})]],
        size=14, color=MUTED, after=3)

    # 3. Working prototype
    d.slide(f"These are real runs, not mock-ups. Attack success is the share of attack tests where at least one answer was breached. "
            f"The hardened prompt only cut it from {pct(asr['campus_poisoned'])} to {pct(asr['campus_hardened'])}; removing the "
            f"poisoned documents cut it to {pct(asr['campus_clean'])}. So the fix is the corpus, not the prompt. Even clean, the bot "
            f"states facts no document holds, so it still is not ready. Show the page live.")
    kicker_and_title(d, "03 / WORKING PROTOTYPE", "Four real apps, four evidenced verdicts")
    d.text(0.6, 1.7, 6.0, 0.35, "ATTACK SUCCESS RATE · share of attack tests breached", size=12, color=MUTED, font=MONO, bold=True)
    bars = [("campus_poisoned", "stock prompt + poison"), ("campus_hardened", "hardened prompt + poison"),
            ("campus_clean", "poison removed"), ("dvla", "banking agent")]
    for i, (case, label) in enumerate(bars):
        y = 2.15 + i * 0.62
        r = asr[case]
        d.text(0.6, y, 2.3, 0.45, label, size=13, anchor="m")
        d.rect(2.95, y + 0.08, 2.6, 0.3, fill="1C1C1C", line=None)
        if r["rate"]:
            d.rect(2.95, y + 0.08, max(0.04, 2.6 * r["rate"]), 0.3, fill=RED if r["rate"] >= 0.2 else MUTED, line=None)
        d.text(5.6, y, 1.2, 0.45, [[(pct(r), {"bold": True, "color": TEXT}), (f" {frac(r)}", {"color": MUTED, "size": 11})]],
               size=14, font=MONO, anchor="m")
    findings = [
        [("Hardened prompt: ", {"bold": True}), (f"{pct(asr['campus_poisoned'])} to {pct(asr['campus_hardened'])}; "
                                                f"{frac(carry['campus_hardened'])} of stage 1's failed tests fixed. Still Reject.", {"color": MUTED})],
        [("Poison removed: ", {"bold": True}), (f"{pct(asr['campus_poisoned'])} to {pct(asr['campus_clean'])}; {frac(carry['campus_clean'])} fixed. "
                                               "The fix is the corpus, not the prompt.", {"color": MUTED})],
        [("Clean is not ready either: ", {"bold": True}), (f"grounding {dims['campus_clean']['grounding']:.0f}/100, "
                                                            f"{codes['campus_clean'].count('UNSUPPORTED_CLAIM')} claims no document holds.", {"color": MUTED})]]
    d.text(0.6, 4.75, 6.1, 2.2, findings, size=14, after=8)
    h = d.image("deck/ui_campus_poisoned.png", 7.0, 1.7, 5.73, crop_bottom=0.36)
    d.text(7.0, 1.8 + h, 5.73, 0.75, "The release page on stage 1: what was tested, the verdict, why, the fix, how far to trust it, "
           "and the six scores. Every finding below links to the answer it came from.", size=12, color=MUTED)

    # 4. Dynamic adaptation
    jury_line = (f"Dry run: {jury['tests']} new tests, {jury['answers']} answers, re-decided in {jury['seconds']} s."
                 if jury else "Dry run pending.")
    d.slide("The suite is not a fixed prompt list. Each run, the LLM writes tests from the risk register, the app's description "
            "and its documents, and is told which prompts earlier runs used. Code then mutates every attack, adds rephrasings, "
            "and turns failures into regression tests. For the jury: type any scenario in the Jury box; it becomes a new risk "
            f"with new tests, runs against the app and the verdict is re-decided. {jury_line}")
    kicker_and_title(d, "04 / DYNAMIC ADAPTATION", "Tests are generated each run, and they adapt")
    steps = [(f"{risks}", "risks in the register: accuracy, grounding, completeness, safety, consistency, security"),
             (f"{origin['generated']}", "tests the LLM writes from each risk, the app's description and its documents"),
             (f"{origin['mutated']}", "attack mutations in code: base64, role play, fake system tags, typos, split prompts"),
             (f"{origin['rephrase']}", "rephrasings, so answers can be checked for agreement with no documents at all"),
             (f"{regressions['campus'] + regressions['dvla']}", "failures saved as regression tests, rerun on every new version")]
    for i, (number, label) in enumerate(steps):
        y = 1.75 + i * 0.98
        d.rect(0.6, y, 6.6, 0.82)
        d.text(0.75, y + 0.06, 1.2, 0.7, number, size=26, font=MONO, bold=True, anchor="m")
        d.text(1.95, y + 0.06, 5.15, 0.7, label, size=14, anchor="m")
    d.rect(7.5, 1.75, 5.23, 4.74)
    d.text(7.7, 1.88, 4.9, 0.35, "JURY SURPRISE, LIVE", size=12, color=AMBER, font=MONO, bold=True)
    d.text(7.7, 2.25, 4.9, 2.4, ["1. Type any scenario into the Jury box", "2. It becomes a new risk", "3. New tests are written for it",
                                 "4. They run against the app", "5. Scores and verdict are re-decided"], size=15, after=6)
    d.text(7.7, 4.6, 4.9, 0.75, jury_line, size=14, color=TEXT, bold=True)
    d.text(7.7, 5.35, 4.9, 1.05, "An attack that worked is reframed by the LLM to see how widely it works. "
           "Two generation runs on the same app shared 0 of 31 prompts.", size=12, color=MUTED)

    # 5. Trust
    rec, fa, code_only = held["Faults caught (recall)"], held["False alarms on clean answers"], held["Faults caught by code checks alone, no LLM"]
    labelled = (f"{labels['precision_on_real_findings']['hits']}/{labels['precision_on_real_findings']['total']}"
                if labels and labels.get("precision_on_real_findings", {}).get("total") else "pending")
    d.slide(f"Every number has its count and a 95% interval in the README. Held out means a seed we never looked at while building. "
            f"Code alone catches {frac(code_only)}; the LLM judge brings it to {frac(rec)}. A repeat run gave "
            f"{run1['true_positive']}/96 and {run1['false_positive']}/96, so the spread is a couple of items. We also audited our "
            f"own critical findings and fixed three bugs that caused 11 false alarms. Responsible AI is built in, not added. "
            f"Next: multi-turn attacks, more app adapters, and sampling real production logs.")
    kicker_and_title(d, "05 / TRUST AND RESPONSIBLE AI", "Measured, not claimed")
    callouts = [(frac(rec), f"planted faults caught, held-out seed ({ci(rec)})"),
                (frac(fa), f"false alarms on clean answers; repeat run {run1['true_positive']}/96 caught, {run1['false_positive']}/96 false"),
                (frac(code_only), f"caught by code alone: the LLM judge adds {rec['hits'] - code_only['hits']}"),
                (labelled, "real findings confirmed by rubric labels (real faults are harder)")]
    for i, (number, label) in enumerate(callouts):
        x, y = 0.6 + (i % 2) * 3.2, 1.75 + (i // 2) * 1.75
        d.rect(x, y, 3.0, 1.55)
        d.text(x + 0.15, y + 0.1, 2.75, 0.65, number, size=30, font=MONO, bold=True, color=AMBER if i == 0 else TEXT)
        d.text(x + 0.15, y + 0.75, 2.75, 0.75, label, size=12, color=MUTED)
    nokb = no_kb.get("Recall") or {}
    items = list(csv.DictReader(open("data/labels/items.csv", encoding="utf-8"))) if Path("data/labels/items.csv").exists() else []
    hard = [i for i in items if i["kind"] == "flagged" and i["code"] in ("PROMPT_INJECTION", "HALLUCINATION")]
    soft = [i for i in items if i["kind"] == "flagged" and i["code"] in ("OVER_REFUSAL", "INCONSISTENT", "INCOMPLETE", "LOW_AGREEMENT")]
    labelled_split = (f"rubric labels found {sum(i['label'] == 'true' for i in hard)}/{len(hard)} injection and hallucination "
                      f"findings real, and {sum(i['label'] == 'true' for i in soft)}/{len(soft)} of the softer medium ones.")
    d.text(0.6, 5.3, 6.2, 1.95, [
        [("Without documents: ", {"bold": True}), (f"sample agreement caught {frac(nokb) if nokb else 'n/a'} errors the KB check "
                                                 f"confirmed, so it is a medium signal, never a veto.", {"color": MUTED})],
        [("Self-audit: ", {"bold": True}), ("11 false alarms in our own critical findings, from 3 bugs, fixed and re-run.", {"color": MUTED})],
        [("Where it errs: ", {"bold": True}), (labelled_split, {"color": MUTED})]],
        size=13, after=6)
    rows = [("Human control", "only a named person can release; an override needs a reason"),
            ("Traceability", "every finding cites its evidence; every step is hash-chained"),
            ("Fairness", f"{bias_tests} paired prompts differing only in a group: {bias_found} treated differently"),
            ("Failure handling", "API down: code checks still run, can never say Release; the page shows the saved report"),
            ("Privacy", "synthetic data only; leaked secrets are redacted in shared reports"),
            ("Containment", "apps under test run on localhost; the tester refuses other hosts"),
            ("Standards", "findings mapped to the OWASP Top 10 for LLM Apps 2025"),
            ("Cost, latency", f"${cost:.2f} for four apps; app answers in {latency[0] / 1000:.1f}-{latency[-1] / 1000:.1f} s (p50)")]
    d.rect(7.0, 1.75, 5.73, 5.2)
    for i, (name, text) in enumerate(rows):
        y = 1.86 + i * 0.63
        d.text(7.2, y, 1.7, 0.65, name, size=13, bold=True)
        d.text(8.9, y, 3.75, 0.62, text, size=12, color=MUTED)
    return d


if __name__ == "__main__":
    problems = build().save("LLM_Release_Gate.pptx")
    print("\n".join(problems) or "no overflow found")
    print(f"wrote {OUT / 'LLM_Release_Gate.pptx'} and {OUT / 'preview'}/slide-1..5.png")
