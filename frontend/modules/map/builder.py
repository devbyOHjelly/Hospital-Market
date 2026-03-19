import json
import os
import time
import re
import numpy as np
import folium
import pandas as pd
import geopandas as gpd
from frontend.config import COLORMAP, WWW_DIR

_STATE_ABBR = {
    "Alabama": "AL",
    "Florida": "FL",
    "Georgia": "GA",
}


def build_map(
    filtered: gpd.GeoDataFrame,
    opacity: float,
    focus_zip: str | None = None,
    selected_zips: list[str] | None = None,
    entities: pd.DataFrame | None = None,
    all_states: list[str] | None = None,
    current_state: str | None = None,
    show_market_layer: bool = True,
    show_entities_layer: bool = False,
) -> str:
    bounds = filtered.total_bounds
    center = [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2]

    m = folium.Map(
        location=center,
        zoom_start=7,
        tiles=None,
        prefer_canvas=False,
        control_scale=False,
        attributionControl=False,
    )

    folium.TileLayer(
        "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
        name="Carto Dark",
        attr="&copy; OpenStreetMap contributors &copy; CARTO",
        show=True,
        control=False,
    ).add_to(m)

    m.get_root().html.add_child(
        folium.Element(
            """
    <style>
    html, body, .leaflet-container, .opacity-ctrl, .leaflet-control-layers {
        font-family: "Open Sans", "Segoe UI", Tahoma, Arial, sans-serif !important;
    }
    .zip-tooltip {
        background: #000000 !important;
        color: #ffffff !important;
        border: 2px solid #ffffff !important;
        border-radius: 0 !important;
        padding: 4px 10px !important;
        font-family: "Open Sans", "Segoe UI", Tahoma, Arial, sans-serif !important;
        font-size: 11px !important;
        font-weight: 600 !important;
        letter-spacing: 0.02em !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.4) !important;
        white-space: nowrap !important;
        text-align: left !important;
    }
    .zip-tooltip table { text-align: left !important; width: 100% !important; }
    .zip-tooltip td, .zip-tooltip th { text-align: left !important; padding: 1px 4px 1px 0 !important; }
    .zip-tooltip::before { display: none !important; }
    </style>
    """
        )
    )

    filtered = filtered.copy()
    if "zipcode" in filtered.columns:

        def _norm_zip(v):
            s = str(v).strip()
            if not s or s.lower() in {"nan", "none"}:
                return ""
            if s.endswith(".0"):
                s = s[:-2]
            match = re.search(r"\d{5}", s)
            if match:
                return match.group(0)
            digits = "".join(ch for ch in s if ch.isdigit())
            return digits[:5].zfill(5) if digits else ""

        filtered["zipcode"] = filtered["zipcode"].apply(_norm_zip)

    if "place_name" not in filtered.columns:
        filtered["place_name"] = ""
    filtered["place_name"] = filtered["place_name"].fillna("").astype(str).str.strip()

    if "msa_name" in filtered.columns:
        msa_vals = filtered["msa_name"].fillna("").astype(str).str.strip()
        missing = filtered["place_name"].eq("")
        filtered.loc[missing, "place_name"] = msa_vals[missing]
    if "county_name" in filtered.columns:
        county_vals = filtered["county_name"].fillna("").astype(str).str.strip()
        missing = filtered["place_name"].eq("")
        filtered.loc[missing, "place_name"] = county_vals[missing]

    try:
        import pgeocode

        missing = filtered["place_name"].eq("")
        if missing.any():
            nomi = pgeocode.Nominatim("us")
            zips = filtered.loc[missing, "zipcode"].astype(str).str.strip()
            valid_zips = [z for z in zips.tolist() if len(z) == 5 and z.isdigit()]
            if valid_zips:
                geo = nomi.query_postal_code(valid_zips)
                if isinstance(geo, pd.DataFrame) and "place_name" in geo.columns:
                    geo_zip = geo.get("postal_code", pd.Series(valid_zips)).astype(str).str.zfill(5)
                    places = geo["place_name"].fillna("").astype(str).str.strip()
                    if "state_name" in geo.columns:
                        states = geo["state_name"].fillna("").astype(str).str.strip()
                        places = np.where(
                            (places != "") & (states != ""),
                            places + ", " + states,
                            places,
                        )
                    place_lookup = dict(zip(geo_zip, places))
                    filtered.loc[missing, "place_name"] = (
                        filtered.loc[missing, "zipcode"].map(place_lookup).fillna("").astype(str)
                    )
    except Exception:
        pass

    filtered["state_abbr"] = filtered["state"].map(lambda s: _STATE_ABBR.get(s, s))

    tip_fields = ["state_abbr", "zipcode"]
    tip_aliases = ["State:", "ZIP:"]
    if "place_name" in filtered.columns:
        tip_fields.append("place_name")
        tip_aliases.append("Place:")
    if "hospital_potential" in filtered.columns:
        filtered["hospital_potential_tooltip"] = (
            pd.to_numeric(filtered["hospital_potential"], errors="coerce")
            .round(2)
            .fillna(0.0)
        )
        tip_fields.append("hospital_potential_tooltip")
        tip_aliases.append("Score:")

    geojson_data = json.loads(filtered.to_json())
    _op = opacity

    if show_market_layer:
        geo = folium.GeoJson(
            geojson_data,
            style_function=lambda f: {
                "fillColor": COLORMAP(f["properties"].get("hospital_potential") or 0),
                "color": "#30363d",
                "weight": 0.3,
                "fillOpacity": _op,
            },
            highlight_function=lambda f: {
                "weight": 1.5,
                "color": "#e6edf3",
                "fillOpacity": min(_op + 0.15, 1.0),
            },
            tooltip=folium.GeoJsonTooltip(
                fields=tip_fields,
                aliases=tip_aliases,
                sticky=True,
                class_name="zip-tooltip",
                style="",
            ),
            name="Market Score",
        )
        geo.add_to(m)

    if show_entities_layer and entities is not None and len(entities) > 0:
        _add_entity_layer(m, entities, bounds)

    _inject_click_handler(m)
    _inject_opacity_listener(m, opacity)
    _inject_opacity_slider(m, opacity, current_state=current_state)
    if focus_zip:
        _inject_focus_zip(m, focus_zip)
    if selected_zips:
        _inject_preselected(m, selected_zips)
    _inject_legend(m)

    m.get_root().html.add_child(
        folium.Element(
            "<style>"
            ".leaflet-control-attribution{display:none!important;}"
            ".leaflet-bottom.leaflet-left,.leaflet-bottom.leaflet-right{display:none!important;}"
            ".leaflet-control-layers-separator{display:none!important;}"
            "</style>"
            "<script>"
            "document.addEventListener('DOMContentLoaded',function(){"
            "document.querySelectorAll('.leaflet-bar a[title]').forEach(function(a){a.removeAttribute('title');});"
            "});"
            "</script>"
        )
    )

    m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
    m.get_root().html.add_child(
        folium.Element(
            "<script>"
            "window.addEventListener('load', function(){"
            f"var map=window['{m.get_name()}'];"
            "if(map && !window._initialZoomOutDone){"
            "window._initialZoomOutDone=true;"
            "map.setZoom(Math.max(map.getMinZoom(), map.getZoom()-1));"
            "}"
            "});"
            "</script>"
        )
    )

    m.save(os.path.join(WWW_DIR, "map.html"))
    ts = int(time.time() * 1000)
    return (
        f'<iframe id="map_frame" src="map.html?v={ts}" '
        f'style="width:100%;height:100vh;border:none;display:block;"></iframe>'
    )


def _add_entity_layer(
    m: folium.Map, entities: pd.DataFrame, state_bounds: tuple | None = None
) -> None:
    ents = entities.dropna(subset=["lat", "lon"]).copy()
    if ents.empty:
        return

    if state_bounds is not None:
        minx, miny, maxx, maxy = state_bounds
        pad = 0.5
        ents = ents[
            (ents["lon"] >= minx - pad)
            & (ents["lon"] <= maxx + pad)
            & (ents["lat"] >= miny - pad)
            & (ents["lat"] <= maxy + pad)
        ]
        if ents.empty:
            return

    def _safe(val):
        if pd.isna(val) or str(val).lower() in ("none", "nan", ""):
            return ""
        return str(val).strip()

    ents["_zip5"] = ents["zip"].astype(str).str.zfill(5)
    max_markers = 50

    hospitals = (
        ents[ents["ccn"].notna()].copy()
        if "ccn" in ents.columns
        else pd.DataFrame()
    )
    if not hospitals.empty:
        hospitals = hospitals.sort_values("entity_score", ascending=False)
        hospitals = hospitals.drop_duplicates(subset="_zip5", keep="first")

    used_zips = set(hospitals["_zip5"]) if not hospitals.empty else set()
    remaining_slots = max_markers - len(hospitals) if not hospitals.empty else max_markers

    others = pd.DataFrame()
    if remaining_slots > 0:
        non_hosp = ents[~ents["_zip5"].isin(used_zips)].copy()
        if not non_hosp.empty:
            non_hosp = non_hosp.sort_values("entity_score", ascending=False)
            non_hosp = non_hosp.drop_duplicates(subset="_zip5", keep="first")
            others = non_hosp.head(remaining_slots)

    top_per_zip = (
        pd.concat([hospitals, others], ignore_index=True) if not hospitals.empty else others
    )
    if top_per_zip.empty:
        return

    features = []
    for _, row in top_per_zip.iterrows():
        name = _safe(row.get("display_name", ""))
        etype = _safe(row.get("entity_type", row.get("hospital_type", "")))
        npi = _safe(row.get("npi", ""))
        ccn = _safe(row.get("ccn", ""))
        ownership = _safe(row.get("ownership", ""))
        emergency = _safe(row.get("emergency_services", ""))
        rating = _safe(row.get("hospital_rating", ""))
        city = _safe(row.get("city", ""))
        zipcode = _safe(row.get("zip", ""))
        state = _safe(row.get("state", ""))

        popup_lines = [f"<b style='font-size:13px;color:#ffffff;'>{name}</b>"]
        if etype:
            popup_lines.append(f"<span style='color:#ffffff;'>{etype}</span>")
        popup_lines.append("<hr style='margin:4px 0;border-color:#ffffff;'>")
        if npi:
            popup_lines.append(
                f"<b>NPI:</b> {npi} <span style='color:#ffffff;'>(NPPES)</span>"
            )
        if ccn:
            popup_lines.append(
                f"<b>CCN:</b> {ccn} <span style='color:#ffffff;'>(CMS)</span>"
            )
        if ownership:
            popup_lines.append(f"<b>Ownership:</b> {ownership}")
        if rating:
            try:
                stars = int(float(rating))
                popup_lines.append(f"<b>Rating:</b> {'&#9733;' * stars} ({rating}/5)")
            except (ValueError, TypeError):
                popup_lines.append(f"<b>Rating:</b> {rating}")
        else:
            popup_lines.append("<b>Rating:</b> <span style='color:#ffffff;'>N/A</span>")
        popup_lines.append("<b>Entity Score:</b> <span style='color:#ffffff;'>TBD</span>")
        if emergency:
            popup_lines.append(f"<b>Emergency:</b> {emergency}")
        else:
            popup_lines.append("<b>Emergency:</b> <span style='color:#ffffff;'>N/A</span>")
        if city and zipcode:
            popup_lines.append(f"<b>Location:</b> {city}, {state} {zipcode}")

        popup_html = (
            f"<div style='font-family:\"Open Sans\",\"Segoe UI\",Tahoma,Arial,sans-serif;"
            f"font-size:11px;color:#ffffff;line-height:1.5;min-width:180px;text-align:left;'>"
            f"{'<br>'.join(popup_lines)}</div>"
        )

        rating_display = ""
        if rating:
            try:
                rating_display = f"{float(rating):.0f}/5"
            except (ValueError, TypeError):
                rating_display = rating
        else:
            rating_display = "N/A"

        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(row["lon"]), float(row["lat"])],
                },
                "properties": {
                    "name": name or "Unknown",
                    "state": state,
                    "zip": zipcode,
                    "rating": rating_display,
                    "type": etype,
                    "npi": npi,
                    "popup": popup_html,
                },
            }
        )

    if not features:
        return

    geojson = {"type": "FeatureCollection", "features": features}

    m.get_root().html.add_child(
        folium.Element(
            """
    <style>
    .entity-popup .leaflet-popup-content-wrapper {
        background: #000000 !important;
        color: #ffffff !important;
        border-radius: 0 !important;
        border: 2px solid #ffffff !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.5) !important;
        padding: 0 !important;
    }
    .entity-popup .leaflet-popup-content { margin: 10px 14px !important; text-align: left !important; }
    .entity-popup .leaflet-popup-tip { background: #000000 !important; }
    .entity-popup .leaflet-popup-close-button {
        color: #ffffff !important;
        font-size: 18px !important;
        padding: 6px 8px 0 0 !important;
    }
    .entity-popup .leaflet-popup-close-button:hover { color: #ffffff !important; }
    .entity-pin {
        position: relative;
        width: 18px; height: 24px;
    }
    .entity-pin svg {
        display: block;
        width: 18px; height: 24px;
        transition: transform 0.15s;
    }
    .entity-pin:hover svg {
        transform: scale(1.2) translateY(-2px);
    }
    </style>
    """
        )
    )

    pin_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 30 42">'
        '<path d="M15 1C7.8 1 2 6.8 2 14c0 10.5 13 26 13 26s13-15.5 13-26C28 6.8 22.2 1 15 1z"'
        ' fill="#ff7f00" stroke="#000" stroke-width="1.5"/>'
        '<circle cx="15" cy="14" r="5" fill="#ffffff"/>'
        "</svg>"
    )
    pin_icon = folium.DivIcon(
        html=f'<div class="entity-pin">{pin_svg}</div>',
        icon_size=(18, 24),
        icon_anchor=(9, 24),
        popup_anchor=(0, -24),
    )
    layer = folium.GeoJson(
        geojson,
        name="Entities",
        marker=folium.Marker(icon=pin_icon),
        show=True,
    )
    layer.add_to(m)

    popup_map = {
        f["properties"]["zip"] or f["properties"]["name"]: f["properties"]["popup"]
        for f in features
    }
    popup_js_data = json.dumps(popup_map)
    script = f"""<script>
    window.addEventListener('load', function() {{
        var popupData = {popup_js_data};
        var map = window['{m.get_name()}'];
        if (!map) return;
        var hoverPopup = null;

        var entityLayer = {layer.get_name()};
        if (entityLayer && entityLayer.eachLayer) {{
            entityLayer.eachLayer(function(sub) {{
                    if (sub.feature && sub.feature.geometry && sub.feature.geometry.type === 'Point') {{
                        var p = sub.feature.properties;
                        var key = p.zip || p.name;
                        var html = popupData[key];
                        if (!html) return;

                        sub.on('mouseover', function(e) {{
                            hoverPopup = L.popup({{
                                className: 'entity-popup',
                                maxWidth: 280,
                                closeButton: false,
                                autoPan: false,
                                offset: [0, -22]
                            }})
                            .setLatLng(e.latlng)
                            .setContent(html)
                            .openOn(map);
                        }});

                        sub.on('mouseout', function() {{
                            if (hoverPopup) {{
                                map.closePopup(hoverPopup);
                                hoverPopup = null;
                            }}
                        }});
                    }}
            }});
        }}
    }});
    </script>"""
    m.get_root().html.add_child(folium.Element(script))


def _inject_click_handler(m: folium.Map) -> None:
    map_var = m.get_name()
    script = f"""<script>
window._selectedLayers = {{}};
window._maxSelected = 10;

window._dollarMarkers = {{}};
window._focusTimer = null;
window._focusTransient = null;
window._selectedBorderColor = '#ff7f00';
window._normZip = function(v) {{
    var s = String(v || '').trim();
    if (!s) return '';
    if (s.endsWith('.0')) s = s.slice(0, -2);
    var m = s.match(/\\d{{5}}/);
    if (m) return m[0];
    var d = s.replace(/\\D/g, '');
    return d ? d.slice(0, 5).padStart(5, '0') : '';
}};
window._ensureStripePattern = function(map) {{
    if (!map || !map.getContainer) return;
    var svgs = map.getContainer().querySelectorAll('svg');
    svgs.forEach(function(svg) {{
        if (!svg.querySelector('#hmStripePattern')) {{
            var defs = svg.querySelector('defs');
            if (!defs) {{
                defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
                svg.insertBefore(defs, svg.firstChild);
            }}
            var pattern = document.createElementNS('http://www.w3.org/2000/svg', 'pattern');
            pattern.setAttribute('id', 'hmStripePattern');
            pattern.setAttribute('patternUnits', 'userSpaceOnUse');
            pattern.setAttribute('width', '8');
            pattern.setAttribute('height', '8');
            pattern.setAttribute('patternTransform', 'rotate(45)');
            var bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
            bg.setAttribute('x', '0'); bg.setAttribute('y', '0');
            bg.setAttribute('width', '8'); bg.setAttribute('height', '8');
            bg.setAttribute('fill', '#ffffff');
            var stripe = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            stripe.setAttribute('x1', '0'); stripe.setAttribute('y1', '0');
            stripe.setAttribute('x2', '0'); stripe.setAttribute('y2', '8');
            stripe.setAttribute('stroke', '#ff7f00');
            stripe.setAttribute('stroke-width', '4');
            pattern.appendChild(bg);
            pattern.appendChild(stripe);
            defs.appendChild(pattern);
        }}
    }});
}};
window._applySelectedStyle = function(layer, map, emphasize) {{
    if (!layer || !layer.setStyle) return;
    window._ensureStripePattern(map);
    var selectedFillOpacity = Math.max(0.1, Math.min(1, window._mapOpacity || 1));
    var borderW = emphasize ? 3 : 2.5;
    layer.setStyle({{
        fillColor: '#ffffff',
        fillOpacity: selectedFillOpacity,
        color: window._selectedBorderColor,
        weight: borderW
    }});
    if (layer._path) {{
        layer._path.setAttribute('fill', 'url(#hmStripePattern)');
        layer._path.setAttribute('fill-opacity', String(selectedFillOpacity));
        layer._path.style.fillOpacity = String(selectedFillOpacity);
        layer._path.style.filter = emphasize
            ? 'drop-shadow(0 0 10px rgba(255,127,0,0.75))'
            : 'drop-shadow(0 0 8px rgba(255,127,0,0.65))';
    }}
}};
window._clearSelectedStyle = function(layer) {{
    if (!layer || !layer.setStyle) return;
    var baseFill = layer._origFillColor || layer.options.fillColor || '#30363d';
    layer.setStyle({{
        fillColor: baseFill,
        fillOpacity: window._mapOpacity,
        color: '#30363d',
        weight: 0.3
    }});
    if (layer._path) {{
        layer._path.setAttribute('fill', baseFill);
        layer._path.setAttribute('fill-opacity', String(window._mapOpacity));
        layer._path.style.filter = '';
        layer._path.style.fillOpacity = '';
    }}
}};
window._clearTransientFocus = function() {{
    if (window._focusTimer) {{
        clearTimeout(window._focusTimer);
        window._focusTimer = null;
    }}
    var cur = window._focusTransient;
    if (!cur || !cur.layer) {{
        window._focusTransient = null;
        return;
    }}
    var layer = cur.layer;
    var zip = cur.zip;
    if (!window._selectedLayers[zip]) {{
        layer._focusHighlight = false;
        window._clearSelectedStyle(layer);
    }}
    window._focusTransient = null;
}};
window._focusZipTransient = function(layer, map, zipcode, durationMs) {{
    var zip = window._normZip(zipcode);
    if (!layer || !zip) return false;
    window._clearTransientFocus();
    map.fitBounds(layer.getBounds(), {{maxZoom: 11, padding: [40, 40]}});
    if (!window._selectedLayers[zip]) {{
        if (!layer._origFillColor) layer._origFillColor = layer.options.fillColor || '#30363d';
        layer._focusHighlight = true;
        window._applySelectedStyle(layer, map, true);
        window._focusTransient = {{layer: layer, zip: zip}};
        window._focusTimer = setTimeout(function() {{
            window._clearTransientFocus();
        }}, durationMs || 2000);
    }}
    layer.bringToFront();
    return true;
}};

window._addDollarSign = function(layer, map) {{
    var bounds = layer.getBounds();
    var center = bounds.getCenter();
    var icon = L.divIcon({{
        className: '',
        html: '<div style="font-size:16px;font-weight:900;color:#15803d;text-shadow:0 1px 2px rgba(0,0,0,0.5);text-align:center;line-height:1;">$</div>',
        iconSize: [20, 20],
        iconAnchor: [10, 10]
    }});
    var marker = L.marker(center, {{icon: icon, interactive: false, pane: 'tooltipPane'}});
    marker.addTo(map);
    return marker;
}};

window._deselectZip = function(zipcode) {{
    var zip = window._normZip(zipcode);
    var layer = window._selectedLayers[zip];
    if (layer) {{
        layer._focusHighlight = false;
        window._clearSelectedStyle(layer);
        if (window._dollarMarkers[zip]) {{
            window._dollarMarkers[zip].remove();
            delete window._dollarMarkers[zip];
        }}
        delete window._selectedLayers[zip];
    }}
}};

window._selectZip = function(layer, map, noZoom) {{
    var zipcode = window._normZip(layer.feature.properties.zipcode || '');
    if (!zipcode) return false;
    if (Object.keys(window._selectedLayers).length >= window._maxSelected) return false;
    if (!layer._origFillColor) layer._origFillColor = layer.options.fillColor || '#30363d';
    layer._focusHighlight = true;
    window._applySelectedStyle(layer, map, false);
    layer.bringToFront();
    if (!noZoom) map.fitBounds(layer.getBounds(), {{maxZoom: 11, padding: [40, 40]}});
    window._selectedLayers[zipcode] = layer;
    return true;
}};

window.addEventListener('load', function() {{
    var map = window['{map_var}'];
    if (!map) {{
        setTimeout(function() {{
            var retryMap = window['{map_var}'];
            if (!retryMap) return;
            retryMap.eachLayer(function(layer) {{
                if (layer.eachLayer) {{
                    layer.eachLayer(function(sub) {{
                        if (sub.feature && sub.feature.properties && sub.feature.properties.zipcode) {{
                            sub.on('click', function() {{
                                var p = sub.feature.properties;
                                var zipcode = window._normZip(p.zipcode || '');
                                var isSelected = !!window._selectedLayers[zipcode];
                                var action;
                                if (isSelected) {{
                                    window._deselectZip(zipcode);
                                    action = 'deselect';
                                }} else {{
                                    var added = window._selectZip(sub, retryMap);
                                    if (!added) {{
                                        window.parent.postMessage({{
                                            type: 'zip_click', action: 'limit_reached',
                                            zipcode: zipcode, state: String(p.state || '')
                                        }}, '*');
                                        return;
                                    }}
                                    action = 'select';
                                }}
                                var payload = Object.assign({{}}, p || {{}});
                                payload.type = 'zip_click';
                                payload.action = action;
                                payload.zipcode = zipcode;
                                payload.zip_code = String(p.zip_code || p.zipcode || zipcode || '');
                                payload.state = String(p.state || '');
                                window.parent.postMessage(payload, '*');
                            }});
                        }}
                    }});
                }}
            }});
        }}, 150);
        return;
    }}
    map.eachLayer(function(layer) {{
        if (layer.eachLayer) {{
            layer.eachLayer(function(sub) {{
                if (sub.feature && sub.feature.properties && sub.feature.properties.zipcode) {{
                    sub.on('click', function() {{
                        var p = sub.feature.properties;
                        var zipcode = window._normZip(p.zipcode || '');
                        var isSelected = !!window._selectedLayers[zipcode];
                        var action;
                        if (isSelected) {{
                            window._deselectZip(zipcode);
                            action = 'deselect';
                        }} else {{
                            var added = window._selectZip(sub, map);
                            if (!added) {{
                                window.parent.postMessage({{
                                    type: 'zip_click', action: 'limit_reached',
                                    zipcode: zipcode, state: String(p.state || '')
                                }}, '*');
                                return;
                            }}
                            action = 'select';
                        }}
                        var payload = Object.assign({{}}, p || {{}});
                        payload.type = 'zip_click';
                        payload.action = action;
                        payload.zipcode = zipcode;
                        payload.zip_code = String(p.zip_code || p.zipcode || zipcode || '');
                        payload.state = String(p.state || '');
                        window.parent.postMessage(payload, '*');
                    }});
                }}
            }});
        }}
    }});
}});
</script>"""
    m.get_root().html.add_child(folium.Element(script))


def _inject_opacity_listener(m: folium.Map, initial_opacity: float) -> None:
    map_var = m.get_name()
    script = f"""<script>
window._mapOpacity = {initial_opacity};
window.addEventListener('load', function() {{
    var map = window['{map_var}'];
    if (!map) return;
    map.eachLayer(function(layer) {{
        if (layer.eachLayer) {{
            layer.eachLayer(function(sub) {{
                if (sub.feature && sub.feature.properties && sub.feature.properties.zipcode && sub.setStyle) {{
                    if (!sub._origFillColor && sub.options.fillColor) sub._origFillColor = sub.options.fillColor;
                    sub.off('mouseover').off('mouseout');
                    sub.on('mouseover', function(e) {{
                        if (e.target._focusHighlight) {{
                            window._applySelectedStyle(e.target, map, true);
                        }} else {{
                            e.target.setStyle({{
                                fillOpacity: Math.min(window._mapOpacity + 0.15, 1.0),
                                weight: 1.5, color: '#e6edf3'
                            }});
                        }}
                    }});
                    sub.on('mouseout', function(e) {{
                        if (e.target._focusHighlight) {{
                            window._applySelectedStyle(e.target, map, false);
                        }} else {{
                            e.target.setStyle({{
                                fillOpacity: window._mapOpacity, weight: 0.3, color: '#30363d'
                            }});
                            if (e.target._path) e.target._path.style.filter = '';
                        }}
                    }});
                }}
            }});
        }}
    }});
}});

window.addEventListener('message', function(event) {{
    if (event.data && event.data.type === 'deselect_zip') {{
        window._deselectZip(String(event.data.zipcode || ''));
    }}
    if (event.data && event.data.type === 'select_zip') {{
        var targetZip = window._normZip(event.data.zipcode || '');
        var map = window['{map_var}'];
        if (!map) return;
        if (targetZip && !window._selectedLayers[targetZip]) {{
            map.eachLayer(function(layer) {{
                if (layer.eachLayer) {{
                    layer.eachLayer(function(sub) {{
                        if (sub.feature && sub.feature.properties &&
                            window._normZip(sub.feature.properties.zipcode) === targetZip) {{
                            window._selectZip(sub, map);
                        }}
                    }});
                }}
            }});
        }}
    }}
    if (event.data && event.data.type === 'focus_blink') {{
        var zip = window._normZip(event.data.zipcode || '');
        if (window._blinkingZip === zip) return;
        var map = window['{map_var}'];
        if (!map) return;
        var found = null;
        map.eachLayer(function(layer) {{
            if (layer.eachLayer) {{
                layer.eachLayer(function(sub) {{
                    if (sub.feature && sub.feature.properties &&
                        window._normZip(sub.feature.properties.zipcode) === zip) {{
                        found = sub;
                    }}
                }});
            }}
        }});
        if (!found) return;
        window._blinkingZip = zip;
        window.parent.postMessage({{type: 'blink_ack'}}, '*');
        window._focusZipTransient(found, map, zip, 2000);
        if (window._blinkingZip === zip) window._blinkingZip = null;
    }}
    if (event.data && event.data.type === 'clear_focus_highlight') {{
        window._clearTransientFocus();
    }}
}});
</script>"""
    m.get_root().html.add_child(folium.Element(script))


def _inject_states_in_layer_control(m: folium.Map, states: list[str], current: str) -> None:
    """Inject state radio buttons into the Leaflet LayerControl panel."""
    if not states:
        return
    items_js = ",".join(
        f'{{"full":"{s}","abbr":"{_STATE_ABBR.get(s, s)}"}}'
        for s in states
    )
    html = f"""
<style>
.lc-states-section {{
    border-top: none;
    padding: 6px 0 4px;
    margin-top: 4px;
}}
.lc-states-section label {{
    display: block; padding: 3px 0; cursor: pointer;
    font-size: 0.75rem; color: #ffffff;
}}
.lc-states-section label:hover {{ color: #ff7f00; }}
.lc-states-section input[type="radio"] {{
    accent-color: #f97316; margin-right: 6px; vertical-align: middle;
}}
.leaflet-control-layers {{
    background: transparent !important;
    border: none !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    color: #1a1a1a !important;
    padding: 0 !important;
    font-family: "Open Sans", "Segoe UI", Tahoma, Arial, sans-serif !important;
}}
.leaflet-control-layers-list {{
    background: #000000 !important;
    border: 2px solid #ffffff !important;
    border-radius: 0 !important;
    padding: 16px 20px !important;
    margin-top: 6px !important;
    min-width: 0 !important;
    width: max-content !important;
}}
.leaflet-control-layers label {{
    color: #ffffff !important; font-size: 0.86rem !important;
    padding: 3px 0 !important;
    margin: 0 !important;
}}
.leaflet-control-layers-toggle {{
    background-color: #000000 !important;
    border: 2px solid #ffffff !important;
    border-radius: 0 !important;
    width: 44px !important; height: 44px !important;
    background-image: url('https://unpkg.com/leaflet@1.9.4/dist/images/layers.png') !important;
    background-repeat: no-repeat !important;
    background-position: center !important;
    background-size: 20px 20px !important;
    text-decoration: none !important;
}}
.leaflet-control-layers-toggle::before {{
    content: none !important;
}}
.leaflet-control-layers-toggle:hover {{
    background-color: #000000 !important;
    border-color: #ffffff !important;
    box-shadow: 0 2px 6px rgba(0,0,0,0.2) !important;
}}
.leaflet-control-layers input[type="checkbox"] {{
    accent-color: #f97316;
    margin-left: 0 !important;
    margin-right: 6px !important;
}}
.leaflet-control-layers-expanded {{
    padding: 0 !important;
}}
.leaflet-control-layers-expanded .leaflet-control-layers-list {{
    min-width: 0 !important;
    width: max-content !important;
    padding: 14px 16px !important;
    border: 2px solid #ffffff !important;
}}
.leaflet-control-layers-expanded .leaflet-control-layers-list label {{
    font-size: 0.9rem !important;
    padding: 3px 0 !important;
}}
.leaflet-top .leaflet-control:hover .leaflet-control-layers-list {{
    border: 2px solid #ffffff !important;
}}
</style>
<script>
document.addEventListener('DOMContentLoaded', function() {{
    var items = [{items_js}];
    var current = "{current}";

    function inject() {{
        var ctrl = document.querySelector('.leaflet-control-layers');
        var panel = document.querySelector('.leaflet-control-layers-list');
        var toggle = document.querySelector('.leaflet-control-layers-toggle');
        if (!ctrl || !panel || !toggle) {{ setTimeout(inject, 100); return; }}

        var section = document.createElement('div');
        section.className = 'lc-states-section';

        items.forEach(function(it) {{
            var label = document.createElement('label');
            var radio = document.createElement('input');
            radio.type = 'radio';
            radio.name = 'state_select';
            radio.value = it.full;
            if (it.full === current) radio.checked = true;
            radio.addEventListener('change', function() {{
                current = it.full;
                window.parent.postMessage({{type: 'state_change', state: it.full}}, '*');
            }});
            label.appendChild(radio);
            label.appendChild(document.createTextNode(it.abbr));
            section.appendChild(label);
        }});

        panel.appendChild(section);
    }}
    inject();
}});
</script>"""
    m.get_root().html.add_child(folium.Element(html))


def _inject_opacity_slider(m: folium.Map, initial_opacity: float, current_state: str | None = None) -> None:
    map_var = m.get_name()
    pct = int(initial_opacity * 100)
    script = f"""
<style>
.opacity-ctrl {{
    position: fixed; right: 10px; top: calc(50% + 24px); transform: translateY(-50%);
    z-index: 1000; display: flex; flex-direction: column; align-items: center;
    background: #000000; border-radius: 0; padding: 8px 0;
    border: 2px solid #ffffff; gap: 8px;
    height: 280px;
    justify-content: space-between;
    width: 62px; box-sizing: border-box;
    font-family: "Open Sans", "Segoe UI", Tahoma, Arial, sans-serif !important;
}}
.opacity-ctrl .op-label {{
    color: #ffffff; font-size: 0.72rem; letter-spacing: 0.02em; text-transform: none;
    writing-mode: vertical-rl; text-orientation: mixed; transform: rotate(180deg); margin: 4px 0;
    font-weight: 600;
}}
.opacity-ctrl input[type="range"] {{
    writing-mode: vertical-lr; direction: rtl; width: 8px; height: 190px;
    appearance: none; -webkit-appearance: none; background: transparent; cursor: pointer;
}}
.opacity-ctrl input[type="range"]::-webkit-slider-runnable-track {{
    width: 8px; background: #ff7f00;
    border-radius: 4px; border: 1px solid rgba(0,0,0,0.25);
}}
.opacity-ctrl input[type="range"]::-webkit-slider-thumb {{
    -webkit-appearance: none; width: 20px; height: 8px; border-radius: 1px;
    background: #ffffff; border: 1px solid #ffffff;
    box-shadow: 0 0 3px rgba(0,0,0,0.35); margin-left: -6px;
    transform: none;
}}
.opacity-ctrl input[type="range"]::-moz-range-track {{
    width: 8px; background: #ff7f00;
    border-radius: 4px; border: 1px solid rgba(0,0,0,0.25);
}}
.opacity-ctrl input[type="range"]::-moz-range-thumb {{
    width: 20px; height: 8px; border-radius: 1px;
    background: #ffffff; border: 1px solid #ffffff;
    box-shadow: 0 0 3px rgba(0,0,0,0.35);
}}
.opacity-ctrl .op-val {{ color: #ffffff; font-size: 0.76rem; font-weight: 600; width: 38px; text-align: center; }}
</style>
<div class="opacity-ctrl">
    <span class="op-val" id="op-pct">{pct}%</span>
    <input type="range" id="opacity-slider" min="10" max="100" step="5" value="{pct}">
    <span class="op-label">Opacity</span>
</div>
<script>
(function() {{
    var slider = document.getElementById('opacity-slider');
    var label = document.getElementById('op-pct');
    function applyOpacity(val) {{
        window._mapOpacity = val;
        var map = window['{map_var}'];
        if (!map) return;
        map.eachLayer(function(layer) {{
            if (layer.eachLayer) {{
                layer.eachLayer(function(sub) {{
                    if (sub.feature && sub.feature.properties && sub.feature.properties.zipcode && sub.setStyle) {{
                        if (sub._focusHighlight) {{
                            window._applySelectedStyle(sub, map, false);
                        }} else {{
                            sub.setStyle({{fillOpacity: val}});
                            if (sub._path) {{
                                sub._path.setAttribute('fill-opacity', String(val));
                                sub._path.style.fillOpacity = String(val);
                                sub._path.style.opacity = '1';
                            }}
                        }}
                    }}
                }});
            }}
        }});
        // Hard fallback: force visible opacity update on all rendered SVG polygons.
        try {{
            var container = map.getContainer();
            if (container) {{
                var paths = container.querySelectorAll('path.leaflet-interactive');
                paths.forEach(function(p) {{
                    var fillVal = p.getAttribute('fill') || '';
                    var target = (fillVal.indexOf('hmStripePattern') >= 0)
                        ? Math.max(0.1, val)
                        : val;
                    p.setAttribute('fill-opacity', String(target));
                    p.style.fillOpacity = String(target);
                    p.style.opacity = '1';
                }});
            }}
        }} catch (e) {{}}
    }}
    function pushOpacity(val) {{
        window.parent.postMessage({{type: 'opacity_save', value: val}}, '*');
    }}
    applyOpacity(parseInt(slider.value) / 100);
    slider.addEventListener('input', function() {{
        var val = parseInt(this.value) / 100;
        label.textContent = this.value + '%';
        applyOpacity(val);
        pushOpacity(val);
    }});
}})();
</script>"""
    m.get_root().html.add_child(folium.Element(script))


def _inject_focus_zip(m: folium.Map, zipcode: str) -> None:
    map_var = m.get_name()
    script = f"""<script>
window.addEventListener('load', function() {{
    var targetZip = window._normZip ? window._normZip('{zipcode}') : '{zipcode}';
    if (!targetZip) return;
    window._blinkingZip = targetZip;
    var map = window['{map_var}'];
    if (!map) return;
    var attempts = 0;
    function tryFocus() {{
        var found = null;
        map.eachLayer(function(layer) {{
            if (found || !layer.eachLayer) return;
            layer.eachLayer(function(sub) {{
                if (found) return;
                if (sub.feature && sub.feature.properties &&
                    (window._normZip ? window._normZip(sub.feature.properties.zipcode) : String(sub.feature.properties.zipcode)) === targetZip) {{
                    found = sub;
                }}
            }});
        }});
        if (found) {{
            if (window._focusZipTransient) {{
                window._focusZipTransient(found, map, targetZip, 2000);
            }} else {{
                map.fitBounds(found.getBounds(), {{maxZoom: 11, padding: [40, 40]}});
            }}
            window.parent.postMessage({{type: 'blink_ack'}}, '*');
            if (window._blinkingZip === targetZip) window._blinkingZip = null;
            return;
        }}
        attempts += 1;
        if (attempts < 20) setTimeout(tryFocus, 150);
    }}
    tryFocus();
}});
</script>"""
    m.get_root().html.add_child(folium.Element(script))


def _inject_preselected(m: folium.Map, zipcodes: list[str]) -> None:
    map_var = m.get_name()
    zips_js = ",".join(f"'{z}'" for z in zipcodes)
    script = f"""<script>
window.addEventListener('load', function() {{
    var map = window['{map_var}'];
    if (!map) return;
    var targets = new Set([{zips_js}]);
    map.eachLayer(function(layer) {{
        if (layer.eachLayer) {{
            layer.eachLayer(function(sub) {{
                if (sub.feature && sub.feature.properties &&
                    targets.has(String(sub.feature.properties.zipcode))) {{
                    window._selectZip(sub, map, true);
                }}
            }});
        }}
    }});
}});
</script>"""
    m.get_root().html.add_child(folium.Element(script))


def _inject_legend(m: folium.Map) -> None:
    legend = (
        '<div style="position:fixed;bottom:18px;left:50%;transform:translateX(-50%);'
        'z-index:1000;background:#000000;border-radius:0;'
        'padding:12px 18px 14px;border:2px solid #ffffff;'
        'font-family:\'Open Sans\',\'Segoe UI\',Tahoma,Arial,sans-serif;">'
        '<div style="text-align:center;color:#ffffff;font-size:0.92rem;font-weight:600;'
        'letter-spacing:0.02em;text-transform:none;margin-bottom:4px;">'
        "ZIP Score</div>"
        '<div style="display:flex;align-items:center;gap:10px;">'
        '<span style="color:#ffffff;font-size:0.76rem;font-weight:600;letter-spacing:0.02em;'
        'text-transform:uppercase;">Low</span>'
        '<div style="width:280px;height:16px;border-radius:0;'
        "background:linear-gradient(to right,#ffffff,#fff0d4,#ffd699,#ffb84d,#ff7f00,#ff7f00);"
        'border:none;"></div>'
        '<span style="color:#ffffff;font-size:0.76rem;font-weight:600;letter-spacing:0.02em;'
        'text-transform:uppercase;">High</span>'
        "</div></div>"
    )
    m.get_root().html.add_child(folium.Element(legend))
