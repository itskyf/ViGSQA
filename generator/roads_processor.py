# %%
import json
from glob import glob

import psycopg2
from shapely.geometry import shape

# %%
roads_files = glob("./osm_extract/roads/*.geojson")


# %%
type_map = {
    str: "string",
    int: "integer",
    float: "float",
    type({"abc": 231}): "string",
}

# Schema filter: keep tags present in more than this many features.
TAG_MIN_COUNT = 100


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
        if (aggregate_schema[k] > TAG_MIN_COUNT or not useTags)
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
        # if 'name' not in f['properties']['tagsMap']:
        # continue
        if "name" in f["properties"]["tagsMap"]:
            f["properties"]["tagsMap"]["road_name"] = f["properties"]["tagsMap"]["name"]
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
    if len(values) == 0:
        return ""
    columns = "geometry," + ",".join(columns)
    # Trailing space after ({columns}) mirrors the original template byte-for-byte.
    query = f"\n    INSERT INTO {table_name} ({columns}) \n    VALUES{values};\n    "
    return query


# %%
# roads = []
# for f in roads_files:
#     roads += json.loads(open(f, "r").read())['features']
#     print(len(roads))

# %%
# schema = define_schema(roads)
# {k: schema[k] for k in schema if 'tiger' not in k
#     and 'name:' not in k and 'alt_' not in k}

# %%
schema = json.loads(open("roads_schema.json").read())

run_sql(schema_to_sql(schema, "roads"))


# %%
def insert_features(features):
    for i in range(0, len(features), 10000):
        _features = features[i : min(len(features), i + 10000)]
        sql = insert_rows_sql("roads", schema, _features, useTags=True)
        if sql != "":
            run_sql(sql)
        # print(str(i+100) + ' out of ' + len(features))


for f in roads_files:
    roads = json.loads(open(f).read())["features"]
    # print(len(roads))
    insert_features(roads)
    print(f)
