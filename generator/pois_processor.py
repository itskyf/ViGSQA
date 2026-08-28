# %%
import json
from glob import glob

import psycopg2
from shapely.geometry import shape

# %%
# pois = json.loads(
#     open(
#         "/home/mrash013/spatial_llm/data/osm21_pois_California_USA.geojson", "r"
#     ).read()
# )['features']
pois_files = glob("./osm_extract/pois/*.geojson")


# %%
type_map = {
    str: "string",
    int: "integer",
    float: "float",
    type({"abc": 231}): "string",
}

# Schema filter: keep tags present in at least this fraction of features.
TAG_MIN_RATIO = 0.8


def define_schema(features, useTags=True):
    aggregate_schema = {}
    for i in range(len(features)):
        tags = (
            features[i]["properties"]["tagsMap"]
            if useTags
            else features[i]["properties"]
        )
        for k in tags:
            # if 'wiki' in k or 'addr' in k or 'gnis' in k or 'source' in k or ':' in k:
            #     continue
            aggregate_schema[k] = aggregate_schema.get(k, 0) + 1
    filtered_schema = {
        k: aggregate_schema[k]
        for k in aggregate_schema
        if (aggregate_schema[k] / len(features) > TAG_MIN_RATIO or not useTags)
    }
    final_schema = {"geometry": {"type": "string", "coordinates": "array[double]"}}
    for i in range(len(features)):
        tags = (
            features[i]["properties"]["tagsMap"]
            if useTags
            else features[i]["properties"]
        )
        for k in tags:
            if k not in filtered_schema:
                continue
            final_schema[k] = type_map[type(tags[k])]
        if len(final_schema) == len(filtered_schema) + 1:
            break
    return final_schema


def schema_to_sql(schema, table_name):
    columns = ""
    type_map = {"string": "VARCHAR(255)", "integer": "BIGINT", "float": "DOUBLE"}
    for k in schema:
        if k != "geometry":
            columns += f"        {k} {type_map[schema[k]]},\n"
    columns = columns[:-2]
    "customer_name VARCHAR(255) NOT NULL"
    create_table = f"""
    DROP TABLE IF EXISTS {table_name} CASCADE;
    CREATE TABLE {table_name} (
        id SERIAL PRIMARY KEY,
        geometry GEOGRAPHY(GEOMETRY, 4326),\n{columns}
    );
    """
    return create_table


def run_sql(sql):
    conn = psycopg2.connect(
        host="localhost",
        dbname="osm_ca",
        user="postgres",
        password="postgres",
        port=5432,
    )
    cur = conn.cursor()
    cur.execute(sql)
    conn.commit()
    cur.close()
    conn.close()


def insert_rows_sql(table_name, schema, features, useTags=True):
    columns = []
    for k in schema:
        if k != "geometry":
            columns.append(k)
    values = ""
    for f in features:
        if "name" in f["properties"]["tagsMap"]:
            f["properties"]["tagsMap"]["poi_name"] = f["properties"]["tagsMap"]["name"]
        f["properties"]["tagsMap"]["osm_id"] = f["properties"]["id"]
        value = f"\n        ('{shape(f['geometry']).wkt}'"
        tags = f["properties"]["tagsMap"] if useTags else f["properties"]
        for c in columns:
            _c = c.replace("_", ":") if "addr_" in c else c
            if _c in tags:
                if schema[c] == "string":
                    tag = str(tags[_c]).replace("'", "''")
                    value += f",'{tag}'"
                else:
                    value += f",{tags[_c]!s}"
            else:
                value += ",NULL"
        value += "),"
        values += value
    values = values[:-1]
    columns = "geometry," + ",".join(columns)
    # Trailing space after ({columns}) mirrors the original template byte-for-byte.
    query = f"\n    INSERT INTO {table_name} ({columns}) \n    VALUES{values};\n    "
    return query


# %%
pois = []
for f in pois_files:
    pois += json.loads(open(f).read())["features"]
    print(len(pois))

# %%
schema = json.loads(open("poi_schema.json").read())

selected_tourism = [
    "aquarium",
    "attraction",
    "viewpoint",
    "art_gallery",
    "theme_park",
    "museum",
    "bed_and_breakfast",
    "gallery",
    "zoo",
    "hotel",
]
selected_amenities = [
    "restaurant",
    "hospital",
    "university",
    "food",
    "fast_food",
    "coffee",
    "cafe",
]
selected_leisure = [
    "park",
    "beach_resort",
    "golf_course",
    "nature_reserve",
    "garden",
    "stadium",
]

tourism_features = [
    p
    for p in pois
    if "tourism" in p["properties"]["tagsMap"]
    and p["properties"]["tagsMap"]["tourism"] in selected_tourism
    and "name" in p["properties"]["tagsMap"]
]
amenties_features = [
    p
    for p in pois
    if "amenity" in p["properties"]["tagsMap"]
    and p["properties"]["tagsMap"]["amenity"] in selected_amenities
    and "name" in p["properties"]["tagsMap"]
]
leisure_features = [
    p
    for p in pois
    if "leisure" in p["properties"]["tagsMap"]
    and p["properties"]["tagsMap"]["leisure"] in selected_leisure
    and "name" in p["properties"]["tagsMap"]
]

categorized_features = {}


def select_features(features, category_tag="tourism"):
    for f in features:
        tags = f["properties"]["tagsMap"]
        category = tags[category_tag]
        record = {}
        record["osm_id"] = f["properties"]["id"]
        for t in tags:
            if t in schema:
                record[t] = tags[t]
            # elif t == 'name':
            #     record['poi_name'] = tags[t]
        categorized_features[category] = [
            *categorized_features.get(category, []),
            record,
        ]


select_features(tourism_features, "tourism")
select_features(amenties_features, "amenity")
select_features(leisure_features, "leisure")

with open("selected_features.json", "w") as f:
    f.write(json.dumps(categorized_features, indent=4))


category_attributes = {}

for c, cat_features in categorized_features.items():
    keys = []
    for f in cat_features:
        keys += f.keys()
    category_attributes[c] = list(set(keys))

with open("category_attributes.json", "w") as f:
    f.write(json.dumps(category_attributes, indent=4))


# %%
# run_sql('CREATE EXTENSION postgis;')

# %%
schema = json.loads(open("poi_schema.json").read())
run_sql(schema_to_sql(schema, "pois"))
# print(schema_to_sql(schema, 'pois'))

# %%

# print sql query to create pois table


def insert_features(features):
    for i in range(0, len(features), 100):
        _features = features[i : min(len(features), i + 100)]
        run_sql(insert_rows_sql("pois", schema, _features, useTags=True))
        # print(str(i+100) + ' out of ' + len(features))


insert_features(tourism_features)
insert_features(amenties_features)
insert_features(leisure_features)

# %%
# def run_sql_select(sql):
#     conn = psycopg2.connect(
#         host = 'localhost',
#         dbname = 'osm_ca',
#         user = 'postgres',
#         password = 'postgres',
#         port = 5432
#     )
#     cur = conn.cursor()
#     cur.execute(sql)
#     records = cur.fetchall()
#     cur.close()
#     conn.close()
#     return records

# run_sql_select('SELECT * FROM pois WHERE addr_state IS NOT NULL LIMIT 1;')

# # %%
# selected_filter_attributes = {
#     "viewpoint": [
#         "internet_access",
#         "wheelchair"
#     ],
#     "attraction": [
#         "outdoor_seating",
#         "wheelchair"
#     ],
#     "museum": [
#         "opening_hours",
#         "internet_access",
#         "wheelchair",
#         "museum"
#     ],
#     "theme_park": [
#         "operator",
#         "opening_hours",
#         "wheelchair"
#     ],
#     "hotel": [
#         "historic",
#     ],
#     "gallery": [
#         "wheelchair",
#         "opening_hours",
#         "internet_access",
#         "artwork_type"
#     ],
#     "zoo": [
#         "zoo",
#     ],
#     "cafe": [
#         "outdoor_seating",
#         "delivery",
#         "historic",
#         "takeaway",
#         "opening_hours",
#         "drive_through",
#         "internet_access",
#         "capacity",
#         "wheelchair"
#     ],
#     "restaurant": [
#         "outdoor_seating",
#         "delivery",
#         "historic",
#         "takeaway",
#         "opening_hours",
#         "cuisine",
#         "restaurant",
#         "drive_through",
#         "internet_access",
#         "capacity",
#         "wheelchair"
#     ],
#     "fast_food": [
#         "outdoor_seating",
#         "delivery",
#         "takeaway",
#         "opening_hours",
#         "cuisine",
#         "fast_food",
#         "drive_through",
#         "internet_access",
#         "capacity",
#         "wheelchair"
#     ],
#     "university": [
#         "operator",
#         "wheelchair",
#     ],
#     "hospital": [
#         "emergency",
#         "operator",
#         "opening_hours",
#         "healthcare"
#     ],
#     "park": [
#         "historic",
#         "wheelchair",
#         "operator",
#         "sport",
#         "opening_hours"
#     ],
#     "nature_reserve": [
#         "parking",
#         "operator",
#         "opening_hours"
#     ],
#     "stadium": [
#         "sport"
#     ],
#     "garden": [
#         "historic",
#         "operator",
#         "wheelchair"
#     ]
# }

# # %%
# filter_attirbute_values = {}

# for k in selected_filter_attributes:
#     filter_attirbute_values[k] = {}
#     for row in categorized_features[k]:
#         for t in row:
#             if t in selected_filter_attributes[k]:
#                 filter_attirbute_values[k][t] = (
#                     filter_attirbute_values[k].get(t, []) + [row[t]]
#                 )

# for k in filter_attirbute_values:
#     print("### " + k)
#     for t in filter_attirbute_values[k]:
#         filter_attirbute_values[k][t] = list(set(filter_attirbute_values[k][t]))
#         print(t, filter_attirbute_values[k][t])

# # %%
# print(
#     "SELECT geometry,poi_name FROM pois\nWHERE leisure = 'garden'\n"
#     "ORDER BY geometry <-> (SELECT geometry FROM pois "
#     "WHERE poi_name = 'Carnegie Art Museum' LIMIT 1)\nLIMIT 1;\n"
# )
