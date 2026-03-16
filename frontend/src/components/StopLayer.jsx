/**
 * StopLayer — Renders public transport stops as glowing markers with labels.
 *
 * Fetches stop data from /api/stops on mount and renders:
 *   - Glowing circle markers visible from zoom level 12+
 *   - Stop name labels visible from zoom level 13+
 *   - Premium dark theme-matching design with strong contrast
 */
import { useEffect, useRef } from 'react';
import { fetchStops } from '../services/api';

const STOP_SOURCE_ID = 'stops-source';
const STOP_GLOW_LAYER = 'stops-glow';
const STOP_DOT_LAYER = 'stops-dot';
const STOP_LABEL_LAYER = 'stops-label';

export default function StopLayer({ map }) {
  const loadedRef = useRef(false);

  useEffect(() => {
    if (!map || loadedRef.current) return;

    async function loadStops() {
      try {
        const stops = await fetchStops();
        if (!Array.isArray(stops) || stops.length === 0) return;

        // Build GeoJSON
        const features = stops
          .filter(s => s.lat && s.lon)
          .map(s => ({
            type: 'Feature',
            geometry: {
              type: 'Point',
              coordinates: [s.lon, s.lat], // MapLibre: [lng, lat]
            },
            properties: {
              id: s.id,
              name: s.name,
              city: s.city || 'Dresden',
            },
          }));

        const geojson = { type: 'FeatureCollection', features };

        // Add source
        if (!map.getSource(STOP_SOURCE_ID)) {
          map.addSource(STOP_SOURCE_ID, { type: 'geojson', data: geojson });
        }

        // Outer glow layer
        if (!map.getLayer(STOP_GLOW_LAYER)) {
          map.addLayer({
            id: STOP_GLOW_LAYER,
            type: 'circle',
            source: STOP_SOURCE_ID,
            minzoom: 12,
            paint: {
              'circle-radius': [
                'interpolate', ['linear'], ['zoom'],
                12, 8,
                15, 14,
                18, 20,
              ],
              'circle-color': '#0ea5e9',
              'circle-opacity': 0.4,
              'circle-blur': 0.8,
            },
          });
        }

        // Inner dot layer
        if (!map.getLayer(STOP_DOT_LAYER)) {
          map.addLayer({
            id: STOP_DOT_LAYER,
            type: 'circle',
            source: STOP_SOURCE_ID,
            minzoom: 12,
            paint: {
              'circle-radius': [
                'interpolate', ['linear'], ['zoom'],
                12, 2.5,
                15, 4.5,
                18, 7,
              ],
              'circle-color': '#38bdf8',
              'circle-stroke-width': 1.8,
              'circle-stroke-color': '#ffffff',
            },
          });
        }

        // Label layer — station names visible from zoom 13+
        if (!map.getLayer(STOP_LABEL_LAYER)) {
          map.addLayer({
            id: STOP_LABEL_LAYER,
            type: 'symbol',
            source: STOP_SOURCE_ID,
            minzoom: 13,
            layout: {
              'text-field': ['get', 'name'],
              'text-size': [
                'interpolate', ['linear'], ['zoom'],
                13, 9,
                15, 11,
                17, 13,
              ],
              'text-offset': [0, 1.4],
              'text-anchor': 'top',
              'text-font': ['Noto Sans Bold'],
              'text-max-width': 10,
              'text-optional': true,
            },
            paint: {
              'text-color': '#c4dff6',
              'text-halo-color': 'rgba(8, 12, 21, 0.92)',
              'text-halo-width': 2,
            },
          });
        }

        loadedRef.current = true;
        console.log(`[StopLayer] Loaded ${features.length} stop markers`);
      } catch (err) {
        console.error('[StopLayer] Failed to load stops:', err);
      }
    }

    loadStops();
  }, [map]);

  return null;
}
