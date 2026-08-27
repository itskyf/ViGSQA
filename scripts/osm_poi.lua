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

local poi_table = osm2pgsql.define_node_table("planet_osm_point", {
	{ column = "name", type = "text", not_null = true },
	{ column = "amenity", type = "text" },
	{ column = "tourism", type = "text" },
	{ column = "shop", type = "text" },
	{ column = "leisure", type = "text" },
	{ column = "way", type = "point", projection = 3857, not_null = true },
}, {
	cluster = "no",
	indexes = {
		{ column = "way", method = "gist" },
	},
})

local function selected(group, value)
	return value ~= nil and allowed[group][value] == true
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

	poi_table:insert({
		name = tags.name,
		amenity = amenity,
		tourism = tourism,
		shop = shop,
		leisure = leisure,
		way = object:as_point():transform(3857),
	})
end
