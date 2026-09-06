#import "@preview/tracl:0.8.1": *
#import "@preview/pergamon:0.7.1": add-bib-resource, cite

#show: doc => acl(
  doc,
  anonymous: false,
  title: [VN-GeoQA: A Reproducible Vietnamese Geospatial Question Answering Benchmark],
  authors: make-authors(
    (
      name: ("Anh Pham-Ky", "Tien Dang-Anh", "Thuat Nguyen-Thien"),
      affiliation: [
        University of Science, VNU-HCM\
        Ho Chi Minh City, Vietnam\
        #email("{25C1503361, 25C1102267, 25C1502531}@student.hcmus.edu.vn")
      ],
    ),
  ),
)

#abstract[
  VN-GeoQA is a Vietnamese geospatial question answering benchmark: 2,800 questions across 28 templates generated from a pinned OpenStreetMap Vietnam snapshot against PostGIS, with SQL-computed answers and hierarchical address gold composed from native OpenStreetMap address components. We evaluate two 9B open models crossed with Direct and Text2SQL prompting under a frozen decoding profile. Direct prompting leaves 2,214 of 2,800 questions unattempted for Ornith-1.5-9B and 2,039 for Qwen3.5-9B. Text2SQL improves 9 of 10 reported per-family test metrics over Direct for each model, with two-source questions remaining at zero. A pre-registered intervention, Records-to-Answer Rescue, recovers 222 held-out test questions without regressions, increasing entity text F1 by 0.162 and decreasing distance relative error by 0.078. Address geocoding misses account for the most frequent tracked Vietnamese-specific evaluation flag (219 of 471 attempted location questions), whereas diacritic loss affects only 9 questions.
]

= Introduction <sec:intro>

When asked which café is nearest to Notre-Dame Cathedral (_"Quán cà phê nào gần Nhà thờ Đức Bà nhất?"_), language models tend to name a prominent city café rather than the nearest one. Geospatial QA remains rare among LLM benchmarks, with no prior Vietnamese resource (@sec:related). The language also differs structurally from English, inverting Western address ordering (_số nhà_ house number, _đường_ street, _phường/xã_ ward, _quận/huyện_ district, _tỉnh/thành phố_ province) with semantically contrastive tone marks, so address handling derived from English resources does not transfer. We port GS-QA's #cite("saeedan2026gsqa") construction methodology to Vietnam, inheriting its 28 templates, deterministic SQL-computed gold and spatial-aware evaluation, under SPARTQA's #cite("mirzaee2021spartqa") warrant that rule-based generation validated on a human-checked sample is a legitimate path to a language resource.

Our contributions are:
- *VN-GeoQA*: 2,800 questions regenerating deterministically from a fixed seed, pinned snapshot, and generator, released with evaluation artifacts and cache.
- Vietnamese adaptations: native `addr_*` location gold, 128 surface phrasings over 28 templates, 26 target categories, diacritic-stripped surfaces, and Unicode NFKC evaluation.
- Four sealed Ornith and Qwen runs across Direct and Text2SQL prompting, plus Records-to-Answer Rescue (`records-to-answer-rescue-v1`) on a frozen 560/2,240 split whose dev gains transfer to test without regressions.
- An error taxonomy across pipeline stages with Vietnamese-phenomenon flags: address geocoding misses are the most frequent tracked Vietnamese-specific evaluation flag, while diacritic loss affects few questions.

Code and dataset artifacts are publicly available at #link("https://github.com/itskyf/ViGSQA").

= Related Work <sec:related>

Prior geospatial QA resources are modest in scale: GeoQuestions201 #cite("punjani2018geoquestions201") (201 questions), GeoQuestions1089 #cite("kefalidis2023geoquestions") (1,089), GeoAnQu #cite("xu2020geoanqu") (429), and MapQA #cite("li2025mapqa") (3,154 over two U.S. regions). GS-QA #cite("saeedan2026gsqa"), which we port, replaces crowdsourced collection and knowledge-graph queries with generated SQL gold over PostGIS and adds two-source questions.

*Construction.* A _template_ is a question pattern paired with the database query that fills its blanks and computes the answer simultaneously, making gold correct by construction and recomputable whenever the map changes. GS-QA builds a PostGIS database from a February 2024 US OpenStreetMap extract, crosses five spatial relationships with eight answer types into 28 natural combinations, and keeps 100 questions per template, 10% reviewed by hand.

*Baselines and findings.* GS-QA crosses three LLMs with three strategies (bare prompting, Text2SQL, retrieval-augmented generation). Sonnet with Text2SQL reaches 0.23 average F1 against 0.07 bare, two-source questions fail almost completely, and compass questions sit near chance.

Vietnamese QA is active, but lacks geospatial benchmarks. UIT-ViQuAD #cite("nguyen2020uitviquad") established reading comprehension over Vietnamese Wikipedia, later extended to health #cite("thai2022vicov19qa") and spoken input #cite("minh2026visqa"). VIMQA #cite("le2022vimqa") introduces multi-hop reasoning, but its location answers are place names retrieved from text, not positions computed from geometry. ViText2SQL #cite("nguyen2020vitext2sql"), translating Spider #cite("yu2018spider") into Vietnamese, is the closest structural relative to our Text2SQL baseline, yet Spider databases contain no spatial operators.

Compared to prior Vietnamese QA benchmarks, the distinguishing property of VN-GeoQA is that answers are computed from PostGIS geometry rather than retrieved from text, over real OpenStreetMap data rather than synthetic scenes. Compared to GS-QA, which established this methodology for the United States, VN-GeoQA adapts the pipeline to Vietnam with hierarchical native-address gold, evaluates open NVFP4 models with a unified evaluation parser, and introduces Records-to-Answer Rescue.

= The VN-GeoQA Dataset <sec:dataset>

== Construction <sec:construction>

Every question is generated by a program and its answer computed by a database rather than typed by an annotator. We take a dated OpenStreetMap extract of Vietnam #cite("osm") and load it into PostGIS, which evaluates spatial predicates (distance, direction, and containment) directly. The database contains five tables covering 38,207 points of interest, administrative regions, parks, lakes, and roads. Each point carries its name, category, narrowing tags, coordinates, and up to eight native address fields (@sec:locgold).

Generation samples an anchor feature, instantiates the question template, and executes the associated query. The returned row is the gold answer. A candidate query whose answer set is empty, ambiguous, or contains the anchor itself is discarded, and a new anchor is sampled. This procedure is fully deterministic given the fixed seed and database snapshot (@fig:pipeline, @sec:appendix-pipeline). Two multi-source templates ask for external facts, such as the year a building opened. These attributes are confirmed absent from the database schema, with values sourced from a frozen Wikipedia snapshot.

The benchmark covers seven spatial question categories across 28 natural combinations of predicate and answer type (@tab:templates, @sec:appendix-templates), using schema `answer_type` identifiers `name`, `loc`, `angle`, `count`, `distance`, `area`, and `length`. The 2,800 questions comprise 1,100 entity names, 800 locations, 200 compass directions, 200 counts, 200 distances, 100 areas, 100 lengths, and 100 two-source facts (`external`). Spatial reasoning over metric range and bearing is illustrated in @fig:spatial-reasoning (@sec:appendix-spatial). Representative examples appear in @tab:samples (@sec:appendix-samples).

Each template provides multiple Vietnamese surface variations (128 total across 28 templates), preventing models from overfitting to a single question syntax. Questions are also paired with diacritic-stripped forms (for example, _quan ca phe_ for _quán cà phê_). Target categories preserve OpenStreetMap tag granularity across 26 sub-categories, expanded through a Vietnamese label lexicon.

== Location Gold <sec:locgold>

GS-QA evaluates location predictions using address text F1 and Nominatim-geocoded distance against a flat, U.S.-style gold string. Vietnamese addresses follow a strict administrative hierarchy, from specific street numbers to broader provincial units. A flat gold string loses this structural constraint, and relying on Nominatim to produce gold coordinates would incorporate geocoder errors into the benchmark reference. We therefore compose gold addresses deterministically from native OpenStreetMap `addr_*` tags and restrict geocoding to the prediction side.

A point of interest qualifies as address-bearing if it has a street or place name and at least one broader administrative component, yielding 5,321 eligible locations. Because tag density varies across administrative levels in OpenStreetMap, the criterion accepts any valid broader locator. Location gold records `geo_wkt` (the authoritative spatial reference), eight native `addr_*` fields, and the canonical composed address string. Radius questions provide the complete distance-ordered set of gold locations.

*Quality control.* Generation includes automated verification over all 2,800 records, checking schema conformance, landmark exclusion, duplicate avoidance, and SQL validity. In addition, a 5% stratified sample across all templates was manually audited for semantic correctness.

= Methods <sec:method>

== Relation to GS-QA <sec:relation-gsqa>

ViGSQA builds directly on GS-QA #cite("saeedan2026gsqa"), inheriting its 28 template families, its Direct and Text2SQL baseline structures, and its spatial-aware metric families. We adapt the benchmark to a dated Vietnam OpenStreetMap snapshot with 128 Vietnamese surface phrasings, construct native-address gold from local `addr_*` components, evaluate 4-bit NVFP4 model configurations, employ Ornith as a unified evaluation parser rather than Qwen 3.5, incorporate Vietnamese NFKC normalization, and omit the upstream RAG baseline. The new contributions in this project are the validated VN-GeoQA benchmark instance, the pre-registered Records-to-Answer Rescue method, a Vietnamese-specific failure analysis, and a fresh Vietnamese demo.

== Baselines <sec:baselines>

We evaluate two 9B open models: Ornith-1.5-9B-NVFP4 #cite("ornith2026") and Qwen3.5-9B-NVFP4 #cite("qwen35") (shortened to Ornith and Qwen in later discussions), both 4-bit NVFP4 quantized and served via vLLM #cite("kwon2023vllm").

*Direct.* In Direct (the GS-QA bare-LLM baseline), the question is provided directly to the model to generate a free-text response without database access or external retrieval. This tests parametric knowledge of Vietnamese geography.

*Text2SQL.* Text2SQL follows a three-stage pipeline adapted from GS-QA (@fig:baselines, @sec:appendix-baselines). The model receives the database schema and question, then outputs an SQL query. PostgreSQL executes the query against PostGIS, and the model narrates the returned rows into a Vietnamese answer. Model errors may originate across query generation, execution, narration, structured parsing, or candidate geocoding.

*Inference configuration.* Both models use a frozen decoding configuration (temperature 1.0, top-$p$ 0.95, top-$k$ 20, seed 42, reasoning enabled). All prompt templates and raw outputs are sealed to guarantee reproducible evaluation.

== Records-to-Answer Rescue <sec:rescue>

Analysis of Text2SQL outputs revealed a distinct failure mode: the generated SQL executes successfully and returns usable database rows, yet narration produces an unattempted or unparseable answer. We introduce Records-to-Answer Rescue (`records-to-answer-rescue-v1`) for Text2SQL. When narration fails to emit a valid answer candidate, Records-to-Answer Rescue converts the returned typed rows directly into the evaluator's JSON candidate schema: the primary name attribute for entities, the composed address string for locations, and the corresponding numeric fields for distance and direction.

The rescue intervention fires strictly when the sealed baseline run produced no valid candidate answer. Existing candidate answers are never modified, ensuring that per-question scores can only improve or tie. The method requires no additional model inference, prompt adjustment, or external retrieval.

= Experimental Setup <sec:setup>

== Evaluation Protocol <sec:protocol>

The four evaluated runs cross the two models (Ornith and Qwen) with Direct and Text2SQL prompting, yielding 11,200 total responses. All free-text answers are extracted into a structured JSON schema using Ornith as a common, frozen scoring parser across all runs. Predicted addresses are geocoded using Nominatim #cite("nominatim") under its bulk-use rate limit (1 request per second). We also evaluate a five-question fresh Vietnamese demo on landmarks absent from the benchmark surfaces (@sec:appendix-demo).

*Dev/test split.* Within each template, questions are partitioned into 20 dev and 80 test instances via fixed identifier hashing, yielding 560 dev and 2,240 test questions. The Records-to-Answer Rescue intervention was pre-registered on dev data alone before evaluating on the held-out test split. Baseline aggregates align closely across splits (for example, location distance error is 0.670 on dev and 0.643 on test for Ornith with Text2SQL).

== Metrics <sec:metrics>

Text answers are normalized via Unicode NFKC, case folding, and punctuation-to-space mapping, collapsing consecutive whitespace while preserving Vietnamese diacritics (for example, #text[“Quán Cà-phê!”] $arrow.r$ #text[“quán cà phê”]). For prediction tokens $p$ and gold tokens $g$ counted with multiset multiplicity, precision, recall, and token $F_1$ are:
$
  P = frac(|p inter g|, |p|), quad R = frac(|p inter g|, |g|), quad F_1 = frac(2 P R, P + R).
$
Higher scores are better on $[0, 1]$. Numeric answers (count, distance, area, length) are normalized to standard units (metres, square metres, integers) and evaluated using capped relative error matching the canonical evaluator:
$
  E_"rel"(hat(y), y) = cases(
    0 & "if" hat(y) = y,
    min(frac(|hat(y) - y|, |y|), 1) & "if" y != 0,
    1 & "otherwise."
  )
$
Direction predictions are evaluated by circular error over the azimuth angle and token $F_1$ across eight Vietnamese compass sectors (e.g. _bắc_ north, _đông nam_ southeast). Location predictions are evaluated by address token $F_1$ and geodesic distance $d$ from the geocoded prediction to the gold point centroid:
$
  E_"circ"(hat(a), a) & = frac(|((hat(a) - a + 180) mod 360) - 180|, 180), \
           E_"geo"(d) & = min(frac(d, "500 km"), 1).
$
When multiple prediction or gold candidates are present, scoring selects the best matching pair. A question is classified as _attempted_ when parsing yields at least one candidate. Unattempted questions receive worst-case scores ($F_1 = 0$, $E = 1$). In diagnostic analysis, questions are marked _correct_ if they satisfy primary thresholds ($F_1 >= 0.5$ or $E <= 0.1$). Direct questions where parsing succeeds but no candidate is emitted are classified as _refused_.

= Results and Discussion <sec:results>

== Baseline Comparison <sec:results-baselines>

#figure(
  table(
    columns: (26mm, 15mm, 21mm, 18mm),
    inset: (x: 2.5pt, y: 3pt),
    stroke: none,
    align: (left, left, right, right),
    table.hline(),
    table.header([*Model*], [*Method*], [*Attempted*], [*Correct*]),
    table.hline(stroke: 0.5pt),
    [Ornith], [Direct], [20.9%], [2.8%],
    [Ornith], [Text2SQL], [*54.2%*], [*32.4%*],
    [Qwen], [Direct], [27.2%], [2.8%],
    [Qwen], [Text2SQL], [51.5%], [29.3%],
    table.hline(),
  ),
  caption: [Baseline comparison across the full benchmark (2,800 questions). _Attempted_ indicates at least one parsed candidate. _Correct_ indicates satisfaction of primary evaluation thresholds ($F_1 >= 0.5$ or $E <= 0.1$). Bold marks the best result per column.],
) <tab:baselines>

As shown in @tab:baselines, database grounding dictates baseline performance. Without database access, both models decline most questions: Ornith leaves 2,214 of 2,800 questions unattempted (79.1%, with 2,213 explicit refusals, mainly on entity and location questions), while Qwen leaves 2,039 unattempted (72.8%) at the same 2.8% correct rate.

Text2SQL improves 9 of the 10 reported per-family test metrics over Direct for both models. Two-source questions (`textual_fact`) score zero across all runs: in Text2SQL, external infobox facts are excluded from the database schema without external retrieval, while Direct prompting fails to recall them from parametric weights. In count relative error, Qwen with Text2SQL achieves 0.554 on the held-out test split, outperforming Ornith (0.570) because lower error is better.

== Records-to-Answer Rescue <sec:results-rescue>

#figure(
  table(
    columns: (18mm, 23mm, 10mm, 16mm, 13mm),
    inset: (x: 2.5pt, y: 3pt),
    stroke: none,
    align: (left, left, right, right, right),
    table.hline(),
    table.header([*Family*], [*Metric*], [*Base*], [*Rescue*], [*$Delta$*]),
    table.hline(stroke: 0.5pt),
    [entity], [Text $F_1 arrow.t$], [0.278], [0.440], [$+0.162$],
    [location], [Text $F_1 arrow.t$], [0.387], [0.436], [$+0.049$],
    [], [Dist. err $arrow.b$], [0.643], [0.589], [$-0.055$],
    [direction], [Text $F_1 arrow.t$], [0.552], [0.571], [$+0.019$],
    [], [Angle err $arrow.b$], [0.433], [0.414], [$-0.019$],
    [distance], [Rel. err $arrow.b$], [0.645], [0.568], [$-0.078$],
    table.hline(),
  ),
  caption: [Records-to-Answer Rescue effect on the held-out test split (2,240 questions) for Ornith with Text2SQL. Only families with non-zero change are shown. Unchanged families yield no rescue candidates.],
) <tab:rescue>

On the held-out test split (2,240 questions), Records-to-Answer Rescue recovers 222 previously unattempted questions with zero regressions (@tab:rescue): 165 entity names, 35 locations, 19 distances, and 3 directions. Entity text $F_1$ improves by 0.162, and distance relative error drops by 0.078 without any model inference.

Four families remain unchanged on the test split. Count queries leave zero unattempted rows. Area and length narration failures return rows lacking the requested aggregate column, precluding recovery. Multi-source facts reside outside the database schema.

= Error Analysis <sec:errors>

The error taxonomy categorizes each question in the Ornith/Text2SQL run by its pipeline termination stage (@tab:taxonomy, @sec:appendix-taxonomy).

*Vietnamese-specific phenomena.* Diacritic loss is rare: across the entire 2,800-question run, only 9 attempted entity and textual-fact questions fail initial scoring but reach token $F_1 >= 0.5$ after diacritic stripping. Unicode NFKC normalizes composed and decomposed forms, and the low rate of diacritic loss reflects empirical model generation. In compass questions, only 14 answers exhibit `sector_right_angle_wrong`, reflecting an evaluation resolution mismatch: the predicted compass sector matches gold ($F_1 >= 0.5$), but continuous angular error exceeds the error threshold ($E > 0.1$).

*Address geocoding.* Geocoding misses represent the most frequent tracked Vietnamese-specific evaluation flag. Among 471 location questions where Ornith with Text2SQL produced candidates, 219 (46.5%) contain an address not found or rejected by Nominatim (versus 139 for Qwen/Text2SQL and 175 for Ornith/Direct). While scored on address text $F_1$, unresolved addresses incur the maximum geographic distance penalty.

*Pipeline stages.* SQL execution errors account for 274 failures in Ornith with Text2SQL (including 100 on entity questions) and 591 in Qwen with Text2SQL. An additional 543 queries return no rows, while 178 return rows lacking the requested attribute type.

= Limitations <sec:limitations>

We evaluate two 9B open models under Direct and Text2SQL prompting with a single decoding profile, without proprietary frontier models or dense RAG architectures. Records-to-Answer Rescue recovers only unattempted questions with successful SQL execution, leaving syntax errors and wrong candidates unaddressed.

The benchmark inherits OpenStreetMap density variations between urban centres and rural provinces, and its snapshot captures transitional tagging following administrative reorganization #cite("vnreform2025"). Location evaluation is bounded by Nominatim's public geocoding coverage.

= Ethical Considerations <sec:ethics>

VN-GeoQA is derived from OpenStreetMap data under the Open Database License (ODbL) and Wikipedia infobox data under CC-BY-SA. The benchmark excludes personal data and residential buildings. Nominatim is used strictly within its public service usage policies. Model outputs are preserved verbatim to support error analysis and reproducible benchmarking.

= Conclusion <sec:conclusion>

VN-GeoQA establishes a reproducible Vietnamese geospatial QA benchmark with deterministic PostGIS answers and hierarchical address gold. Database-grounded Text2SQL outperforms Direct prompting across 9 of 10 per-family metrics. Pre-registered Records-to-Answer Rescue recovers 222 test questions with zero regressions, showing that formatting limitations contribute meaningfully to baseline failures. Address geocoding misses form the primary Vietnamese-specific evaluation flag, while diacritic loss remains minimal.

#add-bib-resource(read("references.bib"))
#print-acl-bibliography()

#show: it => appendix(it, clearpage: true)

= Sample Records <sec:appendix-samples>

@tab:samples presents sample records from the released VN-GeoQA dataset across six question types. Each record links the question, canonical template identifier, answer type, and gold reference. Location gold pairs an address string with a WGS84 point geometry, scored through separate text and spatial metrics. Two-source questions incorporate external facts from Wikipedia infoboxes.

#figure(
  [
    #set text(size: 8.5pt)
    #table(
      columns: (2.8cm, 1fr, 2.0cm, 4.4cm),
      inset: (x: 3pt, y: 2pt),
      stroke: none,
      align: (left, left, left, left),
      table.hline(),
      table.header(
        [*Task & Template*],
        [*Question (Vietnamese, with gloss)*],
        [*Type*],
        [*Gold answer*],
      ),
      table.hline(stroke: 0.5pt),
      [Nearest entity\ (`knn+name`, T05)],
      [phòng trưng bày gần Nhà Hàng Âu Lạc Brazil II, Hà Nội nhất có tên là gì?\ #text(size: 0.85em, style: "italic")[Nearest art gallery to Nhà Hàng Âu Lạc Brazil II, Hanoi?]],
      [name],
      [Lunet Art Galerie],
      [Radius count\ (`range+count`, T23)],
      [Trong phạm vi 20 km từ Nhà Hàng Lối Xưa có bao nhiêu bệnh viện?\ #text(size: 0.85em, style: "italic")[How many hospitals within 20 km of Nhà Hàng Lối Xưa?]],
      [count],
      [38],
      [Nearest location\ (`knn+loc`, T17)],
      [Cho tôi biết vị trí siêu thị gần Hong Thien 2 hotel nhất.\ #text(size: 0.85em, style: "italic")[Where is the supermarket nearest to Hong Thien 2 hotel?]],
      [loc],
      [19 Trần Hưng Đạo, Phú Xuân, Huế, Thừa Thiên Huế, 49000\ #raw("POINT(107.5841 16.4678)", lang: "txt")],
      [Distance\ (`knn+distance`, T26)],
      [Khoảng cách từ GachDo Coffee tới ngân hàng gần nhất là bao nhiêu?\ #text(size: 0.85em, style: "italic")[Distance from GachDo Coffee to the nearest bank?]],
      [distance],
      [229.57 m],
      [Direction\ (`knn+angle`, T22)],
      [Góc phương vị từ Pizza Hut, Hà Nội đến nhà thuốc gần nhất là bao nhiêu?\ #text(size: 0.85em, style: "italic")[Azimuth angle from Pizza Hut, Hanoi to the nearest pharmacy?]],
      [angle],
      [103.4° (đông nam)],
      [Two-source fact\ (`knn+name+`\ `multi_source1`, T07)],
      [trường đại học gần SHB nhất được thành lập vào năm nào?\ #text(size: 0.85em, style: "italic")[Year the university nearest to SHB was founded?]],
      [external],
      [2009 #text(size: 0.85em, style: "italic")[(Wikipedia infobox)]],
      table.hline(),
    )
  ],
  caption: [Sample records from the released VN-GeoQA dataset spanning six templates and answer types. Glosses are provided for readability. Released questions are in Vietnamese. Location gold carries both a composed address and point geometry. The Type column shows the raw schema identifier (name, loc, angle, count, distance, external) corresponding to the evaluated family. The final row is a two-source question drawn from Wikipedia.],
  placement: top,
  scope: "parent",
) <tab:samples>

== Spatial Reasoning Visualization <sec:appendix-spatial>

@fig:spatial-reasoning visualizes the search geometry for template T16 in projected coordinates (UTM 48N).

#figure(
  image("figures/spatial_reasoning_example.svg", width: 80%),
  caption: [Spatial reasoning geometry for template T16 (`range:towards+loc-035`), answering #"“"Những công viên cách Trường Mầm Non Sen Hồng không quá 3 km theo hướng Thuốc Tây Minh Hạnh nằm ở đâu?#"”". Anchor POI (black square), towards reference (orange triangle), search sector ($plus.minus 22.5 degree$), range limit arc (dashed), and gold locations (blue circles) are shown in UTM 48N. Map: © OpenStreetMap contributors.],
  placement: bottom,
  scope: "parent",
) <fig:spatial-reasoning>

== Stored Record Schema <sec:appendix-record>

#figure(
  [
    #show raw: set text(size: 6.2pt)
    ```json
    {
      "id": "knn+loc-014", "tid": "T17", "type": "knn+loc", "answer_type": "loc",
      "question": "Cho tôi biết vị trí siêu thị gần Hong Thien 2 hotel nhất.",
      "question_surfaces": {
        "full":     "Cho tôi biết vị trí siêu thị gần Hong Thien 2 hotel nhất.",
        "stripped": "Cho toi biet vi tri sieu thi gan Hong Thien 2 hotel nhat."
      },
      "sql": "SELECT id, geo_wkt, poi_name, addr_* FROM pois WHERE id <> 668713429 AND shop ILIKE 'supermarket' AND poi_name IS NOT NULL AND ((addr_street IS NOT NULL OR addr_place IS NOT NULL) AND ...) ORDER BY geometry <-> $anchor LIMIT 1;",
      "answers": [{
        "id": 12546999774, "poi_name": "Urban Go", "geo_wkt": "POINT(107.5841 16.4678)",
        "address": "19 Trần Hưng Đạo, Phú Xuân, Huế, Thừa Thiên Huế, 49000",
        "addr_housenumber": "19", "addr_street": "Trần Hưng Đạo", "addr_district": "Phú Xuân",
        "addr_city": "Huế", "addr_province": "Thừa Thiên Huế", "addr_postcode": "49000"
      }],
      "question_entities": {
        "[1]": {"main_category": "shop", "sub_category": "supermarket"},
        "[2]": {"id": 668713429, "name": "Hong Thien 2 hotel", "geo_wkt": "POINT(107.5961 16.4691)"}
      }
    }
    ```
  ],
  caption: [One verified record (`knn+loc-014`) from the released dataset, abridged for presentation. Address components are preserved in native OSM fields and composed into a canonical address string. `geo_wkt` provides spatial coordinates.],
  kind: image,
  placement: none,
) <fig:record>

== Generation Pipeline <sec:appendix-pipeline>

#figure(
  image("figures/fig3_pipeline.svg", width: 92%),
  caption: [Generation pipeline. Validation stages reject and resample invalid candidates, ensuring that every released record satisfies structural and spatial constraints deterministically.],
  placement: none,
) <fig:pipeline>

== Surface Variation <sec:appendix-surfaces>

Each template provides multiple interchangeable Vietnamese phrasings, selected randomly during benchmark generation. The phrasing variations for `knn+name` (T05) are shown below:

```
[1] nào gần [2] nhất?
[1] gần nhất với [2] là gì?
Cho tôi biết [1] gần [2] nhất.
Đâu là [1] gần [2] nhất?
Tìm giúp tôi [1] gần [2] nhất.
[1] gần [2] nhất có tên là gì?
Tôi đang tìm [1] gần [2] nhất.
```

The phrasings vary in tone and structure (interrogative vs. request). Across all 28 templates, the benchmark defines 128 distinct phrasings.

= Baseline Architectures <sec:appendix-baselines>

#figure(
  image("figures/fig1_baselines.svg", width: 85%),
  caption: [Baseline architectures adapted and simplified from GS-QA #cite("saeedan2026gsqa"). Direct (top) queries the model without database access. Text2SQL (bottom) generates SQL, executes against PostgreSQL/PostGIS, and narrates the returned rows into a Vietnamese answer.],
) <fig:baselines>

= The 28 Templates <sec:appendix-templates>

Each template pairs a spatial predicate with an answer type and is realized through multiple Vietnamese surface patterns (@tab:templates). Placeholders denote target category `[1]`, anchor `[2]`, and secondary spatial reference `[3]` or `[4]`.

#figure(
  table(
    columns: (1.0cm, 4.6cm, 3.4cm, 2.3cm, 1fr),
    inset: (x: 3pt, y: 2.5pt),
    stroke: none,
    align: (left, left, left, left, left),
    table.hline(),
    table.header(
      [*ID*],
      [*Template*],
      [*Spatial predicate*],
      [*Dataset*\ *answer_type*],
      [*Vietnamese surface pattern*],
    ),
    table.hline(stroke: 0.5pt),
    [T01],
    [range+name],
    [within radius],
    [name],
    ["[1] nào nằm trong bán kính [2] quanh [3]?"],
    [T02],
    [range:non_spat_filter+name],
    [radius + non-spatial],
    [name],
    ["[1] nào trong bán kính [2] quanh [3]?"],
    [T03],
    [range:direction+name],
    [radius + compass],
    [name],
    ["[1] nào ở phía [4] [3] trong phạm vi [2]?"],
    [T04],
    [range:towards+name],
    [radius + towards],
    [name],
    ["[1] nào trong bán kính [2] quanh [3] nằm về hướng [4]?"],
    [T05], [knn+name], [nearest neighbour], [name], ["[1] nào gần [2] nhất?"],
    [T06],
    [knn:non_spat_filter+name],
    [nearest + non-spatial],
    [name],
    ["[1] nào gần [2] nhất?"],
    [T07],
    [knn+name+multi_source1],
    [nearest + external],
    [external],
    ["[1] nào gần [2] nhất? (Wikipedia fact)"],
    [T08],
    [knn+name+multi_source2],
    [nearest + external],
    [name],
    ["[1] nào gần [2] nhất? (external anchor)"],
    [T09],
    [knn:direction+name],
    [nearest + compass],
    [name],
    ["[1] nào ở phía [3] [2] và gần [2] nhất?"],
    [T10],
    [knn:towards+name],
    [nearest + towards],
    [name],
    ["[1] nào gần [2] nhất và nằm về hướng [3]?"],
    [T11],
    [intersects:area_max+name],
    [region overlap],
    [name],
    ["[1] nào lớn nhất ở [2]?"],
    [T12],
    [intersects:length_max+name],
    [region overlap],
    [name],
    ["[1] nào dài nhất đi qua [2]?"],
    [T13],
    [range+loc],
    [within radius],
    [loc],
    ["Các [1] trong bán kính [2] quanh [3] nằm ở đâu?"],
    [T14],
    [range:non_spat_filter+loc],
    [radius + non-spatial],
    [loc],
    ["Các [1] trong bán kính [2] quanh [3] nằm ở đâu?"],
    [T15],
    [range:direction+loc],
    [radius + compass],
    [loc],
    ["Các [1] ở phía [4] [3] trong phạm vi [2] nằm ở đâu?"],
    [T16],
    [range:towards+loc],
    [radius + towards],
    [loc],
    ["Trong bán kính [2] quanh [3], các [1] về hướng [4] nằm ở đâu?"],
    [T17],
    [knn+loc],
    [nearest neighbour],
    [loc],
    ["[1] gần [2] nhất nằm ở đâu?"],
    [T18],
    [knn:non_spat_filter+loc],
    [nearest + non-spatial],
    [loc],
    ["[1] gần [2] nhất nằm ở đâu?"],
    [T19],
    [knn:direction+loc],
    [nearest + compass],
    [loc],
    ["[1] gần nhất phía [3] của [2] nằm ở đâu?"],
    [T20],
    [knn:towards+loc],
    [nearest + towards],
    [loc],
    ["[1] gần [2] nhất về hướng [3] nằm ở đâu?"],
    [T21],
    [range+angle],
    [within radius],
    [angle],
    ["Các [1] trong bán kính [2] quanh [3] nằm ở hướng bao nhiêu độ?"],
    [T22],
    [knn+angle],
    [nearest neighbour],
    [angle],
    ["[1] gần [2] nhất nằm ở hướng bao nhiêu độ?"],
    [T23],
    [range+count],
    [within radius],
    [count],
    ["Có bao nhiêu [1] trong bán kính [2] quanh [3]?"],
    [T24],
    [intersects+count],
    [region overlap],
    [count],
    ["Có bao nhiêu [1] ở [2]?"],
    [T25],
    [range+distance],
    [within radius],
    [distance],
    ["Các [1] trong bán kính [2] quanh [3] cách [3] bao xa?"],
    [T26],
    [knn+distance],
    [nearest neighbour],
    [distance],
    ["[1] gần [2] nhất cách bao xa?"],
    [T27],
    [intersects:area_total+area],
    [region overlap],
    [area],
    ["Tổng diện tích các [1] ở [2] là bao nhiêu?"],
    [T28],
    [intersects:length_total+length],
    [region overlap],
    [length],
    ["Tổng chiều dài các [1] đi qua [2] là bao nhiêu?"],
    table.hline(),
  ),
  caption: [The 28 templates defined in the benchmark manifest, grouped by predicate and answer type: entity name (T01--T12), address (T13--T20), and numeric or directional types (T21--T28). A representative surface pattern is shown per template. Across the benchmark, 128 phrasings are released in total.],
  placement: auto,
  scope: "parent",
) <tab:templates>

#pagebreak()

= Error Taxonomy Details <sec:appendix-taxonomy>

The full 2,800-question run of Ornith-1.5-9B with Text2SQL is partitioned across pipeline termination stages in @tab:taxonomy.

#figure(
  table(
    columns: (22mm, auto, auto, auto, auto, auto, auto),
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
  ),
  caption: [Failure stage by family for Ornith-1.5-9B with Text2SQL across all 2,800 benchmark questions. _Wrong_ denotes candidate generation with primary metric failure. _Rescuable_ denotes usable rows without emitted candidate. _Unusable_ denotes rows lacking required typed columns. Two parse failures across the run are omitted.],
  placement: none,
) <tab:taxonomy>

= Fresh Vietnamese Demo <sec:appendix-demo>

To evaluate end-to-end performance on fresh entities, the notebook tests five Vietnamese questions whose anchor landmarks do not appear in benchmark surfaces (@tab:demo). Released model generations are replayed from step records, while question construction, gold SQL, PostGIS execution, rescue, and rendering are recomputed live.

#figure(
  table(
    columns: (1.8cm, 4.8cm, 3.8cm, 1fr),
    inset: (x: 3pt, y: 3pt),
    stroke: none,
    align: (left, left, left, left),
    table.hline(),
    table.header(
      [*Family*],
      [*Question (Vietnamese)*],
      [*Qualitative outcome*],
      [*Analysis note*],
    ),
    table.hline(stroke: 0.5pt),
    [entity],
    [nhà thuốc gần Phở Số 1 Hà Nội nhất là gì?],
    [Direct refused\ Text2SQL correct\ Rescue recovered],
    [Direct declines without maps. Text2SQL generates valid KNN spatial join returning Pharmacity.],
    [location],
    [Vị trí của khách sạn gần LPBank nhất là gì?],
    [Direct refused\ Text2SQL wrong hotel\ Rescue structured],
    [Text2SQL executes valid spatial query but identifies a different hotel candidate than gold.],
    [count],
    [Có bao nhiêu cây xăng trong bán kính 5 km quanh Basic school?],
    [Direct refused\ Text2SQL correct\ Rescue recovered],
    [Direct declines. Text2SQL executes `ST_DWithin` returning 0, matching gold count.],
    [distance],
    [Từ Nhà Hàng Chay Phương Nam đến phòng khám gần nhất bao xa?],
    [Direct refused\ Text2SQL rounded\ Rescue exact],
    [Direct declines. Text2SQL returns 429 m. Rescue extracts exact 429.29 m float from rows.],
    [direction],
    [Cho tôi biết góc phương vị của các quán cà phê cách Khách Sạn Đức Thái không quá 3 km.],
    [Direct formula only\ Text2SQL partial list\ Rescue recovered],
    [Direct outputs azimuth formula. Text2SQL lists angles. Rescue extracts first returned azimuth.],
    table.hline(),
  ),
  caption: [Five-question fresh Vietnamese demo evaluating landmarks absent from the benchmark surfaces. Direct prompting refuses all five questions. Text2SQL executes valid PostGIS queries across all five, and Records-to-Answer Rescue successfully extracts structured typed fields from returned execution rows.],
  placement: auto,
  scope: "parent",
) <tab:demo>
