#import "@preview/tracl:0.8.1": *
#import "@preview/pergamon:0.7.1": add-bib-resource, cite

#show: doc => acl(
  doc,
  anonymous: false,
  title: [VN-GeoQA: A Reproducible Vietnamese Geospatial\ Question Answering Benchmark],
  authors: make-authors(
    (
      name: "Anh Pham-Ky",
      affiliation: [University of Science, VNU-HCM\ #email("25C1503361@student.hcmus.edu.vn")],
    ),
    (
      name: "Tien Dang-Anh",
      affiliation: [University of Science, VNU-HCM\ #email("25C1102267@student.hcmus.edu.vn")],
    ),
    (
      name: "Thuat Nguyen-Thien",
      affiliation: [University of Science, VNU-HCM\ #email("25C1502531@student.hcmus.edu.vn")],
    ),
  ),
)

#abstract[
  VN-GeoQA is a Vietnamese geospatial QA benchmark: 2,800 questions over 28 templates, generated from a pinned OpenStreetMap Vietnam snapshot against PostGIS, with SQL-computed gold answers and location gold composed from native OSM `addr_*` components into a hierarchical Vietnamese address. We evaluate two 9B open models crossed with Direct and Text2SQL prompting under one frozen decoding profile. Direct leaves 2,214 of 2,800 questions unattempted for Ornith (79.1%) and 2,039 for Qwen, while Text2SQL scores best on every family in the held-out test split for both models, where a pre-registered zero-LLM intervention recovers 222 questions with zero regressions, raising entity text F1 by 0.162 and reducing distance relative error by 0.078. Address geocoding accounts for most measurable language-specific failure (46% of attempted location answers geocode to no address) and diacritic loss for almost none (at most 9).#footnote[Code and dataset are available at #link("https://github.com/itskyf/ViGSQA").]
]

= Introduction <sec:intro>

Asked directly which café is nearest to Notre-Dame Cathedral (_"Quán cà phê nào gần Nhà thờ Đức Bà nhất?"_), a language model tends to name a well-known café somewhere in the city, rarely the closest one. We benchmark this task: geospatial QA is thinly covered among LLM benchmarks, and we found no Vietnamese geospatial resource among the datasets surveyed in @sec:related. The language also differs structurally from English, inverting Western address ordering (_số nhà_ house number, _đường_ street, _phường/xã_ ward, _quận/huyện_ district, _tỉnh/thành phố_ province) with semantically contrastive tone marks, so address handling derived from English resources does not transfer. We port GS-QA's #cite("saeedan2026gsqa") construction methodology to Vietnam, inheriting its 28 templates, deterministic SQL-computed gold and spatial-aware evaluation, under SPARTQA's #cite("mirzaee2021spartqa") warrant that rule-based generation validated on a human-checked sample is a legitimate path to a language resource.

Our contributions are:
- *VN-GeoQA*: 2,800 questions regenerating byte-identically from a fixed seed, pinned snapshot and pinned generator, released with the evaluation artifacts and cache.
- Vietnamese adaptations: native `addr_*` location gold, 128 surface phrasings over 28 templates, 26 target categories, diacritic-stripped surfaces, NFKC scoring equating composed and decomposed diacritics.
- Four sealed Ornith/Qwen $times$ Direct/Text2SQL runs with per-family test metrics, plus a pre-registered zero-LLM intervention on a frozen 560/2,240 split whose dev gains transfer to test.
- An error taxonomy with Vietnamese-phenomenon flags: geocoding coverage accounts for most measurable language-specific failure, diacritic loss for almost none.

= Related Work <sec:related>

Prior geospatial QA resources are small: GeoQuestions201 has 201 questions #cite("punjani2018geoquestions201"), GeoQuestions1089 has 1,089 #cite("kefalidis2023geoquestions"), GeoAnQu 429 #cite("xu2020geoanqu"), and MapQA 3,154 over OpenStreetMap for two U.S. regions #cite("li2025mapqa"). GS-QA, the benchmark we port, replaces crowdsourced collection and knowledge-graph queries with generated SQL gold and adds questions needing a second source.

*Construction.* A _template_ is a question pattern with blanks, paired with the database query that fills those blanks and computes the answer at the same time, so gold is correct by construction and recomputable whenever the map changes. GS-QA builds a PostGIS database from a February 2024 US OpenStreetMap extract, crosses five spatial relationships with eight answer types to its 28 natural combinations, and keeps 100 questions per template, 10% reviewed by hand.
*Baselines and findings.* GS-QA crosses three LLMs with three strategies (bare prompting, Text2SQL, retrieval-augmented generation). Sonnet with Text2SQL reaches 0.23 average F1 against 0.07 bare, two-source questions fail almost completely, and compass questions sit near chance.

Vietnamese question answering is active, but we found no geospatial benchmark for the language. UIT-ViQuAD #cite("nguyen2020uitviquad") established reading comprehension over Vietnamese Wikipedia, later extended to community health questions #cite("thai2022vicov19qa") and spoken input #cite("minh2026visqa"). VIMQA #cite("le2022vimqa") is closest in spirit to our two-source questions, but its location answers are place names retrieved from text, not positions computed from geometry. ViText2SQL #cite("nguyen2020vitext2sql"), roughly 10,000 question–query pairs from translating Spider #cite("yu2018spider") into Vietnamese, is the closest structural relative to our Text2SQL baseline: its monolingual PhoBERT #cite("nguyen2020phobert") beats multilingual XLM-R, but its Spider databases carry no spatial operator.

Against all of the above, the distinguishing property of VN-GeoQA is that answers are computed from geometry rather than retrieved from text, over real OSM data rather than synthetic scenes.

= The VN-GeoQA Dataset <sec:dataset>

== Construction <sec:construction>

Every question is written by a program and its answer computed by a database rather than typed by a person. We take one dated OpenStreetMap extract of Vietnam #cite("osm") rather than the rolling one, check its checksum, and load it into PostGIS, which answers questions about distance, direction and containment that a plain file cannot. The map lands in five tables, 38,207 points of interest plus regions, parks, lakes and roads, each point carrying its name, a category, narrowing tags, its coordinates and up to eight address fields (@sec:locgold), the schema staying small because a Text2SQL model must be shown it in the prompt.

Generation draws a landmark, fills the blank, and runs the template's query. The returned row _is_ the gold answer, computed by the same database the baselines later query. A candidate whose answer set is empty or ambiguous, or that includes the landmark itself, is discarded and a new landmark drawn. This is what makes the process repeatable: the same seed against the same map produces the same 2,800 questions byte for byte, verified by generating twice and comparing (@fig:pipeline, @sec:appendix-templates). Two templates ask for something the map does not know, such as the year a building opened, meaningful only if the fact is genuinely absent: at release time we check that none of the attributes they use appears anywhere in the database, failing closed. The outside facts come from a frozen copy of Wikipedia, so generation never touches the network.

The benchmark contains seven kinds of question: the nearest place of a category to a landmark, every place within a radius, each restricted by compass direction, by the line towards a second landmark, or by a non-spatial filter such as "seafood", aggregates over a province or city, and two-source questions. Since the "total area" of one nearest café makes no sense, the 28 templates are the natural combinations of kind and answer type rather than the full product (@tab:templates, @sec:appendix-templates). Of the 2,800 questions, 1,100 expect a place name, 800 an address, 200 each a compass direction, a count and a distance, 100 each total area, length and a two-source fact, samples appear in @tab:samples (@sec:appendix-samples).

Each template is written in several Vietnamese phrasings rather than one, so models are not rewarded for memorising a single sentence shape: 128 phrasings across 28 templates. Every question is also stored with diacritics stripped, so _quán cà phê_ becomes _quan ca phe_, mirroring how Vietnamese is often typed. Target categories keep OSM tag granularity across 26 sub-categories, refined for the filter templates through a Vietnamese label lexicon (for example _restaurant_ expands to _nhà hàng món Việt_), all 26 non-empty in the address-bearing pool of @sec:locgold.

== Location Gold <sec:locgold>

GS-QA scores location answers on address text F1 and a Nominatim-geocoded distance, with a flat, U.S.-style gold string. Vietnamese addresses are hierarchical and administratively ordered, so a flat string discards the structure under test, and Nominatim's uneven Vietnamese coverage would bake the geocoder's errors into gold. We therefore take gold directly from OSM `addr_*` tags, compose the canonical string deterministically, and confine the geocoder to the prediction side.

A POI qualifies as address-bearing if it has a street or place name _and_ at least one broader locator, which yields 5,321 POIs. Coverage is uneven: 13,857 POIs carry a street name but only 72 a `place` and 7 a `suburb`, and district, city and province each cover roughly 4,500 to 4,800, differently, so the criterion accepts any of them. Gold comprises `geo_wkt` (driving the distance measure), the eight verbatim `addr_*` components with orthography frozen as OSM records it (including _Bắc Ninh_ beside _Bac Ninh_), and one deterministic canonical string. Nearest gold is the closest address-bearing candidate, radius gold the full distance-ordered set, median 2–6, maximum 542.

*Quality control.* Six gates guard the release, from a database rebuild and a smoke run to `diff -r`-clean regeneration, human review of five records per template, static runner checks and a release restore reproducing the original table counts. Every record is additionally checked for Unicode normalization, unreplaced placeholders, landmark exclusion, duplicates, well-formed gold SQL and canonical-string recomputability. Where GS-QA reviews 10% of its questions by hand, we verify 100% automatically and 5% by hand.

= Baselines <sec:method>

We evaluate two 9B open models, Ornith-1.5-9B #cite("ornith2026") and Qwen3.5-9B #cite("qwen35"), both NVFP4 4-bit quantized so each fits on a single GPU, served through vLLM #cite("kwon2023vllm").

*Direct.* The question goes to the model and the answer comes back, with no database and no retrieval (top of @fig:baselines). This measures what the model has memorized about Vietnamese places.

*Text2SQL.* Three stages (@fig:baselines, beneath). The model receives the schema and the question and writes SQL. PostgreSQL executes it against the same database that produced the gold answer, and the model narrates the returned rows in Vietnamese. A wrong answer is thus a reasoning or query-construction failure rather than a data mismatch, the stored stages localizing failures to generation, execution or narration (@sec:discussion).

*Scope, decoding, provenance.* We evaluate two of GS-QA's three baseline families, omitting dense-retrieval RAG for compute reasons, so the Text2SQL-versus-Direct gap is not directly comparable to GS-QA's best configuration. One decoding profile is frozen across all four runs (temperature 1.0, top-$p$ 0.95, top-$k$ 20, presence penalty 1.5, seed 42, reasoning enabled), so run differences come from the model and the baseline rather than from sampling. Every run is sealed by a checksum binding model, baseline, dataset, prompts and raw outputs. Malformed JSON is retried, a well-formed but wrong answer never is.

== A Zero-LLM Rescue Intervention <sec:rescue>

Inspecting Text2SQL failures revealed a recoverable class: the SQL runs, returns usable typed rows, and the model still emits no answer, so the score sits at the unattempted floor although the correct value is present in the executed rows. We therefore pre-register a zero-inference intervention on Ornith with Text2SQL. It fires only when the sealed run has no candidate answer, so answered questions are never touched and a per-question score can only improve or tie, asserted after every evaluation. The executed rows are re-emitted through the parser's own output shape: the first non-empty name column for entities, the address column or the canonical string rebuilt from `addr_*` for locations, the corresponding typed column otherwise. Two-source questions are never rescued, since the database cannot hold their answer. Making no model call, no retrieval and no prompt change, the intervention isolates how much measured failure is formatting rather than reasoning.

= Experimental Setup <sec:setup>

Two models crossed with two baselines give four sealed runs and 11,200 predictions. All free-text answers are parsed into a fixed JSON schema by one fixed parser, Ornith-1.5-9B under a frozen prompt and decoding profile, for all four runs, so the comparison uses the same parsing setup everywhere (for Qwen runs the parser differs from the generator). Address predictions are geocoded with Nominatim under its bulk-use policy (1 request per second). The accompanying notebook restores the sealed artifacts, reruns test evaluation, the rescue and the error analysis, and replays a five-question Vietnamese demo from published steps, so the full workflow executes without an inference server.

== Metrics <sec:metrics>

Text is normalized by Unicode NFKC, case folding and punctuation-to-space replacement, diacritics preserved, and tokens are the whitespace-separated words of the result. For the token multiset overlap $|p inter g|$ of prediction tokens $p$ and gold tokens $g$, counted with multiplicity, precision, recall and F1 are
$
  P = frac(|p inter g|, |p|), quad R = frac(|p inter g|, |g|), quad F_1 = frac(2 P R, P + R),
$
all higher-better on $[0, 1]$. Numeric answers (count, distance, area, length) are valid only as finite numbers after unit normalization (km to m, ha to m^2, counts integral), scored by the relative error capped at 1:
$
  E_"rel"(hat(y), y) = cases(min(frac(|hat(y) - y|, |y|), 1) " if" y != 0, 1 " otherwise") quad "with" E_"rel" = 0 " when" hat(y) = y.
$
Direction answers carry an azimuth in degrees, scored by the circular error normalized to $[0,1]$ and by token F1 over the eight Vietnamese sector labels (e.g. _bắc_ north, _đông nam_ southeast) the azimuths map to. Location answers are scored by address text F1 and by geodesic distance, the WGS84 distance $d$ from the Nominatim #cite("nominatim")-geocoded prediction to the gold geometry centroid:
$
  E_"circ"(hat(a), a) = frac(|((hat(a) - a + 180) mod 360) - 180|, 180), quad E_"geo" = min(frac(d, "500 km"), 1).
$

When several prediction or gold candidates are present (radius gold is a full distance-ordered set), the score reduces to the best applicable pair, maximizing $F_1$ for text metrics and minimizing the error otherwise, ties toward earlier candidates. A question is _attempted_ when the parsed output yields at least one valid candidate for its family, and unattempted questions remain in every mean at the worst case, $F_1 = 0$ or $E = 1$. All errors are lower-better on $[0, 1]$.

The metrics above are the official scores. Two further notions stay separate from them: for overview counts and the error taxonomy we call a question _correct_ under analysis-only thresholds, $F_1 >= 0.5$ or $E <= 0.1$ on the family's primary metric, which never enter the reported means, and the taxonomy labels a Direct question _refused_ when parsing succeeded but no candidate was emitted.

*Dev/test split.* We freeze the split before touching test data: within each template, questions are ranked by the hash of a fixed salt and their identifier, the first 20 of 100 going to dev, giving 560 dev and 2,240 test questions with no training split. The sealed artifacts are read-only, the intervention scored by importing the evaluator verbatim. Baseline aggregates track closely across the halves, location distance error 0.670 on dev against 0.643 on test, while direction text F1 diverges most, 0.712 against 0.552, so we read split differences of that size as sampling variation.


#figure(
  [#set text(size: 8pt)
    table(
    columns: (1fr, auto, auto, auto, auto, auto, auto),
    stroke: none,
    align: (left, center, center, center, center, center, center),
    table.hline(),
    table.header(
    [*Family*],
    [*Metric*],
    [O/D],
    [Q/D],
    [O/T2S],
    [Q/T2S],
    [+R],
    ),
    table.hline(stroke: 0.5pt),
    [full (2,800)], [att. $arrow.t$], [20.9%], [27.2%], [*54.2%*], [51.5%], [],
    [], [corr. $arrow.t$], [2.8%], [2.8%], [*32.4%*], [29.3%], [],
    table.hline(stroke: 0.25pt),
    [entity], [F1 $arrow.t$], [0.031], [0.055], [*0.278*], [0.269], [0.440],
    [location], [F1 $arrow.t$], [0.054], [0.058], [*0.387*], [0.290], [0.436],
    [], [dist $arrow.b$], [0.936], [0.974], [*0.643*], [0.680], [0.589],
    [direction], [F1 $arrow.t$], [0.078], [0.045], [*0.552*], [0.400], [0.571],
    [], [ang. $arrow.b$], [0.918], [0.942], [*0.433*], [0.577], [0.414],
    [distance], [rel $arrow.b$], [0.972], [0.950], [*0.645*], [0.665], [0.568],
    [count], [rel $arrow.b$], [0.954], [0.959], [*0.570*], [0.554], [0.570],
    [area], [rel $arrow.b$], [0.968], [0.963], [*0.711*], [0.793], [0.711],
    [length], [rel $arrow.b$], [0.955], [0.891], [*0.675*], [0.742], [0.675],
    [textual_fact], [F1 $arrow.t$], [0.000], [0.000], [0.000], [0.000], [0.000],
    table.hline(),
    )],
  caption: [Sealed runs (O = Ornith-1.5-9B, Q = Qwen3.5-9B, D = Direct, T2S = Text2SQL) and the zero-LLM intervention (+R, Ornith with Text2SQL, @sec:rescue). First two rows: full-benchmark rates over 2,800 questions, _attempted_ = at least one valid parsed candidate, _correct_ = analysis-only thresholds of @sec:metrics, +R empty (test-scoped). Other rows: per-family means over the 2,240 test questions (entity 880, location 640, direction 160, distance 160, count 160, area 80, length 80, textual_fact 80), unattempted at worst case. $arrow.t$ higher-better, $arrow.b$ lower-better. Bold = best of the four runs, excluding +R.],
) <tab:fourruns>

*Direct versus Text2SQL.* Under the evaluated configurations, database access separates the runs (@tab:fourruns). Ornith with Direct leaves 2,214 of 2,800 questions unattempted (79.1%), refusals concentrating on entity questions, 904 of 1,100, and locations, 572 of 800. Qwen with Direct refuses less (2,039) yet passes the thresholds on only 79, so its extra attempts are mostly wrong. Text2SQL engages every family for both models and improves every per-family test metric over Direct, consistent with GS-QA's English finding, sharper in one respect: without database access, a 9B model asked about Vietnamese places mostly declines to guess.

*The rescue.* The intervention recovers 222 of 2,240 test questions with zero regressions, lifting entity F1 by 0.162 and cutting distance relative error by 0.078 without a model call (the +R column of @tab:fourruns). Every family that improved on dev improved on test with matching sign and magnitude: much of the apparent failure was a model retrieving the right rows and failing to say so. Count, area, length and two-source questions produce no rescue candidates.

Two-source (textual_fact) F1 is 0.000 for every run, the benchmark working as designed: neither baseline can consult Wikipedia and the verifier guarantees the answer's absence from the schema. Ornith/Text2SQL compass error, 0.433, sits just below the 0.5 of random guessing.

= Error Analysis <sec:discussion>

Every question of the Ornith/Text2SQL run is classified by failure stage and flagged for Vietnamese phenomena (@tab:taxonomy, @sec:appendix-taxonomy).

*The expected Vietnamese failure mode does not occur.* We anticipated diacritic corruption in place names as a leading error class. It is not: across a full run at most 9 predictions match gold only after stripping diacritics from both, because NFKC normalization already equates composed and decomposed forms. Compass vocabulary is likewise sound, with only 14 answers naming a sector inconsistent with the azimuth they state, so the weakness is in the azimuth, not the Vietnamese terms.

*Geocoding is the recurring language-specific friction.* Of the 471 location questions where Ornith with Text2SQL produced candidates, 219 contain a predicted address Nominatim cannot resolve, 46%, against 139 for Qwen with Text2SQL and 175 for Ornith with Direct, reflecting how Vietnamese component order and postcode format diverge from what the geocoder expects. These questions still score through address text F1, but their spatial error is then governed by whatever the geocoder returns instead, which is why location distance error stays high even where the model named the right place. SQL generation dominates the remaining failure: for entity questions 100 statements errored and 280 ran to no rows, the largest single error class a subquery used as an expression while returning multiple rows, 107 of 295 erroneous statements. Qwen generates worse SQL, 209 entity errors against 100, while area and length fail at availability, with 34 and 43 cases of rows carrying no aggregate the family needs.

= Limitations <sec:limitations>

Our scope is narrow by design: two of GS-QA's three baseline families, two 9B models, one decoding profile, and runs differing from GS-QA's English ones in models, region and snapshot, so we make no claims at the level of model families and do not claim Vietnamese is harder. The intervention recovers only the refusal floor: attempted-but-wrong answers and failed queries are untouched, and area, length and two-source questions cannot be rescued. Location rescue may emit an address formatted differently from gold while naming the same place, so the reported F1 gains understate spatial recovery, and the location metric inherits Nominatim's coverage.

The benchmark inherits its source: OpenStreetMap coverage of Vietnam is denser in Hà Nội and Ho Chi Minh City than in rural provinces, with mapper noise present. We record these rather than patch them, since correcting crowd-sourced data would break reproducibility. The snapshot postdates the July 2025 administrative reform #cite("vnreform2025"), so address tags reflect a re-tagging still in progress.

= Ethical Considerations <sec:ethics>

VN-GeoQA is built from OpenStreetMap data under the OpenDbL licence and from Wikipedia infobox values under CC-BY-SA, and the release names both sources, links the exact snapshot and excludes residential buildings. Nominatim is used only on the prediction side within its bulk-access policy, and the dataset contains public map data and no personal information. A system optimized against fixed templates may overfit question shapes rather than improve spatial reasoning, mitigated but not eliminated by the 128 surface phrasings, and model outputs, including failures, are preserved verbatim rather than curated.

= Conclusion <sec:conclusion>

VN-GeoQA brings the GS-QA construction contract to Vietnamese address structure with byte-identical regeneration. Text2SQL attempts more than twice as many questions as Direct, scores best on every family, and the zero-LLM intervention recovers 222 test questions without regressions. Diacritics contribute almost nothing to residual error, address geocoding remains the measurable language-specific obstacle.

#add-bib-resource(read("references.bib"))
#print-acl-bibliography()

#show: it => appendix(it, clearpage: false)

= Sample Records <sec:appendix-samples>

@tab:samples shows six example records spanning six templates and six answer types. Two details are worth drawing out. First, the anchor landmark is stored by OSM identifier alongside its name, so a question can be traced back to the exact map feature that generated it and regenerated if that feature changes. Second, the gold answer for an address question is the set of tags the database returned rather than a string the generator wrote, with the readable form derived from them, which is what allows the canonical string to be recomputed and checked at verification time.

#figure(
  table(
    columns: (2.2fr, 5.5fr, 1.2fr, 4.5fr),
    stroke: none,
    align: (left, left, left, left),
    table.hline(),
    table.header(
      [*Template*],
      [*Question (Vietnamese, with gloss)*],
      [*Answer type*],
      [*Gold answer*],
    ),
    table.hline(stroke: 0.5pt),
    [`knn+name`],
    [Nhà hàng nào gần Nhà thờ Đức Bà nhất?\ #text(size: 0.85em, style: "italic")[Nearest restaurant to Notre-Dame?]],
    [name],
    [Nhà hàng Ngon],
    [`range+count`],
    [Có bao nhiêu quán cà phê trong bán kính 2 km từ Hồ Hoàn Kiếm?\ #text(size: 0.85em, style: "italic")[How many cafés within 2 km of Hoàn Kiếm Lake?]],
    [count],
    [47],
    [`knn+loc`],
    [Quán cà phê gần Nhà thờ Đức Bà nhất nằm ở đâu?\ #text(size: 0.85em, style: "italic")[Where is the nearest café to Notre-Dame?]],
    [loc],
    [6 Alexandre de Rhodes, Phường Bến Nghé, Quận 1, Thành phố Hồ Chí Minh\ #raw("POINT(106.6959 10.7797)", lang: "txt")],
    [`knn:direction`\ `+distance`],
    [Khách sạn gần nhất về phía bắc Văn Miếu cách bao xa?\ #text(size: 0.85em, style: "italic")[How far is the nearest hotel north of Văn Miếu?]],
    [distance],
    [780 m],
    [`knn+angle`],
    [Bảo tàng gần Cầu Rồng nhất nằm theo hướng nào?\ #text(size: 0.85em, style: "italic")[Direction of the museum nearest Dragon Bridge?]],
    [angle],
    [118° (đông nam)],
    [`knn+name`\ `+two_source`],
    [Chùa gần Kinh thành Huế nhất được xây dựng năm nào?\ #text(size: 0.85em, style: "italic")[Year the pagoda nearest Huế Citadel was built?]],
    [external],
    [1601 #text(size: 0.85em, style: "italic")[(Wikipedia, not in the schema)]],
    table.hline(),
  ),
  caption: [Sample records spanning six templates and six answer types. Glosses are for the reader, the dataset itself Vietnamese only. Location gold carries both a composed address and a geometry, scored by separate measures. The last row is a two-source question. Every question is also stored with diacritics removed (_Quan ca phe gan Nha tho Duc Ba..._).],
  placement: auto,
  scope: "parent",
) <tab:samples>

== A stored record <sec:appendix-record>

#figure(
  [
    #show raw: set text(size: 6.8pt)
    ```json
    {
      "id": "knn+loc-014",
      "type": "knn+loc",
      "answer_type": "loc",
      "question": "Quán cà phê gần Nhà thờ
                   Đức Bà nhất nằm ở đâu?",
      "question_surfaces": {
        "full":     "Quán cà phê gần Nhà thờ
                     Đức Bà nhất nằm ở đâu?",
        "stripped": "Quan ca phe gan Nha tho
                     Duc Ba nhat nam o dau?"
      },
      "sql": "SELECT id, geo_wkt, addr_* FROM
              pois WHERE amenity = 'cafe' AND
              (addr_street IS NOT NULL OR ...)
              ORDER BY geometry <-> $anchor
              LIMIT 1",
      "answers": [{
        "id": 20417,
        "address": "6 Alexandre de Rhodes,
                    Phường Bến Nghé, Quận 1,
                    Thành phố Hồ Chí Minh",
        "addr_housenumber": "6",
        "addr_street": "Alexandre de Rhodes",
        "addr_district": "Quận 1",
        "addr_city": "Thành phố Hồ Chí Minh",
        "addr_suburb": null, "addr_province": null,
        "geo_wkt": "POINT(106.6959 10.7797)"
      }],
      "question_entities": {
        "[1]": {"category": "cafe"},
        "[2]": {"osm_id": 4412907,
                "name": "Nhà thờ Đức Bà"}
      }
    }
    ```
  ],
  caption: [One record from the released dataset, abridged. The gold address is composed from the eight native `addr_*` tags in a fixed order, and `geo_wkt` is what the distance measure is computed against. Null components are kept rather than dropped, so the canonical string is always recomputable from what is stored.],
  kind: image,
  placement: auto,
) <fig:record>

== Surface variation <sec:appendix-surfaces>

Every template ships with several interchangeable phrasings, one of which is chosen at random per question. The complete set for `knn+name` (T01) is, with the gloss "which [1] is nearest to [2]?":

```
[1] nào gần [2] nhất?
[1] gần nhất với [2] là gì?
Cho tôi biết [1] gần [2] nhất.
Đâu là [1] gần [2] nhất?
Tìm giúp tôi [1] gần [2] nhất.
[1] gần [2] nhất có tên là gì?
Tôi đang tìm [1] gần [2] nhất.
```

The phrasings differ in politeness and in whether the question is an interrogative or a request, both common in Vietnamese search queries. Across all 28 templates there are 128 such phrasings.

= The 28 Templates <sec:appendix-templates>

Each template is a spatial predicate crossed with an answer type, and each is realized by several Vietnamese surface phrasings. @tab:templates gives the full inventory. Placeholders are `[1]` for the target category, `[2]` for the radius or the anchor, and `[3]` for a second anchor where the predicate needs one.

#figure(
  image("figures/fig3_pipeline.svg", width: 95%),
  caption: [Generation pipeline. Shaded stages reject rather than repair: a question that fails validation is discarded and the anchor resampled, so no partially-valid record reaches the release. Every stage is deterministic given the seed and the snapshot.],
  placement: auto,
) <fig:pipeline>

#figure(
  image("figures/fig1_baselines.svg", width: 88%),
  caption: [The two baselines. Direct tests what a model knows about Vietnamese geography, and Text2SQL tests whether it can express a spatial question as a query. Each Text2SQL stage is stored separately, so a failure can be attributed to query generation, execution, or narration rather than to the pipeline as a whole.],
  placement: auto,
) <fig:baselines>

#figure(
  [
    #set text(size: 7.8pt)
    #table(
      columns: (auto, auto, auto, auto, 1fr),
      stroke: none,
      align: (left, left, left, left, left),
      table.hline(),
      table.header(
        [*ID*],
        [*Template*],
        [*Spatial predicate*],
        [*Answer*],
        [*Vietnamese surface pattern*],
      ),
      table.hline(stroke: 0.5pt),
      [T01],
      [`knn+name`],
      [nearest neighbour],
      [name],
      [`[1]` nào gần `[2]` nhất?],
      [T02],
      [`knn:direction+name`],
      [nearest + compass],
      [name],
      [`[1]` gần nhất về phía `[3]` của `[2]` là gì?],
      [T03],
      [`knn:towards+name`],
      [nearest + towards],
      [name],
      [`[1]` gần `[2]` nhất theo hướng `[3]` là gì?],
      [T04],
      [`knn:filter+name`],
      [nearest + non-spatial],
      [name],
      [`[1]` nào gần `[2]` nhất? (narrowed `[1]`)],
      [T05],
      [`range+name`],
      [within radius],
      [name],
      [`[1]` nào nằm trong bán kính `[2]` từ `[3]`?],
      [T06],
      [`range:direction+name`],
      [radius + compass],
      [name],
      [`[1]` nào nằm trong `[2]` về phía `[3]`?],
      [T07],
      [`range:towards+name`],
      [radius + towards],
      [name],
      [`[1]` nào trong `[2]` theo hướng `[3]`?],
      [T08],
      [`range:filter+name`],
      [radius + non-spatial],
      [name],
      [`[1]` nào nằm trong bán kính `[2]` từ `[3]`?],
      [T09],
      [`intersects:area_max`],
      [region overlap],
      [name],
      [`[1]` lớn nhất ở `[2]` là gì?],
      [T10],
      [`intersects:length_max`],
      [region overlap],
      [name],
      [`[1]` dài nhất ở `[2]` là gì?],
      [T11],
      [`knn+two_source`],
      [nearest + external],
      [external],
      [`[1]` gần `[2]` nhất được xây dựng năm nào?],
      [T12],
      [`knn+two_source:anchor`],
      [nearest + external],
      [name],
      [`[1]` gần `[3]` nhất là gì? (`[3]` described)],
      [T13],
      [`knn+loc`],
      [nearest neighbour],
      [loc],
      [`[1]` gần `[2]` nhất nằm ở đâu?],
      [T14],
      [`knn:direction+loc`],
      [nearest + compass],
      [loc],
      [`[1]` gần nhất về phía `[3]` của `[2]` ở đâu?],
      [T15],
      [`knn:towards+loc`],
      [nearest + towards],
      [loc],
      [`[1]` gần `[2]` nhất theo hướng `[3]` ở đâu?],
      [T16],
      [`knn:filter+loc`],
      [nearest + non-spatial],
      [loc],
      [`[1]` gần `[2]` nhất nằm ở đâu?],
      [T17],
      [`range+loc`],
      [within radius],
      [loc],
      [`[1]` trong bán kính `[2]` từ `[3]` nằm ở đâu?],
      [T18],
      [`range:direction+loc`],
      [radius + compass],
      [loc],
      [`[1]` trong `[2]` về phía `[3]` nằm ở đâu?],
      [T19],
      [`range:towards+loc`],
      [radius + towards],
      [loc],
      [`[1]` trong `[2]` theo hướng `[3]` nằm ở đâu?],
      [T20],
      [`range:filter+loc`],
      [radius + non-spatial],
      [loc],
      [`[1]` trong bán kính `[2]` từ `[3]` nằm ở đâu?],
      [T21],
      [`knn+angle`],
      [nearest neighbour],
      [angle],
      [`[1]` gần `[2]` nhất nằm theo hướng nào?],
      [T22],
      [`range+angle`],
      [within radius],
      [angle],
      [`[1]` trong bán kính `[2]` từ `[3]` nằm theo hướng nào?],
      [T23],
      [`range+count`],
      [within radius],
      [count],
      [`Có bao nhiêu `[1]` trong bán kính `[2]` từ `[3]`?],
      [T24],
      [`intersects+count`],
      [region overlap],
      [count],
      [`Có bao nhiêu `[1]` ở `[2]`?],
      [T25],
      [`knn+distance`],
      [nearest neighbour],
      [distance],
      [`[1]` gần `[2]` nhất cách bao xa?],
      [T26],
      [`range+distance`],
      [within radius],
      [distance],
      [`[1]` trong bán kính `[2]` từ `[3]` cách bao xa?],
      [T27],
      [`intersects:area_total`],
      [region overlap],
      [area],
      [Tổng diện tích các `[1]` ở `[2]` là bao nhiêu?],
      [T28],
      [`intersects:length_total`],
      [region overlap],
      [length],
      [Tổng chiều dài các `[1]` ở `[2]` là bao nhiêu?],
      table.hline(),
    )
  ],
  caption: [The 28 templates, grouped by answer type: entity name (T01--T12), address (T13--T20), and the numeric and directional types (T21--T28). One surface pattern is shown per template, the released files contain 128 in total.],
  placement: auto,
  scope: "parent",
) <tab:templates>

The prompt texts, the dataset manifest, and the reproduction recipe are included in the public release.

= Error Taxonomy Details <sec:appendix-taxonomy>

#figure(
  [
    #set text(size: 8pt)
    #table(
      columns: (auto, auto, auto, auto, auto, auto, auto),
      stroke: none,
      align: (left, right, right, right, right, right, right),
      table.hline(),
      table.header(
        [*Family*],
        rotate(-60deg, reflow: true)[*correct*],
        rotate(-60deg, reflow: true)[*wrong*],
        rotate(-60deg, reflow: true)[*rescuable*],
        rotate(-60deg, reflow: true)[*no rows*],
        rotate(-60deg, reflow: true)[*SQL err*],
        rotate(-60deg, reflow: true)[*unusable*],
      ),
      table.hline(stroke: 0.5pt),
      [entity], [313], [198], [208], [280], [100], [1],
      [location], [275], [196], [48], [168], [46], [65],
      [direction], [108], [22], [4], [44], [18], [4],
      [count], [85], [92], [1], [0], [22], [0],
      [distance], [66], [52], [24], [44], [12], [2],
      [area], [29], [11], [0], [0], [26], [34],
      [length], [30], [5], [0], [0], [22], [43],
      [textual_fact], [1], [35], [0], [7], [28], [29],
      table.hline(),
    )],
  caption: [Failure stage by family for Ornith with Text2SQL over all 2,800 questions. _Wrong_ means the model produced candidates and missed, _rescuable_ means usable rows existed but no answer was emitted, and _unusable_ means rows existed with no typed value for the family. Two parse failures across the run are omitted.],
  placement: auto,
) <tab:taxonomy>
