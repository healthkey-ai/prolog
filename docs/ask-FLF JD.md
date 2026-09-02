# Questions for FLF

Open items needing FLF confirmation or input for the Global Patient Survey 2026 app. Sections 1–2 confirm decisions we made on 2026-08-28 to keep the build moving (each lists what we did and what changes if FLF decides otherwise); section 3 collects the remaining product/launch questions. Full context: docs/implementation-plan.md §7.

## 1\. Please confirm these interpretations of the survey doc (V0.6)

1. **Q10 branching** — the doc says Q10 (“what caused the problem or delay?”) is asked “only if **Q8** \= yes”, but Q8 has no yes/no answer. We gated Q10 on **Q9** (“Have you ever experienced problems or delays accessing a treatment your doctor recommended?”) \= Yes. Correct? Please also fix the reference in the next doc revision.

2. **Q22 ranking “Other”** — the ranking question includes “Other (free text)”. We made ranking the six fixed outcomes mandatory and the “Other” item optional (rank it only if the respondent adds text). Is that the intent?

3. **Q24c rows** — the interference matrix shows one 1–5 row per symptom selected in Q24b (including “Other”, labeled with the respondent’s own text). Confirm.

## 2\. Please confirm these product decisions

4. **Skip policy (soft-required)** — respondents who tap Next without answering get a one-time “Skip this question?” confirmation; confirming records an explicit skip and they can return later. Nothing except Q28 (free text) and Q29 (email) skips silently, and no question hard-blocks progress. Acceptable for year-on-year comparability? (Skips are recorded distinctly, so “skipped” is analyzable and never conflated with “not reached”.)

5. **Country list** — Q1 use UK, EU countries, US, Australia and New Zealand plus “Prefer not to say”, rather than a curated subset. OK?

6. **Typography** — Neue Haas Grotesk is commercially licensed, so the app ships with a close free fallback (Hanken Grotesk / Helvetica Neue). **Can FLF supply licensed NHG webfont files?** If yes, they drop in with no rebuild; if no, please approve the fallback as permanent.

7. **Translations** — Spanish and Portuguese question text is **machine-translated** (marked machine in the survey definition and disclosed as such to respondents; per \#11 this now launches rather than blocking launch). **Who at FLF can review ES and PT, and by when?** Review is no longer a gate, but it is the highest-value thing FLF can do to the survey: the clinical terms below are where machine translation most often goes wrong. Notable choices to check: usted (formal) for ES; Brazilian-leaning Portuguese with você; “plano de saúde” for “insurance” in PT; “recaída/recidiva” for relapse; drug names Rituximabe/Obinutuzumabe (PT) vs Rituximab/Obinutuzumab (ES).

8. **Data protection** — FLF is the **data controller**; HealthKey is the **data processor**. The survey will be hosted on **Google Cloud Platform in the UK**. Users who provide an email address can request deletion of their data at any time. Our policies: no cookies beyond a single browser resume token, no IP logging, no third-party analytics. Can you approve?

9. **Launch languages** — the survey will launch **EN+ES+PT together** once translations are reviewed. Can you approve?

10. **Q29 — storing answers and the optional email.** All survey answers are stored against a Person record in PRomop. Respondents who do not provide an email remain fully anonymous — their Person record holds nothing identifying. Respondents who provide an email at Q29 get an **identified record**: their answers are held against it, they can request deletion of their data at any time, and future surveys can skip what we already know. This is implemented in [PR \#11](https://github.com/healthkey-ai/FLFSurvey/pull/11). Can you approve this approach?

## 3\. Open questions

11. **Q14/Q15 proposal (future revision)** — respondents who answer Q11/Q12 \= 1 (“Not informed at all”) are still asked the 14-option barrier questions; today “I am unsure” is their escape hatch. For a future survey revision, consider hiding Q14 when Q11 \= 1 and Q15 when Q12 \= 1\. (2026 ships verbatim either way, preserving comparability with 2024/25.)

12. **Privacy policy — please review, and confirm where it lives.** We have drafted a privacy notice: [**docs/privacy-policy.md**](http://privacy-policy.md) (FLFSurvey\#10). Please have FLF’s legal adviser review it — the **\[FLF\]** markers are values only FLF can supply. We propose serving it at **\<survey domain\>/privacy** (same origin, all three languages, linked from intro and Q29; runner capability prolog\#6). The exact domain is \#15 below and does not need solving now.

13. **Intro page copy** — the doc’s participant-facing paragraph is used verbatim; the headline (“Your voice helps beat follicular lymphoma”), the “\~10 minutes · anonymous” claims, and the completion-page copy are ours. Please approve or supply preferred wording.

14. **Section titles** — the structure table says “Decision-making and support” while the section heading says “Decision-making burden and support”. We used the section heading; confirm which should face patients.

15. **Hosting & domain** — where should the survey live (e.g. survey.theflf.org), and who manages DNS/SSL? **Not urgent** — the app runs on its provider hostname until a domain is pointed at it, and the privacy notice at /privacy (\#12) follows whatever domain is chosen. Needed before launch, not before build.

16. **Results access** — please provide the list of who gets access to the response export/dashboard. We will provide a completion-metrics view (starts, drop-off by question) during the fieldwork period.

ADDITIONAL FEEDBACK ON ONLINE SURVEY

For the final page ‘COMPLETE’

It would be nice to add a link to the FLF website here.  Your can find FL resources here [https://www.theflf.org/](https://www.theflf.org/)

Add FLF Logo to the first and last page