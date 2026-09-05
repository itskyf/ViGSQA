#import "@preview/tracl:0.8.1": *

#show: doc => acl(
  doc,
  anonymous: false,
  title: [VN-GeoQA: A Reproducible Vietnamese Geospatial\ Question Answering Benchmark],
  authors: make-authors(
    (
      name: "Anh Pham-Ky",
      affiliation: [University of Science, VNU-HCM\ #email("25C0000000@student.hcmus.edu.vn")],
    ),
    (
      name: "Tien Dang-Anh",
      affiliation: [University of Science, VNU-HCM\ #email("25C1102267@student.hcmus.edu.vn")],
    ),
  ),
)

#abstract[
  Vietnamese geospatial question answering has no public benchmark. We introduce *VN-GeoQA*, a Vietnamese adaptation of the GS-QA benchmark: 2,800 questions over 28 templates, generated from a pinned OpenStreetMap Vietnam snapshot against a PostGIS database, with gold answers computed by SQL at generation time. Location gold is taken from native OSM `addr_*` components composed into a hierarchical Vietnamese address rather than a geocoded string. We evaluate two 9B open models crossed with Direct and Text2SQL prompting under one frozen decoding profile. Text2SQL is decisively the right architecture: Direct refuses roughly 82% of questions, answering only 77 of 2,800 correctly, while Text2SQL engages every family. On a frozen 560/2,240 dev/test split we pre-register a zero-LLM intervention that recovers 222 test questions with zero regressions, raising entity text F1 by 0.162 and cutting distance relative error by 0.078.#footnote[Code and dataset are available at #link("https://github.com/itskyf/ViGSQA").]
]

= Introduction <sec:intro>

Consider an everyday question about a map: _"Quán cà phê nào gần Nhà thờ Đức Bà nhất?"_, or in English, which café is nearest to Notre-Dame Cathedral? Answering it requires identifying the landmark, retrieving its coordinates, understanding that "nearest" is a spatial comparison rather than a popularity judgment, and returning a specific café that actually exists. A language model asked this question directly tends to name a well-known café somewhere in the city, which is often not the closest one.

This is the task we benchmark. Large language models are evaluated on strong general-domain QA benchmarks, but geospatial QA remains thinly covered and Vietnamese geospatial resources are effectively absent. The gap is not only one of volume. Vietnamese addresses invert Western ordering (_số nhà_, _đường_, _phường/xã_, _quận/huyện_, _tỉnh/thành phố_), and Vietnamese tone marks are semantically contrastive, so address handling derived from English resources does not transfer.

We port the construction methodology of GS-QA @saeedan2026gsqa to Vietnam. GS-QA supplies the design contract: 28 templates, deterministic SQL-computed gold, and an evaluation suite that combines text matching with spatial-aware measures. SPARTQA @mirzaee2021spartqa supplies the methodological warrant that rule-based automatic generation, paired with a human-verified sample, is a legitimate path to a language resource.

Our contributions are:
- *VN-GeoQA*, 2,800 questions that regenerate byte-identically from a fixed seed, a pinned snapshot and a pinned generator, published with the evaluation artifacts and cache.
- Vietnamese adaptations: native `addr_*` location gold, 128 surface phrasings across 28 templates, a 26-entry Vietnamese category lexicon, parallel diacritic-stripped surfaces, and NFKC-based scoring that equates composed and decomposed diacritics.
- Four baseline runs, each _sealed_: every output is stored with a hash binding it to the exact model, prompts and dataset that produced it.
- A frozen 560/2,240 dev/test split and a pre-registered zero-LLM intervention whose dev gains transfer to test with matching sign and magnitude.
- A measured Vietnamese error taxonomy showing that geocoding coverage, not diacritic handling, is the language-specific bottleneck.

= Related Work <sec:related>

== GS-QA <sec:gsqa>

GS-QA addresses four limitations of prior geospatial QA benchmarks: small size, crowdsourced construction, a knowledge-graph query paradigm that constrains expressible spatial operations, and the absence of questions needing a second source. Prior resources are small: GeoQuestions201 has 201 questions, GeoQuestions1089 has 1,089, GeoAnQu has 429, and the concurrent MapQA has 3,154 over OpenStreetMap for two U.S. regions.

*Construction.* A _template_ is a question pattern with blanks, such as "What is the nearest {category} to {landmark}?", paired with a database query that fills those blanks and computes the correct answer at the same time. Because the answer comes from the database rather than from a person or a model, it is correct by construction and can be recomputed whenever the map changes. GS-QA builds a PostGIS database from a February 2024 US OpenStreetMap extract (267,612 points of interest, plus parks, lakes, roads and administrative regions) and crosses five spatial relationships (nearest neighbour, within a radius, in a compass direction, in the direction of a second landmark, and overlapping a region) with eight answer types, keeping the 28 combinations that produce natural questions. One thousand questions are generated per template and down-sampled to 100 for diversity, giving 2,800; 10% are reviewed by hand. Two templates deliberately require a fact the database does not store, forcing a system to combine the map with Wikipedia; we call these _two-source_ questions throughout.

*Baselines and findings.* Three LLMs (GPT-4o, Claude Sonnet 4.6, Ministral-3) are crossed with three strategies (bare prompting, Text2SQL, and retrieval-augmented generation) for nine configurations plus a random baseline. Answers are scored by token F1 on free text and then, after parsing into a fixed schema, by type-specific measures. The best configuration is Sonnet with Text2SQL at 0.23 average F1 against 0.07 for bare Sonnet. Text2SQL beats both alternatives throughout; two-source questions fail almost completely; compass-direction questions sit at chance for most systems; and configurations given more context _attempt_ fewer questions, which the authors read as appropriate abstention.

== SPARTQA <sec:spartqa>

SPARTQA targets textual spatial reasoning, where bAbI Task 17 was previously the only dedicated dataset and is too simple: three objects, four directions, at most two reasoning steps. It releases 1.1k QA pairs written by annotators over visual scenes, where experts score 92%, and some 93.7k generated by grammars and reasoning rules applied to a stored scene graph rather than raw text. Further pretraining BERT on the automatic data lifts accuracy on the human set from 30.17 to 47.25, while a stories-only ablation reaching 32.90 shows the gain comes from the annotations rather than from more text; it transfers to bAbI and boolQ, though human performance at 92.31 stays far above every model. The relevant lesson for us is methodological: rule-based generation validated on a human-checked sample is an accepted way to build a language resource.

== Vietnamese Language Resources <sec:vnresources>

Vietnamese question answering is active, but no geospatial benchmark exists for the language. UIT-ViQuAD @nguyen2020uitviquad established reading comprehension over Vietnamese Wikipedia, and VIMQA @le2022vimqa is closest in spirit to our two-source questions, with over 10,000 multi-hop questions and sentence-level supporting facts; 15% of its answers are locations, but they are place names retrieved from text, not positions computed from geometry, and nothing in it requires a distance or a direction. Later work extends the format to community health questions @thai2022vicov19qa and spoken input @minh2026visqa. None is grounded in a map.

ViText2SQL @nguyen2020vitext2sql is the closest structural relative to our Text2SQL baseline: roughly 10,000 question–query pairs produced by translating Spider into Vietnamese. Its findings bear on our setting: word segmentation improves parsing, schema linking needs corpus statistics rather than string overlap, and the monolingual PhoBERT beats multilingual XLM-R. Its databases, however, are Spider's synthetic academic schemas, so no query involves a spatial operator. Separately, normalizing Vietnamese addresses is a recognized practical problem tackled mostly by engineering tools rather than benchmarks, and it became harder on 1 July 2025, when Vietnam consolidated 63 provincial-level units into 34 and abolished the district (_quận/huyện_) tier outright @vnreform2025. Crowd-sourced map data updates unevenly after such a change, so any nearby snapshot mixes pre- and post-reform naming; we preserve OpenStreetMap's orthography verbatim (@sec:locgold).

== Positioning

VN-GeoQA inherits GS-QA's contract of 28 templates, SQL-computed gold and spatial-aware metrics, together with SPARTQA's paradigm of rule-based generation validated on a human-checked sample. We differ from GS-QA in language, region, address semantics, and baseline scope: we evaluate two of its three baseline families and omit RAG. We differ from SPARTQA in operating over real OSM geometry rather than synthetic scenes, and in not running its language-model pretraining branch. Against the Vietnamese resources above, our distinguishing property is that answers are computed from geometry rather than retrieved from text.

= The VN-GeoQA Dataset <sec:dataset>

== How a Question Is Made

Every question is written by a program and its answer computed by a database rather than typed by a person. Walking through one question end to end is the quickest way to see why the rest of the design follows.

We start from a map. OpenStreetMap publishes a downloadable extract of Vietnam; we take one dated copy rather than the rolling one and check its checksum, so a rebuild six months from now reads the same data. It is loaded into a spatial database, which can answer questions about distance, direction and containment that a plain file cannot.

Next we pick a template, say _which café is nearest to {landmark}_. The program draws a real landmark from the map at random but reproducibly, perhaps Notre-Dame Cathedral in Ho Chi Minh City, fills the blank, and runs the query belonging to that template. The database returns one row, and _that row is the gold answer_. Nobody decides what is correct; the map does.

The candidate then has to pass a few checks: the answer set must not be empty, or the question is unanswerable; it must not be ambiguous, or two answers would be equally right; and the landmark must not appear in its own answer list. A failing candidate is discarded and a new landmark drawn. Nothing is patched up, which is what makes the process repeatable: the same seed against the same map produces the same 2,800 questions byte for byte, verified by generating them twice and comparing. @fig:pipeline in the appendix diagrams the loop. Only then is the question phrased in Vietnamese and checked once more by a verifier.

== What the Database Holds

The map is loaded into five tables: 38,207 points of interest, plus regions, parks, lakes and roads. Points anchor the "nearest" and "within a radius" questions, the polygon tables support containment and area, and roads support length. Keeping the schema small matters twice over, since a Text2SQL model must be shown it in the prompt. Each point of interest carries its name, a broad category such as restaurant or museum, tags that narrow that category so "a restaurant" becomes "a seafood restaurant", its coordinates, and up to eight address fields, which @sec:locgold explains. A few places link to their Wikipedia entry, though no fact from it is stored.

*Keeping two-source questions honest.* Two of the templates ask for something the map does not know, such as the year a building opened. These are only meaningful if the fact is genuinely absent; otherwise a system could answer by reading one more column instead of consulting an outside source. We therefore check at release time that none of the eight attributes those questions use appears anywhere in the database, and the check fails closed. The outside facts come from a frozen copy of Wikipedia, so generation never touches the network.

== What the Questions Ask <sec:whatweask>

The benchmark contains seven kinds of question: the nearest place of a category to a landmark; every place within a radius; either restricted to a compass direction, to the line towards a second landmark, or by a non-spatial filter such as "seafood"; aggregates over a province or city; and two-source questions. Not every kind combines with every answer type, since the "total area" of one nearest café makes no sense, so the 28 templates are the natural combinations rather than the full product (@tab:samples). The answer type matters more than it might appear: naming _which_ café is nearest and saying _where_ it is are different tasks, and a system can get the first right while failing the second, so they are scored separately.

Each template is written in several Vietnamese phrasings rather than one, so models are not rewarded for memorising a single sentence shape: 128 phrasings across 28 templates. Every question is also stored with diacritics stripped, so _quán cà phê_ becomes _quan ca phe_, mirroring how Vietnamese is often typed and supporting a robustness study without regenerating the dataset.

The sub-category lexicon preserves OSM tag granularity in Vietnamese: _restaurant_ expands to _nhà hàng món Việt_, _quán mì và phở_, _nhà hàng hải sản_, and further variants, with analogous entries for cafés, museums, and hospitals. All 26 sub-categories are non-empty in the address-bearing pool.

== Sample Records <sec:samples>

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
    [1601 #text(size: 0.85em, style: "italic")[(Wikipedia; not in the schema)]],
    table.hline(),
  ),
  caption: [Sample records spanning six templates and six answer types. Glosses are for the reader; the dataset is Vietnamese only. Location gold carries both a composed address and a geometry, scored by separate measures. The last row is a two-source question. Every question is also stored with diacritics removed (_Quan ca phe gan Nha tho Duc Ba..._).],
  placement: auto,
  scope: "parent",
) <tab:samples>

@tab:samples gives six example records, and @sec:appendix-prompts shows a complete stored record. Two details are worth drawing out. First, the anchor landmark is stored by OSM identifier alongside its name, so a question can be traced back to the exact map feature that generated it and regenerated if that feature changes. Second, the gold answer for an address question is not a string the generator wrote but the set of tags the database returned, with the readable form derived from them, which is what allows the canonical string to be recomputed and checked at verification time.

== Location Gold <sec:locgold>

GS-QA scores location answers on address text F1 and on a Nominatim-geocoded distance, but its gold address is a flat, U.S.-style string. Two properties of Vietnamese make that unsuitable. Addresses here are hierarchical and administratively ordered, so a flat string discards the structure the task is testing; and Nominatim's Vietnamese coverage is uneven, so a geocoded gold would bake the geocoder's errors into the benchmark. We therefore take gold directly from OSM `addr_*` tags, compose the canonical string deterministically, and confine the geocoder to the _prediction_ side.

A POI qualifies as address-bearing if it has a street or place name _and_ at least one broader locator, which yields 5,321 POIs. Coverage is very uneven: a street name is present on 13,857 POIs but `place` on 72 and `suburb` on 7, while district, city and province each cover roughly 4,500 to 4,800 and not the same ones, which is why the criterion accepts any of them. The alternatives are worse: street alone admits names that repeat across cities, requiring a house number drops the pool to 4,020, and a city name is not a point. The pool spans all three regions, led by Hà Nội (1,464), Bắc Ninh (643) and Ho Chi Minh City (roughly 552 across three OSM spellings).

Gold comprises `geo_wkt`, which drives the distance measure; the eight verbatim `addr_*` components with orthography frozen as OSM records it, including mixed forms such as _Bắc Ninh_ beside _Bac Ninh_; and one deterministic canonical string. Nearest gold is the closest address-bearing candidate; radius gold is the full distance-ordered set, median 2–6 and maximum 542.

== Distribution and Quality Control

Of the 2,800 questions, 1,200 expect the name of a place, 800 an address, and 200 each a compass direction, a count, and a distance, with 100 each for total area and total length.

Generation proceeds by sampling a landmark from a fixed seed, executing the template's query, validating the answer set, filling a Vietnamese phrasing, and writing the record, followed by a verifier pass.

Six gates guard the release: a database rebuild, a smoke run, full generation of all 2,800 questions, regenerating `diff -r`-clean, human review of five records per template, static checks on the runners, and a restore from the published release reproducing the original table counts. Every record is additionally checked for Unicode normalization, unreplaced placeholders, exclusion of the landmark from its own answer set, duplicates, well-formed gold SQL, and, on address questions, a geometry and an address whose canonical string recomputes from the stored components. Where GS-QA reviews 10% of its questions by hand, we verify 100% automatically and 5% by hand.

= Baselines <sec:method>

We evaluate two 9B-parameter open models, Ornith-1.5-9B @ornith2026 and Qwen3.5-9B @qwen35, both in the NVFP4 4-bit quantized format so that each fits on a single GPU, and both served through a vLLM inference server.

#figure(
  image("figures/fig1_baselines.svg", width: 90%),
  caption: [The two baselines. Direct tests what a model knows about Vietnamese geography; Text2SQL tests whether it can express a spatial question as a query. Each Text2SQL stage is stored separately, so a failure can be attributed to query generation, execution, or narration rather than to the pipeline as a whole.],
  placement: auto,
) <fig:baselines>

*Direct.* The question goes to the model and the answer comes back, with no database and no retrieval, shown at the top of @fig:baselines. This measures what the model has memorized about Vietnamese places, which is the condition an ordinary user meets when asking a chat assistant for directions.

*Text2SQL.* Three stages, shown beneath it. The model receives the schema and the question and writes SQL; PostgreSQL executes it against the same database that produced the gold answer; the model narrates the returned rows in Vietnamese. Using the identical database means a wrong answer is a reasoning or query-construction failure rather than a data mismatch. The three stages are stored separately, so failures localize to generation, execution or narration (@sec:discussion).

*Scope.* GS-QA evaluates three baseline families. We evaluate two, omitting dense-retrieval RAG for compute reasons. Our Text2SQL-versus-Direct gap is consequently a comparison over two options rather than three, and is not directly comparable to GS-QA's best-configuration result.

*Decoding.* One frozen profile across all four runs (temperature 1.0, top-$p$ 0.95, top-$k$ 20, presence penalty 1.5, seed 42, reasoning enabled), so differences between runs come from the model and the baseline rather than from sampling.

*Provenance.* Every run is sealed: a single checksum binds the model, the baseline, the dataset, the prompts and the raw outputs, so any result traces back to the exact inputs that produced it. Retries are structural only, meaning malformed JSON is retried and a well-formed but wrong answer never is.

== A Zero-LLM Rescue Intervention <sec:rescue>

Inspecting Text2SQL failures revealed a recoverable class: the SQL runs, returns usable typed rows, and the model still emits no answer, so the score sits at the unattempted floor although the correct value is present in the executed rows.

We therefore pre-register a zero-inference intervention on Ornith with Text2SQL. It fires only when a sealed run has no candidate answer at all, so answered questions are never touched and a per-question score can only improve or tie, which we assert after every evaluation. The executed rows are then re-emitted through the parser's own output shape: the first non-empty name column for entities, the address column or the canonical string rebuilt from `addr_*` for locations, and the corresponding typed column otherwise. Two-source questions are never rescued, since the database cannot hold their answer.

The intervention is deliberately dull: no model call, no retrieval, no prompt. Its effect isolates how much measured failure is a formatting gap rather than a reasoning gap.

= Experimental Setup <sec:setup>

Two models crossed with two baselines give four sealed runs and 11,200 predictions. Following GS-QA we apply Unicode NFKC normalization, case folding and punctuation separation while preserving diacritics, then compute token precision, recall and F1. These measure the overlap between the words a system produced and those in the gold answer, so a nearly-right place name scores partial credit rather than zero.

*Dev/test split.* To evaluate the intervention honestly we freeze a split before touching test data. Within each template, questions are ranked by the hash of a fixed salt and their identifier, and the first 20 of 100 go to dev, giving 560 dev and 2,240 test questions with no training split. The rule is deterministic and re-derivable, the sealed artifacts are read-only, and the intervention arm is scored by importing the evaluator verbatim. Baseline aggregates track each other closely across the halves: location distance error is 0.670 on dev against 0.643 on test.

*Parsing and geocoding.* A single model, Ornith-1.5-9B, parses every answer from both evaluated models and both baselines into a fixed schema under one frozen prompt, so no model parses its own output. Address answers are then scored on text F1 and, after geocoding with Nominatim, on distance from the gold geometry capped at 500 km, so 0.01 is five kilometres. Compass answers map to eight Vietnamese sectors scored by circular error over 180; numeric answers require finite values with units normalized and counts integral, with relative error capped at 1; radius questions are scored by best match over the full gold set. A question counts as _attempted_ when the parsed output carries the required field, matching GS-QA.

= Results <sec:results>

#figure(
  table(
    columns: (auto, auto, auto, auto, auto),
    stroke: none,
    align: (left, left, center, center, center),
    table.hline(),
    table.header([*Family*], [*Metric*], [*Base*], [*Rescue*], [$Delta$]),
    table.hline(stroke: 0.5pt),
    [entity], [F1 $arrow.t$], [0.278], [*0.440*], [$+$0.162],
    [location], [F1 $arrow.t$], [0.387], [0.436], [$+$0.049],
    [location], [dist $arrow.b$], [0.643], [0.589], [$-$0.055],
    [direction], [F1 $arrow.t$], [0.552], [0.571], [$+$0.019],
    [direction], [ang. $arrow.b$], [0.433], [0.414], [$-$0.019],
    [distance], [rel. $arrow.b$], [0.645], [*0.568*], [$-$0.078],
    [count], [rel. $arrow.b$], [0.570], [0.570], [$plus.minus$0.000],
    [area], [rel. $arrow.b$], [0.711], [0.711], [$plus.minus$0.000],
    [length], [rel. $arrow.b$], [0.675], [0.675], [$plus.minus$0.000],
    [two-source], [F1 $arrow.t$], [0.000], [0.000], [$plus.minus$0.000],
    table.hline(),
  ),
  caption: [Ornith with Text2SQL on the 2,240 test questions, before and after the zero-LLM intervention of @sec:rescue. Unattempted questions are included at the worst-case value. Area, length and two-source are unrescuable by construction: the database holds no typed aggregate for the first two and no answer at all for the third.],
  placement: auto,
) <tab:rescue>

*Text2SQL is the only viable architecture.* The gap is not one of degree. Direct refuses roughly 82% of Vietnamese geospatial questions, answering only 77 of 2,800 correctly, Refusals concentrate on entity questions, 904 of 1,100, and on locations, 572 of 800. Text2SQL engages every family. This replicates GS-QA's central English finding, where the best Text2SQL configuration reached 0.23 average F1 against 0.07 for bare prompting, and holds more sharply here: without database access a 9B model asked about Vietnamese places mostly declines to guess.

*A formatting gap, not only a reasoning gap.* The intervention recovers 222 of 2,240 test questions with zero regressions, lifting entity F1 by 0.162 and cutting distance relative error by 0.078 without a single model call. Every family that improved on dev improved on test with matching sign and magnitude, so the gain is no dev-split artifact: much of the apparent failure was a model retrieving the right rows and failing to say so.

*Two other results.* Two-source F1 is 0.000, the benchmark working as designed, since neither baseline can consult Wikipedia and the verifier guarantees the answer is absent from the schema. Compass error of 0.433 sits just below the 0.5 of random guessing.

= Error Analysis <sec:discussion>

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
      [two-source], [1], [35], [0], [7], [28], [29],
      table.hline(),
    )],
  caption: [Failure stage by family for Ornith with Text2SQL over all 2,800 questions. _Wrong_ means the model produced candidates and missed; _rescuable_ means usable rows existed but no answer was emitted; _unusable_ means rows existed with no typed value for the family. Two parse failures across the run are omitted.],
  placement: auto,
) <tab:taxonomy>

Every question is classified by the stage at which it failed, then flagged for Vietnamese phenomena. For Text2SQL the empty-candidate cases split by what the executed SQL did: errored, returned nothing, returned usable rows, or returned rows with no typed value for that family. @tab:taxonomy gives the counts.

*The expected Vietnamese failure mode does not occur.* We anticipated diacritic corruption in place names as a leading error class. It is not. Across a full run at most 9 predictions match gold only after stripping diacritics from both, because NFKC normalization already equates composed and decomposed forms. The character-level problem that motivates much Vietnamese NLP engineering is here solved by a line of Unicode handling. Compass vocabulary is likewise sound: only 14 answers name a sector inconsistent with the azimuth they state, so the weakness is in the azimuth, not the Vietnamese terms.

*Geocoding is the real language-specific friction.* Of the 471 location questions where Ornith with Text2SQL produced candidates, 219 contain a predicted address Nominatim cannot resolve, 46%. The comparable counts are 139 for Qwen with Text2SQL and 175 for Ornith with Direct. Vietnamese component order and postcode format diverge from what the geocoder expects. These questions still score through address text F1, but their spatial error is then governed by whatever the geocoder returns instead, which is why location distance error stays high even where the model named the right place.

*Where the rest sits.* SQL generation dominates: for entity questions 100 statements errored and 280 ran to no rows, the largest class being a subquery used as an expression while returning multiple rows, 107 of roughly 250 execution errors across the benchmark. Qwen generates markedly worse SQL, 209 entity errors against 100, while area and length fail at availability, with 34 and 43 cases where rows carried no aggregate the family needs.

= Limitations <sec:limitations>

Our scope is narrow by design: two of GS-QA's three baseline families, omitting retrieval-augmented generation, and two 9B models under a single decoding profile, so we make no claims at the level of model families. Our runs and GS-QA's English ones differ in models, region and snapshot, so we do not claim Vietnamese is harder. Per-family aggregates for three of four runs are pending, so cross-model comparisons rest on taxonomy counts.

The intervention recovers only the refusal floor: attempted-but-wrong answers and failed queries are untouched, and area, length and two-source questions cannot be rescued. Location rescue may emit an address formatted differently from gold while naming the same place, so the reported F1 gains understate spatial recovery, and the location metric inherits Nominatim's coverage of Vietnamese addresses.

The benchmark inherits its source. OpenStreetMap coverage of Vietnam is denser in Hà Nội and Ho Chi Minh City than in rural provinces, and tag reuse and mapper noise are present; we record these rather than patch them, since correcting crowd-sourced data would break reproducibility. The snapshot postdates Vietnam's July 2025 administrative reform @vnreform2025, so address tags reflect a re-tagging still in progress. OpenStreetMap data is ODbL and Wikipedia content CC-BY-SA, both requiring attribution, which the release provides; the generator excludes `building=residential`.

= Conclusion <sec:conclusion>

VN-GeoQA is the first reproducible Vietnamese geospatial QA benchmark: 2,800 SQL-grounded questions with native hierarchical address gold. Text2SQL is decisively right, since Direct refuses roughly 82% of questions, and a pre-registered zero-LLM intervention recovers 222 test questions without regressions. Diacritics prove solved by Unicode normalization; geocoding does not.

#bibliography("references.yaml")

#show: it => appendix(it, clearpage: false)

= The 28 Templates <sec:appendix-prompts>

Each template is a spatial predicate crossed with an answer type, and each is realized by several Vietnamese surface phrasings. @tab:templates gives the full inventory. Placeholders are `[1]` for the target category, `[2]` for the radius or the anchor, and `[3]` for a second anchor where the predicate needs one.

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
  caption: [One record from the released dataset, abridged. The gold address is composed from the eight native `addr_*` tags in a fixed order; `geo_wkt` is what the distance measure is computed against. Null components are kept rather than dropped, so the canonical string is always recomputable from what is stored.],
  kind: image,
  placement: auto,
) <fig:record>

== A stored record

@fig:record shows one complete record as released.

== Surface variation

Every template ships with several interchangeable phrasings, one of which is chosen at random per question. The complete set for `knn+name` (T01) is:

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

The prompt texts, the dataset manifest, and the reproduction recipe are included in the public release.

#figure(
  image("figures/fig3_pipeline.svg", width: 95%),
  caption: [Generation pipeline. Shaded stages reject rather than repair: a question that fails validation is discarded and the anchor resampled, so no partially-valid record reaches the release. Every stage is deterministic given the seed and the snapshot.],
  placement: auto,
) <fig:pipeline>

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
      [Có bao nhiêu `[1]` trong bán kính `[2]` từ `[3]`?],
      [T24],
      [`intersects+count`],
      [region overlap],
      [count],
      [Có bao nhiêu `[1]` ở `[2]`?],
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
  caption: [The 28 templates, grouped by answer type: entity name (T01--T12), address (T13--T20), and the numeric and directional types (T21--T28). One surface pattern is shown per template; the released files contain 128 in total.],
  placement: auto,
  scope: "parent",
) <tab:templates>
