-- osm2pgsql flex style for the ViGSQA reference database (v3.0.0).
--
-- Five tables back the 28 GS-QA templates: POI nodes (enriched with the
-- non-spatial filter, multi-source and disambiguation columns) plus region,
-- park, lake and road geometries. Only columns the generator, prompts or
-- evaluation actually read are extracted; anything else is one line away
-- via `grab` below.

local allowed = {
	amenity = {
		hospital = true,
		clinic = true,
		pharmacy = true,
		school = true,
		university = true,
		bank = true,
		restaurant = true,
		cafe = true,
		police = true,
		post_office = true,
		marketplace = true,
		place_of_worship = true,
		fast_food = true,
	},
	tourism = {
		hotel = true,
		museum = true,
		attraction = true,
		gallery = true,
		hostel = true,
	},
	shop = {
		supermarket = true,
		convenience = true,
		bakery = true,
		electronics = true,
	},
	leisure = {
		park = true,
		sports_centre = true,
		swimming_pool = true,
		stadium = true,
	},
}

-- Extra POI tags kept verbatim: non-spatial filters (T2/T6/T14/T18),
-- multi-source anchors (T7/T8) and anchor disambiguation. Address
-- components back the v3 Location gold (canonical address strings are
-- derived from them at generation time). `capacity` is deliberately not
-- extracted: it is a T7/T8 external-Wikipedia attribute, and keeping it as
-- a column would leak the multi-source answer into the reference schema.
local poi_extra_tags = {
	"cuisine",
	"museum",
	"takeaway",
	"outdoor_seating",
	"delivery",
	"emergency",
	"wikidata",
	"wikipedia",
	"addr:housenumber",
	"addr:street",
	"addr:place",
	"addr:suburb",
	"addr:district",
	"addr:city",
	"addr:province",
	"addr:postcode",
}

local park_leisure = {
	park = true,
	garden = true,
	nature_reserve = true,
	recreation_ground = true,
	playground = true,
	common = true,
}

-- Lakes hold both water polygons (natural=water) and waterway lines
-- (upstream applies ST_Length to lakes), hence a generic geometry column.
local lake_waterway = {
	river = true,
	canal = true,
	stream = true,
}

local road_highway = {
	motorway = true,
	trunk = true,
	primary = true,
	secondary = true,
	tertiary = true,
	residential = true,
	unclassified = true,
	pedestrian = true,
	living_street = true,
	footway = true,
	cycleway = true,
}

local function text_col(name)
	return { column = name, type = "text" }
end

local poi_columns = {
	{ column = "name", type = "text", not_null = true },
	{ column = "amenity", type = "text" },
	{ column = "tourism", type = "text" },
	{ column = "shop", type = "text" },
	{ column = "leisure", type = "text" },
}
for _, name in ipairs(poi_extra_tags) do
	poi_columns[#poi_columns + 1] = text_col(name:gsub(":", "_"))
end
poi_columns[#poi_columns + 1] = { column = "way", type = "point", projection = 3857, not_null = true }

local poi_table = osm2pgsql.define_node_table("planet_osm_point", poi_columns, {
	cluster = "no",
	indexes = {
		{ column = "way", method = "gist" },
	},
})

-- Named administrative boundary relations only: Vietnam's OSM has no usable
-- postal-code boundaries, so admin units (admin_level 4/6/8 = province,
-- district, commune) are the GS-QA "region" adaptation.
local region_table = osm2pgsql.define_table({
	name = "planet_osm_region",
	ids = { type = "relation", id_column = "osm_id" },
	columns = {
		{ column = "name", type = "text", not_null = true },
		{ column = "admin_level", type = "text" },
		{ column = "way", type = "geometry", projection = 4326, not_null = true },
	},
	cluster = "no",
	indexes = {
		{ column = "way", method = "gist" },
	},
})

local park_table = osm2pgsql.define_table({
	name = "planet_osm_park",
	ids = { type = "any", type_column = "osm_type", id_column = "osm_id" },
	columns = {
		{ column = "park_name", type = "text", not_null = true },
		{ column = "leisure", type = "text" },
		{ column = "way", type = "geometry", projection = 4326, not_null = true },
	},
	cluster = "no",
	indexes = {
		{ column = "way", method = "gist" },
	},
})

local lake_table = osm2pgsql.define_table({
	name = "planet_osm_lake",
	ids = { type = "any", type_column = "osm_type", id_column = "osm_id" },
	columns = {
		{ column = "lake_name", type = "text", not_null = true },
		{ column = "waterway", type = "text" },
		{ column = "water", type = "text" },
		{ column = "way", type = "geometry", projection = 4326, not_null = true },
	},
	cluster = "no",
	indexes = {
		{ column = "way", method = "gist" },
	},
})

-- Named major roads only: 3.2M highway ways exist in the snapshot and the
-- name requirement is what keeps this table at a usable size.
local road_table = osm2pgsql.define_table({
	name = "planet_osm_road",
	ids = { type = "way", id_column = "osm_id" },
	columns = {
		{ column = "road_name", type = "text", not_null = true },
		{ column = "highway", type = "text" },
		{ column = "way", type = "linestring", projection = 4326, not_null = true },
	},
	cluster = "no",
	indexes = {
		{ column = "way", method = "gist" },
	},
})

local function selected(group, value)
	return value ~= nil and allowed[group][value] == true
end

-- Relation member geometry assembly can fail on broken admin rings, which
-- are common in the Vietnam extract; skip those objects instead of dying.
local function safe_geometry(builder)
	local ok, geom = pcall(function()
		return builder():transform(4326)
	end)
	if ok then
		return geom
	end
	return nil
end

function osm2pgsql.process_node(object)
	local tags = object.tags

	if tags.name == nil or tags.name == "" then
		return
	end

	local amenity = selected("amenity", tags.amenity) and tags.amenity or nil
	local tourism = selected("tourism", tags.tourism) and tags.tourism or nil
	local shop = selected("shop", tags.shop) and tags.shop or nil
	local leisure = selected("leisure", tags.leisure) and tags.leisure or nil

	if amenity == nil and tourism == nil and shop == nil and leisure == nil then
		return
	end

	local row = {
		name = tags.name,
		amenity = amenity,
		tourism = tourism,
		shop = shop,
		leisure = leisure,
		way = object:as_point():transform(3857),
	}
	for _, key in ipairs(poi_extra_tags) do
		row[key:gsub(":", "_")] = tags[key]
	end

	poi_table:insert(row)
end

function osm2pgsql.process_way(object)
	local tags = object.tags

	if tags.name == nil or tags.name == "" then
		return
	end

	if park_leisure[tags.leisure] and object.is_closed then
		local geom = safe_geometry(function()
			return object:as_polygon()
		end)
		if geom then
			park_table:insert({ park_name = tags.name, leisure = tags.leisure, way = geom })
		end
		return
	end

	if lake_waterway[tags.waterway] then
		local geom = safe_geometry(function()
			return object:as_linestring()
		end)
		if geom then
			lake_table:insert({
				lake_name = tags.name,
				waterway = tags.waterway,
				water = tags.natural == "water" and tags.natural or nil,
				way = geom,
			})
		end
		return
	end

	if tags.natural == "water" and object.is_closed then
		local geom = safe_geometry(function()
			return object:as_polygon()
		end)
		if geom then
			lake_table:insert({ lake_name = tags.name, waterway = nil, water = tags.water, way = geom })
		end
		return
	end

	if road_highway[tags.highway] then
		local geom = safe_geometry(function()
			return object:as_linestring()
		end)
		if geom then
			road_table:insert({ road_name = tags.name, highway = tags.highway, way = geom })
		end
	end
end

function osm2pgsql.process_relation(object)
	local tags = object.tags

	if tags.name == nil or tags.name == "" then
		return
	end

	local is_region = tags.boundary == "administrative" and tags.admin_level ~= nil
	local is_park = park_leisure[tags.leisure]
	-- Water areas are type=multipolygon/boundary relations; type=waterway
	-- relations are linear collections whose members are already imported
	-- as ways, so they must not be assembled into polygons here.
	local is_lake = (tags.natural == "water" or tags.landuse == "reservoir")
		and (tags.type == "multipolygon" or tags.type == "boundary")

	if not (is_region or is_park or is_lake) then
		return
	end

	local geom = safe_geometry(function()
		return object:as_multipolygon()
	end)
	if not geom then
		return
	end

	if is_region then
		region_table:insert({ name = tags.name, admin_level = tags.admin_level, way = geom })
	elseif is_park then
		park_table:insert({ park_name = tags.name, leisure = tags.leisure, way = geom })
	else
		lake_table:insert({
			lake_name = tags.name,
			waterway = tags.waterway,
			water = tags.natural == "water" and tags.natural or tags.water,
			way = geom,
		})
	end
end
