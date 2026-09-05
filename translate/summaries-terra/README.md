# Superseded summaries (openai:gpt-5.6-terra)

The it/en/ja segment summaries (`{part}.md`) and one-line canto summaries
(`{part}-1.md`) as `summarize_segments.py` / `summarize1.py` first produced
them, with `-m openai:gpt-5.6-terra`. They were the contents of `../../it/`,
`../../en/` and `../../ja/` from commit 6aa4dfd until the regeneration with
`google:gemini-2.5-pro`. Nothing has been edited into them since; the one
change is the blank first line every `{part}.md` used to start with, dropped
here and in the regenerated set alike once `format_summary_md()` stopped
emitting it.

Kept because the project's premise is that its text is Gemini 2.5 Pro's:
these files are not, and regenerating them was what put the summaries back
under that premise. Keeping the superseded set makes the two passes
comparable after the fact - a diff against the current `{part}.md` shows
what changed - and costs the repository almost nothing, since the blobs
were already in history under their old paths.

Not read by anything. `templates/build.py` and the pipeline scripts address
`../../{it,en,ja}/{part}.md` by fixed path, never by glob, so these copies
sit outside every code path.

See [../README.md](../README.md#summary-generation-passes) for why the
summaries were regenerated. This file records what the two passes actually
produced.

## Measurements

Structurally they are the same set: 34 cantos / 126 paragraphs for Inferno
and 33 / 125 for the other two, in all three languages, with no gaps - the
segmentation is fixed by `../segments/{part}.jsonl`, so nothing else was
possible.

They differ in length. Words for Italian and English, characters for
Japanese, per paragraph, given as Gemini / Terra:

| | | total | avg | min | max | ratio |
|---|---|---|---|---|---|---|
| inferno | it | 12,097 / 12,849 | 96.0 / 102.0 | 55 / 58 | 141 / 173 | 0.94 |
| | en | 12,563 / 13,808 | 99.7 / 109.6 | 63 / 60 | 133 / 187 | 0.91 |
| | ja | 30,925 / 33,092 | 245.4 / 262.6 | 116 / 122 | 352 / 432 | 0.93 |
| purgatorio | it | 11,884 / 12,546 | 95.1 / 100.4 | 42 / 38 | 157 / 237 | 0.95 |
| | en | 12,461 / 13,353 | 99.7 / 106.8 | 45 / 39 | 157 / 252 | 0.93 |
| | ja | 30,244 / 32,202 | 242.0 / 257.6 | 119 / 88 | 348 / 584 | 0.94 |
| paradiso | it | 12,915 / 13,574 | 103.3 / 108.6 | 62 / 57 | 154 / 190 | 0.95 |
| | en | 13,217 / 14,344 | 105.7 / 114.8 | 63 / 54 | 153 / 204 | 0.92 |
| | ja | 32,977 / 34,913 | 263.8 / 279.3 | 148 / 108 | 398 / 505 | 0.94 |

Gemini is 5-9% shorter in every one of the nine, and its longest paragraph
is shorter in every one of the nine as well - by a wide margin in places
(Purgatorio ja, 348 characters against 584). Minimums go both ways.

The prompt tells the model to match the length and detail of the summaries
it is given as a guide. Correlating each paragraph's length against its
guide's length in `../../en.jsonl` measures how far that was taken:

| | inferno | purgatorio | paradiso |
|---|---|---|---|
| Gemini | 0.38-0.41 | 0.48-0.56 | 0.46-0.48 |
| Terra | 0.63-0.67 | 0.61-0.64 | 0.53-0.55 |

(ranges over the three languages)

Terra follows the guide's length more closely in all three parts. Against
the Italian source segment's line count instead, the two are close in
Purgatorio and Paradiso (Gemini 0.48-0.55, Terra 0.46-0.59) and separate
only in Inferno (Gemini 0.33-0.42, Terra 0.55-0.59). And Gemini's average
does move between parts - 99.7, 99.7, 105.7 English words - so it is not
writing to a fixed length; it just responds less to the guide than Terra
does.

## Side by side: Inferno 1, segment 1

The poem's opening segment (Inf. I 1-30). English only below; the Italian
and Japanese of each pass track their English closely, since both passes
write the Italian first and make the other two strict translations of it.

Both passes were given the same starting point: the summaries the
translation runs had produced independently, in `../../en.jsonl` and
`../../ja.jsonl`, as a guide to scope and length only. Those two are the
reason `summarize_segments.py` exists - they do not describe the same
things.

**`../../en.jsonl`** (Gemini 2.5 Pro, translation pass) - 56 words:

> The narrator, in the middle of his life, finds himself lost in a dark
> wood, having strayed from the correct path. He describes the terror the
> wood inspires, but feels his fear recede when he reaches a hill whose peak
> is lit by the sun's rays. After a brief rest, he begins to ascend the
> slope.

**`../../ja.jsonl`** (Gemini 2.5 Pro, translation pass) - 74 characters:

> 人生の道の半ばで道に迷い、暗い森で恐怖に苛まれた語り手は、太陽の光が差す丘を見つけて希望を取り戻す。恐ろしい谷間を振り返った後、彼は丘を登り始める。

The English describes the terror and the rest before the climb and never
looks back at the pass; the Japanese has the narrator regain hope, drops
the rest, and does look back. Zipped into a summary page as a pair, they
would not correspond.

**Terra** (`en/inferno.md` here) - 60 words:

> In the middle of life, the narrator finds himself in a dark wood after
> losing the straight path, and describes its harshness and terror. Having
> reached the foot of a hill illuminated by the sun's rays, his fear
> subsides; after looking back at the dangerous passage from which he has
> fled, he resumes his journey by climbing the deserted slope.

**Gemini 2.5 Pro** (`../../en/inferno.md`) - 69 words:

> Midway through his life, the narrator gets lost in a dark wood, having
> strayed from the straight path. He describes the terror the wood inspires
> in him, but his fear subsides when he reaches a hill whose peak is lit by
> the sun's rays. After turning to look back at the perilous pass from which
> he has fled and resting a little, he begins to ascend the deserted slope.

Both cover the same beats in the same order - losing the way, the wood's
terror, the sunlit hill, the backward look at the pass, the climb up the
deserted slope - in the same present tense and register, and both merge the
two guides rather than following either alone: each takes the terror from
the English and the backward look from the Japanese. Both also keep the
narrator's act of describing, which the prompt's ban on meta-phrases does
not quite reach.

Where they part, the guide is usually the explanation:

- Gemini stays much closer to the English guide's wording, keeping "having
  strayed from the ... path", "describes the terror the wood inspires",
  "a hill whose peak is lit by the sun's rays" and "begins to ascend the ...
  slope" nearly intact. Terra rewrites throughout - "harshness and terror",
  "the foot of a hill illuminated by the sun's rays", "resumes his journey".
  Note this is the opposite of what the length statistics show, where it is
  Terra that tracks the guides more closely; the two passes follow the guide
  on different axes.
- Gemini's Japanese renders "passo" as 危険な谷間, which reads as an
  interpretation the Italian does not commit to - but it comes straight from
  the Japanese guide's 恐ろしい谷間 rather than from the model.
- Gemini restores the rest before the climb ("resting a little", Inf. I 28),
  which the English guide has and Terra drops.
- Terra places the sunlight at the foot of the hill; Gemini, following the
  guide, puts it on the peak, which is what the source says ("vestite già
  de' raggi del pianeta").
- Terra packs the last three beats into one semicolon-joined sentence;
  Gemini uses three sentences and reads more evenly.
- Length runs the other way here than over the poem as a whole: Gemini is
  longer in this segment (69 vs 60 words) although its paragraphs are
  shorter in every part overall.

One caveat on reading a single segment: a `-s inferno:1:1` probe run before
the full pass produced a visibly different Gemini summary of this same
segment - four sentences, carrying over the shipwreck simile of Inf. I
22-27 that no version above mentions. Segment 1 has no preceding-segment
context to differ on, so that is sampling variance alone. Treat one segment
as an illustration, not a measurement.
